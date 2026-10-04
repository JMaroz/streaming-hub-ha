"""Main FastAPI entrypoint and API router for Streaming Hub."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import random
from typing import Any
from urllib.parse import urlparse

import aiohttp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from .database import MediaDatabase
from .dns_resolver import DNS_DEFAULT
from .ha_client import HACoreClient
from .metadata import MetadataEnricher
from .models import Movie, Profile, ProviderSource, TvSeries
from .proxy import StreamProxy
from .rating_filter import (
    get_profile_by_id as filter_get_profile_by_id,
    get_profile_max_rating,
    is_title_allowed_for_profile,
)
from .skip_segments import SkipSegmentManager
from .sources.anime_source import AnimeSource
from .sources.crawler_source import CrawlerSource
from .sources.detector import SourceDetector
from .sources.manager import SourceManager
from .sources.reactive_source import ReactiveSource
from .subtitles import SubtitleManager
from .trakt_client import TraktClient
from .utils import CatalogMerger

_LOGGER = logging.getLogger("streaming_hub")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
OPTIONS_FILE = Path("/data/options.json")


def load_options() -> dict[str, Any]:
    """Load add-on options from Supervisor /data/options.json or environment."""
    custom_sources_env = os.getenv("CUSTOM_SOURCES", "").strip()
    parsed_sources: list[Any] = []
    if custom_sources_env:
        try:
            parsed_sources = json.loads(custom_sources_env)
        except Exception:
            parsed_sources = [s.strip() for s in custom_sources_env.split(",") if s.strip()]

    options = {
        "log_level": os.getenv("LOG_LEVEL", "info"),
        "country": str(os.getenv("COUNTRY", "IT")).strip().upper(),
        "custom_dns": os.getenv("CUSTOM_DNS", DNS_DEFAULT),
        "tmdb_api_key": os.getenv("TMDB_API_KEY", ""),
        "stream_port": int(os.getenv("STREAM_PORT", "8099")),
        "anime_preferred_language": os.getenv("ANIME_PREFERRED_LANGUAGE", "all"),
        "anime_enable_tab": os.getenv("ANIME_ENABLE_TAB", "true").lower() in ("true", "1", "yes"),
        "custom_sources": parsed_sources,
        "profiles": [],
    }

    if OPTIONS_FILE.exists():
        try:
            with OPTIONS_FILE.open(encoding="utf-8") as f:
                supervisor_opts = json.load(f)
                options.update(supervisor_opts)
        except Exception as err:
            _LOGGER.warning("Could not read /data/options.json: %s", err)

    # Normalize custom_sources: support list of dicts, list of strings, or legacy parameters
    raw_sources = options.get("custom_sources") or options.get("sources") or []
    normalized_sources: list[dict[str, Any]] = []
    for item in raw_sources:
        if isinstance(item, str) and item.strip():
            normalized_sources.append({"url": item.strip(), "type": "auto", "name": "", "enabled": True})
        elif isinstance(item, dict) and item.get("url"):
            normalized_sources.append(
                {
                    "url": str(item["url"]).strip(),
                    "type": str(item.get("type", "auto")).strip(),
                    "name": str(item.get("name", "")).strip(),
                    "enabled": bool(item.get("enabled", True)),
                }
            )

    # Backward compatibility with single URL env vars if explicitly set by user
    sc_env = os.getenv("SOURCE_ALPHA_BASE_URL", "").strip() or os.getenv("STREAMINGCOMMUNITY_BASE_URL", "").strip()
    if sc_env and not any(s["url"] == sc_env for s in normalized_sources):
        normalized_sources.append({"url": sc_env, "type": "reactive", "name": "Sorgente Reattiva", "enabled": True})

    cb_env = os.getenv("SOURCE_BETA_BASE_URL", "").strip() or os.getenv("CB01_BASE_URL", "").strip()
    if cb_env and not any(s["url"] == cb_env for s in normalized_sources):
        normalized_sources.append({"url": cb_env, "type": "crawler", "name": "Sorgente Web", "enabled": True})

    anime_env = os.getenv("SOURCE_ANIME_BASE_URL", "").strip() or os.getenv("ANIME_BASE_URL", "").strip()
    if anime_env and not any(s["url"] == anime_env for s in normalized_sources):
        normalized_sources.append({"url": anime_env, "type": "anime", "name": "Sorgente Anime", "enabled": True})

    options["custom_sources"] = normalized_sources

    # Normalize profiles
    raw_profiles = options.get("profiles") or []
    normalized_profiles: list[Profile] = []
    if isinstance(raw_profiles, list):
        for p in raw_profiles:
            if isinstance(p, dict) and p.get("name"):
                pid = str(p.get("id") or p.get("name", "")).lower().replace(" ", "_")
                # Inherit global tmdb_api_key if personal is empty
                p_tmdb = str(p.get("tmdb_api_key", "")).strip() or str(options.get("tmdb_api_key", "")).strip()
                normalized_profiles.append(
                    Profile(
                        id=pid,
                        name=str(p["name"]).strip(),
                        avatar=str(p.get("avatar") or "avatar_1"),
                        rating_filter=str(p.get("rating_filter") or "ALL"),
                        tmdb_api_key=p_tmdb,
                        trakt_client_id=str(p.get("trakt_client_id") or "").strip(),
                        trakt_access_token=str(p.get("trakt_access_token") or "").strip(),
                        pin=str(p["pin"]).strip() if p.get("pin") else None,
                    )
                )

    if not normalized_profiles:
        # Default single profile fallback
        normalized_profiles.append(
            Profile(
                id="default",
                name="Principale",
                avatar="avatar_1",
                rating_filter="ALL",
                tmdb_api_key=str(options.get("tmdb_api_key", "")).strip(),
            )
        )

    options["profiles"] = normalized_profiles
    return options


CONFIG = load_options()

# Logging setup
log_level_name = str(CONFIG.get("log_level", "info")).upper()
numeric_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Global components
ha_client = HACoreClient()
stream_proxy = StreamProxy()
metadata_enricher = MetadataEnricher(tmdb_api_key=CONFIG.get("tmdb_api_key"))
db = MediaDatabase()
subtitle_manager = SubtitleManager()
skip_segments_manager = SkipSegmentManager()

# Initialize Source Manager
source_manager = SourceManager()


async def init_sources(sources_list: list[dict[str, Any]], custom_dns: str) -> None:
    """Initialize and register configured user sources with auto-discrimination."""
    async with aiohttp.ClientSession() as session:
        for idx, src_conf in enumerate(sources_list):
            url = src_conf.get("url", "").strip()
            if not url:
                continue
            is_enabled = src_conf.get("enabled", True)
            user_type = src_conf.get("type", "auto")
            custom_name = src_conf.get("name") or ""

            detected_type = await SourceDetector.detect(url, user_specified_type=user_type, session=session)
            _LOGGER.info("Configuring source #%d: %s -> detected type: %s", idx + 1, url, detected_type)

            if detected_type in ("reactive", "streamingcommunity"):
                source_manager.register_source(
                    ReactiveSource(
                        base_url=url,
                        custom_dns=custom_dns,
                        enabled=is_enabled,
                        name=custom_name or "Sorgente Reattiva",
                    )
                )
            elif detected_type in ("crawler", "cb01"):
                source_manager.register_source(
                    CrawlerSource(
                        base_url=url,
                        custom_dns=custom_dns,
                        enabled=is_enabled,
                        name=custom_name or "Sorgente Web",
                    )
                )
            elif detected_type in ("anime", "engine_anime"):
                source_manager.register_source(
                    AnimeSource(
                        base_url=url,
                        custom_dns=custom_dns,
                        enabled=is_enabled,
                        name=custom_name or "Sorgente Anime",
                    )
                )
            else:
                _LOGGER.warning("Source #%d (%s) could not be mapped to any known streaming engine.", idx + 1, url)


CACHE_TTL_ON_DEMAND_SECONDS = 24 * 3600  # 24 hours
BG_SYNC_INTERVAL_SECONDS = 12 * 3600  # 12 hours


async def _background_sync_worker() -> None:
    """Periodic background worker running every 12 hours to refresh active series and movies."""
    _LOGGER.info("Starting background metadata sync worker (interval: 12h)...")
    while True:
        try:
            await asyncio.sleep(BG_SYNC_INTERVAL_SECONDS)
            candidates = await db.get_candidates_for_background_sync(limit=15)
            if candidates:
                _LOGGER.info("Background sync starting for %d active candidates", len(candidates))
            for cand in candidates:
                media_id = cand["media_id"]
                media_type = cand["media_type"]
                try:
                    if media_type == "tv" and cand.get("season_number"):
                        s_num = cand["season_number"]
                        _LOGGER.debug("Background syncing TV series %s S%s", media_id, s_num)
                        fresh_season = await source_manager.get_season(media_id, s_num)
                        if fresh_season and fresh_season.episodes:
                            title_data = await db.get_title(media_id)
                            tmdb_id = title_data.get("tmdb_id") if title_data else None
                            if tmdb_id:
                                await metadata_enricher.enrich_tv_season(tmdb_id, fresh_season)
                            await db.save_season(media_id, fresh_season)
                    elif media_type == "movie":
                        _LOGGER.debug("Background syncing movie %s", media_id)
                        fresh_movie = await source_manager.get_details("movie", media_id)
                        if fresh_movie:
                            tmdb_key = CONFIG.get("tmdb_api_key") or metadata_enricher.tmdb_api_key
                            await metadata_enricher.enrich_movie(fresh_movie, api_key=tmdb_key)
                            await db.save_title(fresh_movie)
                except Exception as err:
                    _LOGGER.debug("Background sync skipped item %s: %s", media_id, err)
                # Polite non-blocking pause between requests to prevent upstream rate limiting
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            _LOGGER.info("Background sync worker cancelled.")
            break
        except Exception as err:
            _LOGGER.warning("Unexpected error in background sync worker: %s", err)
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    _LOGGER.info("Starting Streaming Hub Engine...")
    await db.init()
    custom_dns = CONFIG.get("custom_dns", DNS_DEFAULT)
    custom_sources = CONFIG.get("custom_sources", [])

    if custom_sources:
        await init_sources(custom_sources, custom_dns)
    else:
        _LOGGER.warning("No user sources configured. Please configure sources in Add-on settings.")

    _LOGGER.info(
        "Sources active: %s | DNS=%s | Stream Port=%s",
        [s["name"] for s in source_manager.list_sources() if s["enabled"]],
        custom_dns,
        CONFIG.get("stream_port"),
    )
    sync_task = asyncio.create_task(_background_sync_worker())
    try:
        yield
    finally:
        _LOGGER.info("Shutting down Streaming Hub...")
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task
        await source_manager.close_all()
        await metadata_enricher.close()
        await stream_proxy.close()


app = FastAPI(
    title="Streaming Hub",
    description="Home Assistant App for media streaming, HLS proxying, and Cast control",
    version="1.2.3",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Models
class ResolveRequest(BaseModel):
    page_url: str
    provider_id: str | None = None
    media_id: str | None = None
    quality: str | None = None
    prefer_fhd: bool = True


class CastRequest(BaseModel):
    entity_id: str
    page_url: str
    title: str
    poster_url: str | None = None
    provider_id: str | None = None
    media_id: str | None = None
    quality: str | None = None
    media_type: str = "movie"
    season_number: int | None = None
    episode_number: int | None = None
    seek_seconds: float = 0
    profile_id: str = "default"
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None


class TestSourceRequest(BaseModel):
    url: str
    type: str = "auto"


class ProgressRequest(BaseModel):
    media_id: str
    title: str
    media_type: str = "movie"
    poster_url: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    progress_seconds: float = 0
    duration_seconds: float = 0
    profile_id: str = "default"
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None


class FavoriteRequest(BaseModel):
    title_id: str
    media_type: str = "movie"
    title: str
    poster_url: str | None = None
    profile_id: str = "default"
    tmdb_id: int | None = None
    imdb_id: str | None = None


class TraktScrobbleRequest(BaseModel):
    action: str  # "start", "pause", "stop"
    media_type: str
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    progress_percent: float = 0
    profile_id: str = "default"


class TraktDeviceCodeRequest(BaseModel):
    profile_id: str = "default"


class TraktPollTokenRequest(BaseModel):
    profile_id: str = "default"
    device_code: str


# Helpers
def get_ingress_path(request: Request) -> str:
    """Extract Ingress base path from header or query string."""
    ingress_hdr = request.headers.get("x-ingress-path") or request.headers.get("X-Ingress-Path")
    if ingress_hdr:
        return ingress_hdr.rstrip("/")
    return ""


def get_profile_by_id(profile_id: str) -> Profile:
    """Find profile by id or fallback to first/default profile."""
    profiles: list[Profile] = CONFIG.get("profiles", [])
    return filter_get_profile_by_id(profile_id, profiles)


def get_profile_trakt_client(profile: Profile) -> TraktClient | None:
    """Instantiate a TraktClient for profile if client_id is set."""
    if not profile.trakt_client_id:
        return None
    return TraktClient(client_id=profile.trakt_client_id, access_token=profile.trakt_access_token)


# API Endpoints
@app.get("/api/status")
async def get_status(request: Request) -> dict[str, Any]:
    """Retrieve system, source, and supervisor status."""
    ingress_path = get_ingress_path(request)
    ha_host = await ha_client.get_host_ip_or_url()

    return {
        "status": "online",
        "app_name": "Streaming Hub",
        "version": "1.2.3",
        "ingress_path": ingress_path,
        "ha_host_ip": ha_host,
        "stream_port": CONFIG.get("stream_port", 8099),
        "supervisor_connected": ha_client.is_available,
        "sources": source_manager.list_sources(),
        "dns_mode": CONFIG.get("custom_dns"),
        "country": CONFIG.get("country", "IT"),
        "tmdb_configured": bool(metadata_enricher.tmdb_api_key),
        "active_stream_sessions": len(stream_proxy._sessions),
    }


PROVIDER_CANONICAL_GROUPS = [
    {
        "id": "amazon",
        "name": "Amazon Prime Video",
        "keywords": ("amazon", "prime video", "freevee"),
    },
    {
        "id": "netflix",
        "name": "Netflix",
        "keywords": ("netflix",),
    },
    {
        "id": "disney",
        "name": "Disney+",
        "keywords": ("disney",),
    },
    {
        "id": "apple",
        "name": "Apple TV+",
        "keywords": ("apple tv", "apple"),
    },
    {
        "id": "paramount",
        "name": "Paramount+",
        "keywords": ("paramount",),
    },
    {
        "id": "max",
        "name": "Max",
        "keywords": ("hbo", "max"),
    },
    {
        "id": "raiplay",
        "name": "RaiPlay",
        "keywords": ("raiplay", "rai play"),
    },
    {
        "id": "mediaset",
        "name": "Mediaset Infinity",
        "keywords": ("mediaset", "infinity"),
    },
    {
        "id": "timvision",
        "name": "TIMVISION",
        "keywords": ("timvision",),
    },
    {
        "id": "now",
        "name": "NOW",
        "keywords": ("now tv", "sky go", "now"),
    },
    {
        "id": "discovery",
        "name": "Discovery+",
        "keywords": ("discovery+", "discovery plus", "discovery"),
    },
    {
        "id": "crunchyroll",
        "name": "Crunchyroll",
        "keywords": ("crunchyroll",),
    },
    {
        "id": "pluto",
        "name": "Pluto TV",
        "keywords": ("pluto tv", "pluto"),
    },
    {
        "id": "rakuten",
        "name": "Rakuten TV",
        "keywords": ("rakuten",),
    },
    {
        "id": "youtube",
        "name": "YouTube",
        "keywords": ("youtube",),
    },
]


def get_canonical_provider_group(provider_name: str) -> tuple[str, str]:
    """Return (group_id, canonical_name) for a provider name."""
    p_lower = (provider_name or "").lower().strip()
    for g in PROVIDER_CANONICAL_GROUPS:
        for kw in g["keywords"]:
            if kw in p_lower:
                return g["id"], g["name"]
    clean_id = "".join(c for c in p_lower if c.isalnum())
    return clean_id or "other", provider_name


def extract_streaming_availability(item_dict_or_obj: Any, country_code: str) -> dict[str, Any]:
    """Format country-specific watch providers from TMDb results with canonical provider grouping.
    
    Zero Extra Cost Rule:
    grouped_logos and grouped_providers MUST ONLY include subscription and free streaming (flatrate, free, ads).
    Rent and buy are strictly excluded from grouped_logos to prevent misleading users into thinking paid titles are included.
    """
    c_code = (country_code or "IT").upper().strip()
    if isinstance(item_dict_or_obj, dict):
        raw_wp = item_dict_or_obj.get("watch_providers") or {}
    else:
        raw_wp = getattr(item_dict_or_obj, "watch_providers", {}) or {}

    c_data = raw_wp.get(c_code, {}) if isinstance(raw_wp, dict) else {}
    from .metadata import TMDB_IMAGE_BASE

    def _fmt_list(p_list: Any) -> list[dict[str, Any]]:
        if not p_list or not isinstance(p_list, list):
            return []
        res: list[dict[str, Any]] = []
        for p in p_list:
            if isinstance(p, dict) and p.get("provider_name"):
                logo_path = p.get("logo_path")
                logo_url = f"{TMDB_IMAGE_BASE}{logo_path}" if logo_path else None
                res.append(
                    {
                        "provider_id": p.get("provider_id"),
                        "provider_name": p.get("provider_name"),
                        "logo_path": logo_path,
                        "logo_url": logo_url,
                        "display_priority": p.get("display_priority", 99),
                    }
                )
        res.sort(key=lambda x: x["display_priority"])
        return res

    flatrate = _fmt_list(c_data.get("flatrate") if isinstance(c_data, dict) else None)
    free = _fmt_list(c_data.get("free") if isinstance(c_data, dict) else None)
    ads = _fmt_list(c_data.get("ads") if isinstance(c_data, dict) else None)
    rent = _fmt_list(c_data.get("rent") if isinstance(c_data, dict) else None)
    buy = _fmt_list(c_data.get("buy") if isinstance(c_data, dict) else None)

    # ZERO EXTRA COST RULE:
    # Card streaming icons (grouped_logos) and grouped_providers MUST ONLY include
    # subscription / free / ad-supported streaming: flatrate, free, ads.
    # Rent and buy are completely EXCLUDED from grouped_logos and grouped_providers!
    included_offers = [
        (flatrate, "flatrate", "Abbonamento", "flatrate"),
        (ads, "ads", "Gratis con Pubblicità", "free"),
        (free, "free", "Gratuito", "free"),
    ]

    seen_groups: set[str] = set()
    grouped_logos: list[dict[str, Any]] = []
    grouped_map: dict[str, dict[str, Any]] = {}

    for p_list, type_key, label, badge_class in included_offers:
        for p in p_list:
            gid, cname = get_canonical_provider_group(p["provider_name"])
            # 1. Deduplicated mini logos for cards (max 4)
            if gid not in seen_groups and (p.get("logo_url") or p.get("logo_path")):
                seen_groups.add(gid)
                grouped_logos.append(
                    {
                        "provider_id": p.get("provider_id"),
                        "provider_name": cname,
                        "group_id": gid,
                        "logo_path": p.get("logo_path"),
                        "logo_url": p.get("logo_url"),
                    }
                )

            # 2. Consolidated providers for modal details
            if gid not in grouped_map:
                grouped_map[gid] = {
                    "group_id": gid,
                    "provider_name": cname,
                    "logo_path": p.get("logo_path"),
                    "logo_url": p.get("logo_url"),
                    "badges": [],
                }
            # Add badge if not already added for this group
            if not any(b["key"] == type_key for b in grouped_map[gid]["badges"]):
                grouped_map[gid]["badges"].append(
                    {"key": type_key, "label": label, "badgeClass": badge_class}
                )

    grouped_logos = grouped_logos[:4]
    grouped_providers = list(grouped_map.values())

    return {
        "country": c_code,
        "link": c_data.get("link") if isinstance(c_data, dict) else None,
        "flatrate": flatrate,
        "free": free,
        "ads": ads,
        "rent": rent,
        "buy": buy,
        "grouped_logos": grouped_logos,
        "grouped_providers": grouped_providers,
    }


class ValidateTmdbKeyRequest(BaseModel):
    api_key: str | None = None
    save: bool = False


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    """Retrieve current settings, configured sources, and active engines."""
    key = metadata_enricher.tmdb_api_key
    masked_key = f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else ("***" if key else "")
    return {
        "country": CONFIG.get("country", "IT"),
        "custom_dns": CONFIG.get("custom_dns", DNS_DEFAULT),
        "configured_sources": CONFIG.get("custom_sources", []),
        "active_sources": source_manager.list_sources(),
        "anime_preferred_language": CONFIG.get("anime_preferred_language", "all"),
        "anime_enable_tab": CONFIG.get("anime_enable_tab", True),
        "tmdb_configured": bool(key),
        "tmdb_key_masked": masked_key,
    }


@app.post("/api/settings/tmdb/validate")
async def validate_tmdb_key(req: ValidateTmdbKeyRequest | None = None) -> dict[str, Any]:
    """Validate a TMDb API key or v4 Bearer token against TMDb API and optionally save it dynamically."""
    key_input = req.api_key if req and req.api_key is not None else CONFIG.get("tmdb_api_key", "")
    valid, message = await metadata_enricher.validate_api_key(key_input)

    if valid and req and req.save and req.api_key:
        clean_key = req.api_key.strip().strip("\"'")
        if clean_key.lower().startswith("bearer "):
            clean_key = clean_key[7:].strip()
        CONFIG["tmdb_api_key"] = clean_key
        metadata_enricher.tmdb_api_key = clean_key
        metadata_enricher.clear_cache()
        _LOGGER.info("Successfully updated TMDb API key in active session.")

    return {
        "valid": valid,
        "message": message,
        "configured": bool(metadata_enricher.tmdb_api_key),
    }


@app.post("/api/settings/sources/test")
async def test_source_url(req: TestSourceRequest) -> dict[str, Any]:
    """Test a source URL and detect its streaming provider type."""
    clean_url = req.url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    detected = await SourceDetector.detect(clean_url, user_specified_type=req.type)
    return {
        "url": clean_url,
        "specified_type": req.type,
        "detected_type": detected,
        "supported": detected in ("reactive", "crawler", "anime", "streamingcommunity", "cb01"),
    }


@app.get("/api/sources")
async def get_sources() -> list[dict[str, Any]]:
    """Retrieve list of all registered catalog and streaming sources."""
    return source_manager.list_sources()


@app.get("/api/players")
async def get_players() -> list[dict[str, Any]]:
    """Retrieve all available media players from Home Assistant Core."""
    players = await ha_client.get_media_players()
    return [
        {
            "entity_id": p.entity_id,
            "name": p.name,
            "is_cast": p.is_cast,
            "state": p.state,
            "device_class": p.device_class,
        }
        for p in players
    ]


@app.get("/api/profiles")
async def get_profiles() -> list[dict[str, Any]]:
    """Retrieve configured family profiles (without exposing private secrets)."""
    profiles: list[Profile] = CONFIG.get("profiles", [])
    return [p.to_dict(include_secrets=False) for p in profiles]


@app.post("/api/trakt/auth/device-code")
async def get_trakt_device_code(req: TraktDeviceCodeRequest) -> dict[str, Any]:
    """Request a device code and verification URL from Trakt."""
    profile = get_profile_by_id(req.profile_id)
    if not profile.trakt_client_id:
        raise HTTPException(status_code=400, detail="Trakt Client ID non configurato per questo profilo.")
    trakt = TraktClient(client_id=profile.trakt_client_id)
    res = await trakt.generate_device_code()
    if not res:
        raise HTTPException(status_code=502, detail="Impossibile contattare l'API di Trakt.tv.")
    return res


@app.post("/api/trakt/auth/token")
async def poll_trakt_token(req: TraktPollTokenRequest) -> dict[str, Any]:
    """Poll for Trakt access token once user verifies device code."""
    profile = get_profile_by_id(req.profile_id)
    if not profile.trakt_client_id:
        raise HTTPException(status_code=400, detail="Trakt Client ID non configurato.")
    trakt = TraktClient(client_id=profile.trakt_client_id)
    token_res = await trakt.poll_device_token(req.device_code)
    if not token_res or "access_token" not in token_res:
        raise HTTPException(status_code=400, detail="Token non ancora autorizzato o errore di autenticazione.")
    profile.trakt_access_token = token_res["access_token"]
    return {"status": "ok", "access_token": token_res["access_token"]}


@app.post("/api/trakt/scrobble")
async def trakt_scrobble(req: TraktScrobbleRequest) -> dict[str, Any]:
    """Send playback scrobble event to Trakt for active profile."""
    profile = get_profile_by_id(req.profile_id)
    trakt = get_profile_trakt_client(profile)
    if not trakt or not trakt.is_authenticated:
        return {"status": "ignored", "reason": "trakt_not_authenticated"}

    success = await trakt.scrobble_action(
        action=req.action,
        media_type=req.media_type,
        title=req.title,
        year=req.year,
        tmdb_id=req.tmdb_id,
        imdb_id=req.imdb_id,
        season_number=req.season_number,
        episode_number=req.episode_number,
        progress_percent=req.progress_percent,
    )
    return {"status": "ok", "scrobbled": success}


@app.get("/api/catalog/home")
async def get_home_catalog(
    source: str = Query("all"),
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Retrieve home view catalog: editorial carousels when supported, or indicator for grid mode."""
    profile = get_profile_by_id(profile_id)
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()

    hero_item, raw_carousels = await source_manager.get_home_carousels(source_filter=source)

    if not raw_carousels:
        return {
            "mode": "grid",
            "source": source,
            "profile_id": profile.id,
            "hero": None,
            "carousels": [],
        }

    # 1. Collect all items across carousels (plus hero) to enrich in one batch
    all_items: list[Movie | TvSeries] = []
    if hero_item:
        all_items.append(hero_item)
    for c in raw_carousels:
        all_items.extend(it for it in c.get("items", []) if isinstance(it, (Movie, TvSeries)))

    await db.enrich_items_with_cached_metadata(all_items)

    # 2. Filter carousels by profile Parental Control and prune empty ones
    def is_item_available(it: Movie | TvSeries) -> bool:
        if isinstance(it, Movie) and it.sources:
            return any(s.available for s in it.sources)
        return True

    filtered_carousels: list[dict[str, Any]] = []
    allowed_pool: list[Movie | TvSeries] = []

    for c in raw_carousels:
        allowed_items = [
            it
            for it in c.get("items", [])
            if isinstance(it, (Movie, TvSeries)) and is_title_allowed_for_profile(it, profile) and is_item_available(it)
        ]
        # Prune carousel if empty after parental control and availability filter
        if not allowed_items:
            continue

        allowed_pool.extend(allowed_items)
        serialized_items = [it.to_dict() for it in allowed_items]
        for it_dict in serialized_items:
            it_dict["streaming_availability"] = extract_streaming_availability(it_dict, active_country)

        filtered_carousels.append(
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "count": len(serialized_items),
                "items": serialized_items,
            }
        )

    # If filtering pruned all carousels, return grid mode
    if not filtered_carousels:
        return {
            "mode": "grid",
            "source": source,
            "profile_id": profile.id,
            "hero": None,
            "carousels": [],
        }

    # 3. Hero banner selection:
    # Check if billboard/featured hero is allowed and available
    selected_hero: Movie | TvSeries | None = None
    if hero_item and is_title_allowed_for_profile(hero_item, profile) and is_item_available(hero_item):
        selected_hero = hero_item
    elif allowed_pool:
        # Pick candidate with valid backdrop or poster
        candidates_with_backdrop = [it for it in allowed_pool if it.backdrop_url or it.poster_url]
        if candidates_with_backdrop:
            high_rated = [it for it in candidates_with_backdrop if (it.rating or 0.0) >= 7.0]
            selected_hero = random.choice(high_rated) if high_rated else random.choice(candidates_with_backdrop)
        else:
            selected_hero = allowed_pool[0]

    hero_dict = None
    if selected_hero:
        hero_dict = selected_hero.to_dict()
        hero_dict["streaming_availability"] = extract_streaming_availability(hero_dict, active_country)

    return {
        "mode": "carousels",
        "source": source,
        "profile_id": profile.id,
        "hero": hero_dict,
        "carousels": filtered_carousels,
    }


@app.get("/api/catalog/anime")
async def get_anime_catalog(
    page: int = Query(1, ge=1),
    source: str = Query("all"),
    dub: str = Query("all", pattern="^(all|sub_only|dub_only)$"),
    profile_id: str = Query("default"),
    min_rating: float | None = Query(None),
    sort_by: str = Query("latest", pattern="^(latest|rating|year|alpha)$"),
) -> dict[str, Any]:
    """Retrieve paginated anime catalog with dub filtering and sorting."""
    profile = get_profile_by_id(profile_id)
    active_dub = dub
    if active_dub == "all":
        cfg_dub = CONFIG.get("anime_preferred_language", "all")
        if cfg_dub in ("sub_only", "dub_only"):
            active_dub = cfg_dub

    anime_src = source_manager.get_source("anime")
    if anime_src and anime_src.is_enabled and hasattr(anime_src, "get_latest_anime"):
        items = await anime_src.get_latest_anime(page=page, dub_filter=active_dub)
    else:
        items = await source_manager.get_by_genre("Anime", media_type="tv", source_filter=source, page=page)
        if active_dub == "dub_only":
            items = [it for it in items if getattr(it, "dub_type", None) == "dub"]
        elif active_dub == "sub_only":
            items = [it for it in items if getattr(it, "dub_type", None) == "sub"]

    await db.enrich_items_with_cached_metadata(items)
    filtered = [it for it in items if is_title_allowed_for_profile(it, profile)]

    if min_rating is not None:
        filtered = [item for item in filtered if (item.rating or 0.0) >= min_rating]

    if sort_by == "rating":
        filtered.sort(key=lambda x: x.rating or 0.0, reverse=True)
    elif sort_by == "year":
        filtered.sort(key=lambda x: x.year or 0, reverse=True)
    elif sort_by == "alpha":
        filtered.sort(key=lambda x: (x.title or "").lower())

    results = [item.to_dict() for item in filtered]
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()
    for r in results:
        r["streaming_availability"] = extract_streaming_availability(r, active_country)

    from_idx = (page - 1) * 30 + 1 if results else 0
    to_idx = from_idx + len(results) - 1 if results else 0

    return {
        "page": page,
        "source": source,
        "profile_id": profile.id,
        "dub": active_dub,
        "count": len(results),
        "from": from_idx,
        "to": to_idx,
        "results": results,
    }


@app.get("/api/catalog/latest")
async def get_latest(
    type: str = Query("all", pattern="^(all|movie|tv|anime)$"),
    source: str = Query("all"),
    page: int = Query(1, ge=1),
    profile_id: str = Query("default"),
    year_min: int | None = Query(None),
    year_max: int | None = Query(None),
    min_rating: float | None = Query(None),
    sort_by: str = Query("latest", pattern="^(latest|rating|year|alpha)$"),
) -> dict[str, Any]:
    """Retrieve latest titles across enabled sources with rating filter, multi-criteria filters and sorting."""
    if type == "anime":
        return await get_anime_catalog(
            page=page,
            source=source,
            dub="all",
            profile_id=profile_id,
            min_rating=min_rating,
            sort_by=sort_by,
        )

    profile = get_profile_by_id(profile_id)
    max_rating = get_profile_max_rating(profile)

    # For kids profiles (<= 6, e.g. T, 6+, PEGI 3, PEGI 7), generic unfiltered feed from scrapers
    # contains adult/horror movies without genre tags. Instead, directly fetch certified family channels!
    if max_rating <= 6:
        items = []
        if type in ("all", "movie"):
            anim_m = await source_manager.get_by_genre(
                "Animazione", media_type="movie", source_filter=source, page=page
            )
            fam_m = await source_manager.get_by_genre("Famiglia", media_type="movie", source_filter=source, page=page)
            items.extend(CatalogMerger.merge_movie_lists(anim_m, fam_m))
        if type in ("all", "tv"):
            anim_tv = await source_manager.get_by_genre("Animazione", media_type="tv", source_filter=source, page=page)
            kids_tv = await source_manager.get_by_genre("Kids", media_type="tv", source_filter=source, page=page)
            items.extend(CatalogMerger.merge_tv_lists(anim_tv, kids_tv))
        if type == "all":
            movies = [it for it in items if isinstance(it, Movie)]
            series = [it for it in items if isinstance(it, TvSeries)]
            interleaved = []
            for i in range(max(len(movies), len(series))):
                if i < len(movies):
                    interleaved.append(movies[i])
                if i < len(series):
                    interleaved.append(series[i])
            items = interleaved
    else:
        items = await source_manager.get_latest(media_type=type, source_filter=source, page=page)

    # 1. Hydrate titles with SQLite-cached certification, genres, and hosting URLs
    await db.enrich_items_with_cached_metadata(items)

    filtered = [item for item in items if is_title_allowed_for_profile(item, profile)]

    # 2. If rating filtering reduced the page below 15 items on an active profile, top up from next upstream page
    if len(filtered) < 15 and max_rating < 99 and page < 10:
        try:
            extra_items = await source_manager.get_latest(media_type=type, source_filter=source, page=page + 1)
            if extra_items:
                await db.enrich_items_with_cached_metadata(extra_items)
                extra_filtered = [it for it in extra_items if is_title_allowed_for_profile(it, profile)]
                filtered.extend(extra_filtered)
        except Exception:
            pass

    # 3. Apply optional multi-criteria filters
    if year_min is not None:
        filtered = [item for item in filtered if (item.year or 0) >= year_min]
    if year_max is not None:
        filtered = [item for item in filtered if (item.year or 9999) <= year_max]
    if min_rating is not None:
        filtered = [item for item in filtered if (item.rating or 0.0) >= min_rating]

    # 4. Apply custom sorting
    if sort_by == "rating":
        filtered.sort(key=lambda x: x.rating or 0.0, reverse=True)
    elif sort_by == "year":
        filtered.sort(key=lambda x: x.year or 0, reverse=True)
    elif sort_by == "alpha":
        filtered.sort(key=lambda x: (x.title or "").lower())

    results = [item.to_dict() for item in filtered]
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()
    for r in results:
        r["streaming_availability"] = extract_streaming_availability(r, active_country)

    from_idx = (page - 1) * 30 + 1 if results else 0
    to_idx = from_idx + len(results) - 1 if results else 0

    return {
        "page": page,
        "source": source,
        "profile_id": profile.id,
        "count": len(results),
        "from": from_idx,
        "to": to_idx,
        "results": results,
    }


@app.get("/api/catalog/search")
async def search_catalog(
    q: str = Query(..., min_length=1),
    type: str = Query("all", pattern="^(all|movie|tv|anime)$"),
    source: str = Query("all"),
    profile_id: str = Query("default"),
    year_min: int | None = Query(None),
    year_max: int | None = Query(None),
    min_rating: float | None = Query(None),
    sort_by: str = Query("latest", pattern="^(latest|rating|year|alpha)$"),
) -> dict[str, Any]:
    """Search catalog by title across enabled sources filtered for active profile with optional sorting."""
    profile = get_profile_by_id(profile_id)
    query = q.strip()
    search_type = "all" if type == "anime" else type
    items = await source_manager.search(query, media_type=search_type, source_filter=source)
    if type == "anime":
        items = [
            it
            for it in items
            if getattr(it, "is_anime", False)
            or "anime" in getattr(it, "catalogs", [])
            or any("anim" in g.lower() for g in getattr(it, "genres", []))
        ]
    await db.enrich_items_with_cached_metadata(items)
    filtered = [item for item in items if is_title_allowed_for_profile(item, profile)]

    if year_min is not None:
        filtered = [item for item in filtered if (item.year or 0) >= year_min]
    if year_max is not None:
        filtered = [item for item in filtered if (item.year or 9999) <= year_max]
    if min_rating is not None:
        filtered = [item for item in filtered if (item.rating or 0.0) >= min_rating]

    if sort_by == "rating":
        filtered.sort(key=lambda x: x.rating or 0.0, reverse=True)
    elif sort_by == "year":
        filtered.sort(key=lambda x: x.year or 0, reverse=True)
    elif sort_by == "alpha":
        filtered.sort(key=lambda x: (x.title or "").lower())

    results = [item.to_dict() for item in filtered]
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()
    for r in results:
        r["streaming_availability"] = extract_streaming_availability(r, active_country)
    return {"query": query, "source": source, "profile_id": profile.id, "count": len(results), "results": results}


@app.get("/api/catalog/genres")
async def get_genres() -> list[str]:
    """Return available unique genres across all sources."""
    return await source_manager.get_all_genres()


@app.get("/api/catalog/genre/{genre}")
async def get_by_genre(
    genre: str,
    type: str = Query("movie", pattern="^(movie|tv)$"),
    source: str = Query("all"),
    page: int = Query(1, ge=1),
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Browse catalog by genre across sources with cached database fallback/merge."""
    profile = get_profile_by_id(profile_id)
    live_items = await source_manager.get_by_genre(genre, media_type=type, source_filter=source, page=page)
    if page == 1:
        db_items = await db.get_titles_by_genre(genre, media_type=type, limit=30)
        if type == "tv":
            merged = CatalogMerger.merge_tv_lists(live_items, db_items)
        else:
            merged = CatalogMerger.merge_movie_lists(live_items, db_items)
    else:
        merged = live_items

    await db.enrich_items_with_cached_metadata(merged)
    filtered = [item for item in merged if is_title_allowed_for_profile(item, profile)]
    results = [item.to_dict() for item in filtered]
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()
    for r in results:
        r["streaming_availability"] = extract_streaming_availability(r, active_country)
    from_idx = (page - 1) * 30 + 1 if results else 0
    to_idx = from_idx + len(results) - 1 if results else 0

    return {
        "genre": genre,
        "page": page,
        "source": source,
        "profile_id": profile.id,
        "count": len(results),
        "from": from_idx,
        "to": to_idx,
        "results": results,
    }


@app.get("/api/catalog/title/{media_type}/{title_id}")
async def get_title_details(
    media_type: str,
    title_id: str,
    profile_id: str = Query("default"),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """Fetch complete details, enriched metadata, and sources for a title with SQLite caching and dynamic TTL."""
    profile = get_profile_by_id(profile_id)
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()
    # Always use the primary global generic TMDb API key for all profiles
    tmdb_key = CONFIG.get("tmdb_api_key") or metadata_enricher.tmdb_api_key

    # Check SQLite cache record
    cached_rec = await db.get_title_record(title_id)
    cached = cached_rec["data"] if cached_rec else None

    # Return cached data if fresh and refresh is not forced
    if cached and not refresh and cached_rec["age_seconds"] <= CACHE_TTL_ON_DEMAND_SECONDS:
        if not is_title_allowed_for_profile(cached, profile):
            raise HTTPException(
                status_code=403, detail="Contenuto non disponibile per il profilo selezionato (restrizione d'età)."
            )
        # Check if TMDb key is configured but cached item is missing watch_providers
        has_wp = bool(cached.get("watch_providers"))
        if not tmdb_key or has_wp:
            cached["is_favorite"] = await db.is_favorite(title_id, profile_id=profile.id)
            cached["streaming_availability"] = extract_streaming_availability(cached, active_country)
            cached["age_seconds"] = cached_rec["age_seconds"]
            cached["updated_at"] = cached_rec["updated_at"]
            return cached

    try:
        item = await source_manager.get_details(media_type, title_id)
    except Exception as err:
        _LOGGER.error("Error fetching title %s: %s", title_id, err)
        if cached:
            cached["is_favorite"] = await db.is_favorite(title_id, profile_id=profile.id)
            cached["streaming_availability"] = extract_streaming_availability(cached, active_country)
            cached["age_seconds"] = cached_rec["age_seconds"] if cached_rec else 0
            cached["updated_at"] = cached_rec["updated_at"] if cached_rec else ""
            return cached
        raise HTTPException(status_code=404, detail=f"Titolo non trovato: {err}")

    # Enrich with TMDb or Cinemeta using profile's personal TMDb key if configured
    if isinstance(item, Movie):
        await metadata_enricher.enrich_movie(item, api_key=tmdb_key)
    elif isinstance(item, TvSeries):
        await metadata_enricher.enrich_tv_series(item, api_key=tmdb_key)
        # Cache any pre-loaded seasons/episodes
        for s in item.seasons:
            if s.episodes:
                await db.save_season(item.id, s)

    # Persist in SQLite
    await db.save_title(item)

    if not is_title_allowed_for_profile(item, profile):
        raise HTTPException(
            status_code=403, detail="Contenuto non disponibile per il profilo selezionato (restrizione d'età)."
        )

    data = item.to_dict()
    data["is_favorite"] = await db.is_favorite(title_id, profile_id=profile.id)
    data["streaming_availability"] = extract_streaming_availability(data, active_country)
    data["age_seconds"] = 0
    data["updated_at"] = datetime.now(UTC).isoformat()
    return data


class BatchAvailabilityItem(BaseModel):
    id: str
    media_type: str = "movie"
    title: str
    year: int | None = None


class BatchAvailabilityRequest(BaseModel):
    profile_id: str = "default"
    items: list[BatchAvailabilityItem] = Field(default_factory=list)


@app.post("/api/catalog/batch-streaming-availability")
async def get_batch_streaming_availability(req: BatchAvailabilityRequest) -> dict[str, Any]:
    """Retrieve streaming availability for multiple visible items, pre-fetching TMDb metadata if missing."""
    profile = get_profile_by_id(req.profile_id)
    active_country = (getattr(profile, "country", None) or CONFIG.get("country", "IT")).upper()
    tmdb_key = CONFIG.get("tmdb_api_key") or metadata_enricher.tmdb_api_key

    if not req.items:
        return {"results": {}}

    ids = [item.id for item in req.items]
    cached_wp = await db.get_titles_watch_providers(ids)

    missing_items = [item for item in req.items if item.id not in cached_wp]

    if missing_items and tmdb_key:
        sem = asyncio.Semaphore(5)

        async def _enrich_item(it: BatchAvailabilityItem) -> None:
            async with sem:
                try:
                    if it.media_type == "tv":
                        series = TvSeries(id=it.id, title=it.title, year=it.year)
                        await metadata_enricher.enrich_tv_series(series, api_key=tmdb_key)
                        if series.watch_providers:
                            cached_wp[it.id] = series.watch_providers
                            await db.update_title_watch_providers(
                                it.id,
                                series.watch_providers,
                                media_type="tv",
                                title=it.title,
                                year=it.year,
                                tmdb_id=series.tmdb_id,
                                rating=series.rating,
                                certification=series.certification,
                            )
                    else:
                        movie = Movie(id=it.id, title=it.title, year=it.year)
                        await metadata_enricher.enrich_movie(movie, api_key=tmdb_key)
                        if movie.watch_providers:
                            cached_wp[it.id] = movie.watch_providers
                            await db.update_title_watch_providers(
                                it.id,
                                movie.watch_providers,
                                media_type="movie",
                                title=it.title,
                                year=it.year,
                                tmdb_id=movie.tmdb_id,
                                rating=movie.rating,
                                certification=movie.certification,
                            )
                except Exception as err:
                    _LOGGER.debug("Batch enrich TMDb failed for %s: %s", it.title, err)

        await asyncio.gather(*[_enrich_item(it) for it in missing_items], return_exceptions=True)

    results: dict[str, Any] = {}
    for item in req.items:
        wp = cached_wp.get(item.id, {})
        results[item.id] = extract_streaming_availability({"watch_providers": wp}, active_country)

    return {"results": results}


@app.get("/api/catalog/seasons/{series_id}/{season_number}")
async def get_season_episodes(
    series_id: str,
    season_number: int,
    profile_id: str = Query("default"),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """Retrieve episodes for a specific TV series season with SQLite caching and dynamic TTL."""
    _ = get_profile_by_id(profile_id)
    cached_rec = await db.get_season_record(series_id, season_number)

    if cached_rec and not refresh and cached_rec["age_seconds"] <= CACHE_TTL_ON_DEMAND_SECONDS:
        res = cached_rec["season"].to_dict()
        res["age_seconds"] = cached_rec["age_seconds"]
        res["updated_at"] = cached_rec["updated_at"]
        return res

    try:
        season = await source_manager.get_season(series_id, season_number)
        if season and season.episodes:
            # Enrich season episodes with TMDb if tmdb_id is available
            title_data = await db.get_title(series_id)
            tmdb_id = title_data.get("tmdb_id") if title_data else None
            if tmdb_id:
                await metadata_enricher.enrich_tv_season(tmdb_id, season)
            await db.save_season(series_id, season)
        res = season.to_dict()
        res["age_seconds"] = 0
        res["updated_at"] = datetime.now(UTC).isoformat()
        return res
    except Exception as err:
        _LOGGER.error("Error fetching season %s for %s: %s", season_number, series_id, err)
        if cached_rec:
            _LOGGER.warning("Falling back to cached season %s for %s", season_number, series_id)
            res = cached_rec["season"].to_dict()
            res["age_seconds"] = cached_rec["age_seconds"]
            res["updated_at"] = cached_rec["updated_at"]
            return res
        raise HTTPException(status_code=404, detail=f"Stagione non trovata: {err}")


@app.post("/api/history")
async def save_progress(req: ProgressRequest) -> dict[str, Any]:
    """Save or update video watch progress in SQLite database scoped by profile."""
    await db.save_watch_progress(
        media_id=req.media_id,
        title=req.title,
        media_type=req.media_type,
        poster_url=req.poster_url,
        season_number=req.season_number,
        episode_number=req.episode_number,
        progress_seconds=req.progress_seconds,
        duration_seconds=req.duration_seconds,
        profile_id=req.profile_id,
    )

    # If Trakt is connected for profile, scrobble progress
    profile = get_profile_by_id(req.profile_id)
    trakt = get_profile_trakt_client(profile)
    if trakt and trakt.is_authenticated and req.duration_seconds > 0:
        percent = (req.progress_seconds / req.duration_seconds) * 100
        action = "stop" if percent >= 80 else "pause"
        asyncio.create_task(
            trakt.scrobble_action(
                action=action,
                media_type=req.media_type,
                title=req.title,
                year=req.year,
                tmdb_id=req.tmdb_id,
                imdb_id=req.imdb_id,
                season_number=req.season_number,
                episode_number=req.episode_number,
                progress_percent=percent,
            )
        )

    return {"status": "ok"}


@app.get("/api/history")
async def get_history(
    limit: int = Query(30, ge=1, le=100),
    profile_id: str = Query("default"),
) -> list[dict[str, Any]]:
    """Retrieve user watch history from SQLite database for active profile."""
    return await db.get_watch_history(profile_id=profile_id, limit=limit)


@app.get("/api/history/continue")
async def get_continue_watching(
    limit: int = Query(20, ge=1, le=50),
    profile_id: str = Query("default"),
) -> list[dict[str, Any]]:
    """Retrieve curated continue watching list for active profile."""
    return await db.get_continue_watching(profile_id=profile_id, limit=limit)


@app.get("/api/history/watched")
async def get_watched_list(
    limit: int = Query(30, ge=1, le=100),
    profile_id: str = Query("default"),
) -> list[dict[str, Any]]:
    """Retrieve watched / completed titles for active profile."""
    return await db.get_watched_history(profile_id=profile_id, limit=limit)


@app.delete("/api/history/{media_id}")
async def delete_history_item(
    media_id: str,
    profile_id: str = Query("default"),
) -> dict[str, Any]:
    """Remove a media title from watch history for active profile."""
    await db.delete_watch_history(media_id, profile_id=profile_id)
    return {"status": "ok", "deleted": media_id}


@app.get("/api/history/progress/{media_id}")
async def get_media_progress(
    media_id: str,
    profile_id: str = Query("default"),
    season: int | None = Query(None),
    episode: int | None = Query(None),
) -> dict[str, Any]:
    """Get latest watch progress for a title and active profile, optionally filtered by season and episode."""
    progress = await db.get_media_progress(
        media_id,
        profile_id=profile_id,
        season_number=season,
        episode_number=episode,
    )
    return {"status": "ok", "progress": progress}


@app.post("/api/favorites/toggle")
async def toggle_favorite(req: FavoriteRequest) -> dict[str, Any]:
    """Toggle a title as user favorite in SQLite database for active profile."""
    is_fav = await db.toggle_favorite(
        title_id=req.title_id,
        media_type=req.media_type,
        title=req.title,
        poster_url=req.poster_url,
        profile_id=req.profile_id,
    )

    # Sync to Trakt watchlist if authenticated
    profile = get_profile_by_id(req.profile_id)
    trakt = get_profile_trakt_client(profile)
    if trakt and trakt.is_authenticated:
        asyncio.create_task(
            trakt.sync_favorite(
                media_type=req.media_type,
                title=req.title,
                tmdb_id=req.tmdb_id,
                imdb_id=req.imdb_id,
                is_favorite=is_fav,
            )
        )

    return {"status": "ok", "favorite": is_fav}


@app.get("/api/favorites")
async def get_favorites(profile_id: str = Query("default")) -> list[dict[str, Any]]:
    """Retrieve all user favorites from SQLite database for active profile."""
    return await db.get_favorites(profile_id=profile_id)


@app.post("/api/resolve")
async def resolve_media_source(req: ResolveRequest, request: Request) -> dict[str, Any]:
    """Resolve a streaming source to a proxied HLS playback URL with failover."""
    source = ProviderSource(
        id=f"req_{secrets_token()}",
        media_id=req.media_id or "media",
        provider_id=req.provider_id or "source",
        provider_name=req.provider_id or "Provider",
        page_url=req.page_url,
        quality=req.quality,
    )

    alternate_sources: list[ProviderSource] = []
    if req.media_id:
        try:
            cached_title = await db.get_title(req.media_id)
            if cached_title and cached_title.get("sources"):
                alternate_sources.extend(
                    ProviderSource.from_dict(s)
                    for s in cached_title["sources"]
                    if s.get("page_url") != req.page_url and s.get("available", True)
                )
        except Exception:
            pass

    try:
        resolved = await source_manager.resolve_stream_with_fallback(
            source,
            alternate_sources=alternate_sources,
            prefer_fhd=req.prefer_fhd,
        )
    except Exception as err:
        _LOGGER.error("Failed to resolve source %s: %s", req.page_url, err)
        raise HTTPException(status_code=400, detail=f"Risoluzione stream fallita: {err}")

    token = stream_proxy.register_stream(resolved)
    ingress_path = get_ingress_path(request)
    ha_host = await ha_client.get_host_ip_or_url()
    stream_port = CONFIG.get("stream_port", 8099)

    # Local player URL (through Ingress if available, else relative)
    local_stream_url = f"{ingress_path}/stream/{token}" if ingress_path else f"/stream/{token}"

    # LAN Cast URL (direct host IP without Ingress session authentication)
    lan_stream_url = f"http://{ha_host}:{stream_port}/stream/{token}"

    return {
        "token": token,
        "mime_type": resolved.mime_type,
        "stream_format": resolved.stream_format,
        "local_stream_url": local_stream_url,
        "lan_stream_url": lan_stream_url,
        "headers": resolved.headers,
        "subtitles": [s.to_dict() for s in resolved.subtitles],
    }


@app.post("/api/cast")
async def cast_to_device(req: CastRequest) -> dict[str, Any]:
    """Resolve stream and cast directly to Home Assistant media_player device."""
    source = ProviderSource(
        id=f"cast_{secrets_token()}",
        media_id=req.media_id or "media",
        provider_id=req.provider_id or "source",
        provider_name=req.provider_id or "Provider",
        page_url=req.page_url,
        quality=req.quality,
    )

    alternate_sources: list[ProviderSource] = []
    if req.media_id:
        try:
            cached_title = await db.get_title(req.media_id)
            if cached_title and cached_title.get("sources"):
                alternate_sources.extend(
                    ProviderSource.from_dict(s)
                    for s in cached_title["sources"]
                    if s.get("page_url") != req.page_url and s.get("available", True)
                )
        except Exception:
            pass

    try:
        resolved = await source_manager.resolve_stream_with_fallback(
            source,
            alternate_sources=alternate_sources,
            prefer_fhd=True,
        )
    except Exception as err:
        _LOGGER.error("Failed to resolve stream for casting: %s", err)
        raise HTTPException(status_code=400, detail=f"Risoluzione stream fallita: {err}")

    token = stream_proxy.register_stream(resolved)
    ha_host = await ha_client.get_host_ip_or_url()
    stream_port = CONFIG.get("stream_port", 8099)

    lan_stream_url = f"http://{ha_host}:{stream_port}/stream/{token}"
    _LOGGER.info("Sending Cast command to %s with stream: %s", req.entity_id, lan_stream_url)

    subtitles_list = [s.to_dict() for s in resolved.subtitles] if resolved.subtitles else None

    success, actual_entity = await ha_client.play_on_device(
        entity_id=req.entity_id,
        media_url=lan_stream_url,
        title=req.title,
        poster_url=req.poster_url,
        mime_type=resolved.mime_type or "application/vnd.apple.mpegurl",
        subtitles=subtitles_list,
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Home Assistant non è riuscito ad avviare la riproduzione su {req.entity_id}",
        )

    # Fire Home Assistant Core event for smart home automations
    asyncio.create_task(
        ha_client.fire_ha_event(
            "streaming_hub_playback_started",
            {
                "title": req.title,
                "media_type": req.media_type,
                "entity_id": actual_entity,
                "profile_id": req.profile_id,
                "season_number": req.season_number,
                "episode_number": req.episode_number,
            },
        )
    )

    # Start active tracker to sync watch progress from Home Assistant Cast entity
    cast_profile = get_profile_by_id(req.profile_id)
    cast_trakt = get_profile_trakt_client(cast_profile)

    ha_client.start_cast_tracker(
        entity_id=actual_entity,
        media_id=req.media_id or "media",
        title=req.title,
        media_type=req.media_type,
        poster_url=req.poster_url,
        season_number=req.season_number,
        episode_number=req.episode_number,
        db=db,
        seek_position=req.seek_seconds,
        profile_id=req.profile_id,
        trakt_client=cast_trakt,
        year=req.year,
        tmdb_id=req.tmdb_id,
        imdb_id=req.imdb_id,
    )

    return {
        "success": True,
        "entity_id": actual_entity,
        "stream_url": lan_stream_url,
        "token": token,
    }


@app.get("/api/catalog/next-episode/{series_id}/{season_number}/{episode_number}")
async def get_next_episode_endpoint(
    series_id: str,
    season_number: int,
    episode_number: int,
) -> dict[str, Any]:
    """Retrieve the next sequential episode for binge-watching with automatic season fetching."""
    next_ep = await db.get_next_episode(series_id, season_number, episode_number)

    # 1. Fallback: if not in db, try to fetch current season from source_manager
    if not next_ep:
        try:
            curr_season = await source_manager.get_season(series_id, season_number)
            if curr_season and curr_season.episodes:
                title_data = await db.get_title(series_id)
                tmdb_id = title_data.get("tmdb_id") if title_data else None
                if tmdb_id:
                    await metadata_enricher.enrich_tv_season(tmdb_id, curr_season)
                await db.save_season(series_id, curr_season)
                next_ep = await db.get_next_episode(series_id, season_number, episode_number)
        except Exception as err:
            _LOGGER.debug("Could not fallback fetch season %s: %s", season_number, err)

    # 2. Fallback: if still not found and this might be the end of season, fetch season_number + 1
    if not next_ep:
        try:
            next_season = await source_manager.get_season(series_id, season_number + 1)
            if next_season and next_season.episodes:
                title_data = await db.get_title(series_id)
                tmdb_id = title_data.get("tmdb_id") if title_data else None
                if tmdb_id:
                    await metadata_enricher.enrich_tv_season(tmdb_id, next_season)
                await db.save_season(series_id, next_season)
                next_ep = await db.get_next_episode(series_id, season_number, episode_number)
        except Exception as err:
            _LOGGER.debug("Could not fallback fetch next season %s: %s", season_number + 1, err)

    # 3. Ensure next episode has sources populated
    if next_ep and next_ep.get("episode"):
        ep_dict = next_ep["episode"]
        if not ep_dict.get("sources"):
            target_season_num = next_ep["season_number"]
            try:
                target_season = await source_manager.get_season(series_id, target_season_num)
                if target_season and target_season.episodes:
                    await db.save_season(series_id, target_season)
                    refreshed = await db.get_next_episode(series_id, season_number, episode_number)
                    if refreshed:
                        next_ep = refreshed
            except Exception:
                pass

    return {"has_next": bool(next_ep), "next": next_ep}


@app.get("/api/catalog/skip-segments/{series_id}/{season_number}/{episode_number}")
async def get_skip_segments_endpoint(
    series_id: str,
    season_number: int,
    episode_number: int,
    duration: float | None = Query(None),
) -> dict[str, Any]:
    """Retrieve intro and outro skip markers from SkipDB with local fallback."""
    title_data = await db.get_title(series_id)
    imdb_id = title_data.get("imdb_id") if title_data else None

    if not imdb_id and title_data:
        # Try resolving via Cinemeta if missing
        title_name = title_data.get("title", "")
        if title_name:
            clean_id = await metadata_enricher._search_cinemeta_imdb_id("series", title_name)
            if clean_id:
                imdb_id = clean_id
                title_data["imdb_id"] = clean_id
                with contextlib.suppress(Exception):
                    await db.save_title(TvSeries.from_dict(title_data))

    return await skip_segments_manager.get_skip_segments(
        imdb_id=imdb_id,
        season_number=season_number,
        episode_number=episode_number,
        duration=duration,
    )


@app.get("/api/subtitles/search")
async def search_subtitles_endpoint(
    imdb_id: str | None = None,
    tmdb_id: int | None = None,
    query: str | None = None,
    season: int | None = None,
    episode: int | None = None,
) -> list[dict[str, Any]]:
    """Search available subtitle tracks from OpenSubtitles with fail-open fallback."""
    tracks = await subtitle_manager.search_subtitles(
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        query=query,
        season_number=season,
        episode_number=episode,
    )
    return [t.to_dict() for t in tracks]


@app.get("/api/subtitles/{sub_id}")
async def get_subtitle_file_endpoint(sub_id: str) -> Response:
    """Serve converted WebVTT subtitle file with CORS headers."""
    vtt = subtitle_manager.get_vtt(sub_id)
    if not vtt:
        raise HTTPException(status_code=404, detail="Traccia sottotitoli non trovata")
    return Response(
        content=vtt,
        media_type="text/vtt; charset=utf-8",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )


class CastControlRequest(BaseModel):
    entity_id: str
    command: str
    value: float | None = None


@app.get("/api/cast/status")
async def get_cast_status(entity_id: str | None = None) -> dict[str, Any]:
    """Get active cast playback status and progress."""
    return await ha_client.get_cast_status(entity_id)


@app.post("/api/cast/control")
async def control_cast(req: CastControlRequest) -> dict[str, Any]:
    """Control cast playback (play, pause, stop, seek, volume)."""
    success = await ha_client.control_cast(req.entity_id, req.command, req.value)
    if success and req.command.lower() in ("play", "pause", "stop"):
        asyncio.create_task(
            ha_client.fire_ha_event(
                f"streaming_hub_playback_{req.command.lower()}",
                {"entity_id": req.entity_id},
            )
        )
    return {"success": success}


# Proxy stream endpoints


@app.get("/api/proxy/image")
async def proxy_image(url: str = Query(..., description="Image URL to proxy")) -> Response:
    """Proxy image requests to bypass CORS and referer blocks."""
    if not url or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        parsed = urlparse(url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }

        session = await stream_proxy._get_client_session()
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail="Image not found or blocked")

            content = await resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )
    except HTTPException:
        raise
    except Exception as err:
        _LOGGER.error("Image proxy error for %s: %s", url, err)
        raise HTTPException(status_code=502, detail="Failed to fetch image") from err


@app.api_route("/stream/{token}", methods=["GET", "HEAD"])
async def get_stream(token: str, request: Request, url: str | None = None) -> Response:
    """Stream or sub-playlist proxy supporting GET and HEAD."""
    ingress_path = get_ingress_path(request)
    headers_dict = dict(request.headers)
    return await stream_proxy.get_stream_response(
        token=token,
        target_url=url,
        root_path=ingress_path,
        headers_override=headers_dict,
        method=request.method,
    )


@app.api_route("/segment/{token}", methods=["GET", "HEAD"])
async def get_segment(token: str, request: Request, url: str = Query(...)) -> Response:
    """HLS segment proxy forwarding injected headers supporting GET and HEAD."""
    ingress_path = get_ingress_path(request)
    headers_dict = dict(request.headers)
    return await stream_proxy.get_segment_response(
        token=token,
        segment_url=url,
        headers_override=headers_dict,
        root_path=ingress_path,
        method=request.method,
    )


def secrets_token() -> str:
    """Generate a quick unique token ID."""
    import secrets

    return secrets.token_hex(4)


# Frontend static files & SPA fallback
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        """Serve SPA index.html."""
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        """Fallback to index.html or requested static file."""
        target = FRONTEND_DIR / full_path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(FRONTEND_DIR / "index.html"))


def run():
    """Run uvicorn server."""
    port = CONFIG.get("stream_port", 8099)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run()
