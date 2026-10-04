"""Anime streaming engine client for specialized anime catalogs."""

from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

import aiohttp

from .dns_resolver import DoHResolver
from .engine_reactive import USER_AGENT, ReactiveStreamClient
from .models import Movie, ProviderSource, TvEpisode, TvSeason, TvSeries

_LOGGER = logging.getLogger(__name__)

# Heuristic patterns for anime titles and classification
_DUB_MARKERS = ("(ita)", "[ita]", " ita", "ita doppiato", "doppiato")
_SUB_MARKERS = ("(sub ita)", "[sub ita]", " sub", "sub-ita", "sub ita")


class AnimeStreamClient:
    """Async client for interacting with anime streaming platforms.

    Supports:
    - Fast catalog searching via HTML attributes and AJAX JSON
    - Episode listing via open chunked info APIs
    - Direct VixCloud embed extraction and HLS stream resolution
    - Dual SUB ITA and ITA dubbed categorization
    """

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession | None = None,
        custom_dns: str = "cloudflare",
        timeout: int = 15,
    ) -> None:
        """Initialize anime streaming client."""
        self.base_url = (base_url or "").rstrip("/")
        self._custom_session = session is not None
        self._session = session
        self._custom_dns = custom_dns
        self._timeout = timeout
        self._resolver: DoHResolver | None = None
        self._csrf_token: str | None = None
        self._reactive_client = ReactiveStreamClient(
            base_url=self.base_url,
            session=self._session,
            custom_dns=custom_dns,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or initialize the aiohttp client session."""
        if self._session is None or self._session.closed:
            connector = None
            if self._custom_dns and self._custom_dns != "system":
                self._resolver = DoHResolver(provider=self._custom_dns)
                connector = aiohttp.TCPConnector(resolver=self._resolver)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            )
            self._reactive_client._session = self._session
        return self._session

    async def _request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> str:
        """Execute HTTP request with realistic desktop browser headers."""
        session = await self._get_session()
        req_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if headers:
            req_headers.update(headers)

        full_url = url if url.startswith("http") else urljoin(self.base_url + "/", url.lstrip("/"))
        try:
            if method.upper() == "POST":
                async with session.post(full_url, headers=req_headers, json=json_data) as resp:
                    text = await resp.text(errors="ignore")
                    self._extract_csrf(text)
                    return text
            else:
                async with session.get(full_url, headers=req_headers) as resp:
                    text = await resp.text(errors="ignore")
                    self._extract_csrf(text)
                    return text
        except Exception as err:
            _LOGGER.debug("HTTP %s to %s failed: %s", method, full_url, err)
            raise

    def _extract_csrf(self, html_text: str) -> None:
        """Extract CSRF token from page meta tag if present."""
        if not html_text:
            return
        match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html_text)
        if match:
            self._csrf_token = match.group(1)

    def _clean_title(self, raw_title: str) -> tuple[str, int | None, str]:
        """Extract clean title, release year, and dub type ('sub' or 'dub')."""
        title = raw_title.strip()
        dub_type = "sub"

        # Check for SUB markers before DUB markers to avoid matching ' ita' inside 'sub ita'
        lower = title.lower()
        if any(marker in lower for marker in _SUB_MARKERS):
            dub_type = "sub"
        elif any(marker in lower for marker in _DUB_MARKERS):
            dub_type = "dub"

        # Extract year if in parentheses e.g. "Ranma ½ (2024)"
        year = None
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", title)
        if year_match:
            with contextlib.suppress(ValueError):
                year = int(year_match.group(1))

        # Clean extraneous trailing tags
        clean = re.sub(r"\s*[\(\[]?(?:ita|sub[- ]?ita)[\)\]]?", "", title, flags=re.IGNORECASE).strip()
        clean = re.sub(r"\s*[\(\[]?(?:19\d{2}|20\d{2})[\)\]]?", "", clean).strip()

        return clean or title, year, dub_type

    def _record_to_media(self, rec: dict[str, Any]) -> Movie | TvSeries:
        """Transform raw catalog JSON record into unified Movie or TvSeries model."""
        raw_id = str(rec.get("id") or "")
        slug = str(rec.get("slug") or "")
        media_id = f"anime-{raw_id}-{slug}" if slug else f"anime-{raw_id}"

        raw_title = str(rec.get("title_it") or rec.get("title_eng") or rec.get("title") or "Anime")
        clean_title, parsed_year, dub_marker = self._clean_title(raw_title)

        is_dub = int(rec.get("dub") or 0) == 1 or dub_marker == "dub"
        dub_type = "dub" if is_dub else "sub"
        display_title = f"{clean_title} (ITA)" if is_dub else clean_title

        year = parsed_year
        if not year and rec.get("date"):
            with contextlib.suppress(ValueError):
                year = int(str(rec["date"])[:4])

        rating = None
        if rec.get("score"):
            with contextlib.suppress(ValueError):
                rating = round(float(rec["score"]), 1)

        poster_url = rec.get("imageurl") or rec.get("imageurl_cover")
        backdrop_url = rec.get("imageurl_cover") or rec.get("imageurl")
        description = rec.get("plot")

        genres = ["Animazione", "Anime"]
        raw_genres = rec.get("genres")
        if isinstance(raw_genres, list):
            for g in raw_genres:
                g_name = g.get("name") if isinstance(g, dict) else str(g)
                if g_name and g_name not in genres:
                    genres.append(g_name)

        media_type = str(rec.get("type") or "TV").upper()
        if media_type in ("MOVIE", "FILM"):
            movie = Movie(
                id=media_id,
                title=display_title,
                original_title=str(rec.get("title") or ""),
                year=year,
                poster_url=poster_url,
                backdrop_url=backdrop_url,
                description=description,
                genres=genres,
                rating=rating,
                is_adult=False,
                catalogs=["anime"],
            )
            movie.is_anime = True
            movie.dub_type = dub_type
            return movie

        series = TvSeries(
            id=media_id,
            title=display_title,
            original_title=str(rec.get("title") or ""),
            year=year,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            description=description,
            genres=genres,
            rating=rating,
            is_adult=False,
            catalogs=["anime"],
        )
        series.is_anime = True
        series.dub_type = dub_type
        return series

    def _extract_embedded_records(self, html_text: str, tag_name: str = "archivio") -> list[dict[str, Any]]:
        """Extract JSON serialized array from HTML component attributes."""
        if not html_text:
            return []

        # 1. Match <tag-name records="[...]">
        patterns = [
            rf'<{tag_name}[^>]*\srecords=["\'](.*?)["\']',
            rf'<{tag_name}[^>]*\sitems-json=["\'](.*?)["\']',
            r'<layout-items[^>]*\sitems-json=["\'](.*?)["\']',
        ]
        for pat in patterns:
            match = re.search(pat, html_text, re.DOTALL)
            if match:
                raw_json = html.unescape(match.group(1))
                try:
                    data = json.loads(raw_json)
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict) and "records" in data:
                        return data["records"]
                except Exception as err:
                    _LOGGER.debug("Failed parsing embedded JSON from %s: %s", tag_name, err)

        return []

    async def search(self, query: str) -> list[Movie | TvSeries]:
        """Search titles by keyword."""
        clean_q = query.strip()
        if not clean_q or not self.base_url:
            return []

        # Strategy 1: GET /archivio?title={query} (Pure GET, no CSRF/session needed)
        try:
            search_url = f"{self.base_url}/archivio?title={quote_plus(clean_q)}"
            html_text = await self._request(search_url)
            records = self._extract_embedded_records(html_text, tag_name="archivio")
            if records:
                return [self._record_to_media(r) for r in records if isinstance(r, dict)]
        except Exception as err:
            _LOGGER.debug("GET search for '%s' failed: %s", clean_q, err)

        # Strategy 2: POST /livesearch fallback
        try:
            headers = {"X-Requested-With": "XMLHttpRequest"}
            if self._csrf_token:
                headers["X-CSRF-TOKEN"] = self._csrf_token
            res_text = await self._request(
                f"{self.base_url}/livesearch",
                method="POST",
                headers=headers,
                json_data={"title": clean_q},
            )
            data = json.loads(res_text)
            records = data.get("records", [])
            return [self._record_to_media(r) for r in records if isinstance(r, dict)]
        except Exception as err:
            _LOGGER.debug("POST livesearch for '%s' failed: %s", clean_q, err)

        return []

    async def get_latest_releases(self, page: int = 1) -> list[Movie | TvSeries]:
        """Fetch latest releases from the catalog."""
        if not self.base_url:
            return []

        offset = max(0, (page - 1) * 30)
        url = f"{self.base_url}/archivio?offset={offset}" if offset > 0 else f"{self.base_url}/archivio"

        try:
            html_text = await self._request(url)
            records = self._extract_embedded_records(html_text, tag_name="archivio")
            if not records and page == 1:
                # Try home layout items
                records = self._extract_embedded_records(html_text, tag_name="layout-items")
            return [self._record_to_media(r) for r in records if isinstance(r, dict)]
        except Exception as err:
            _LOGGER.warning("Failed fetching latest anime releases (page %d): %s", page, err)
            return []

    async def get_anime_details(self, anime_id: str | int, slug: str = "") -> Movie | TvSeries:
        """Fetch full details for an anime title and its initial episodes."""
        clean_id = str(anime_id).replace("anime-", "")
        if not slug and "-" in clean_id:
            parts = clean_id.split("-", 1)
            numeric_id = parts[0]
            slug = parts[1]
        elif "-" in clean_id:
            numeric_id = clean_id.split("-")[0]
        else:
            numeric_id = clean_id

        detail_url = f"{self.base_url}/anime/{numeric_id}-{slug}" if slug else f"{self.base_url}/anime/{numeric_id}"
        html_text = await self._request(detail_url)

        # 1. Extract anime prop from <video-player anime="..." ...>
        player_match = re.search(r'<video-player[^>]*\sanime=["\'](.*?)["\']', html_text, re.DOTALL)
        anime_data: dict[str, Any] = {}
        if player_match:
            try:
                anime_data = json.loads(html.unescape(player_match.group(1)))
            except Exception as err:
                _LOGGER.debug("Failed parsing video-player anime prop: %s", err)

        if not anime_data:
            # Fallback: search for title by ID
            matches = await self.search(slug or numeric_id)
            for m in matches:
                if str(numeric_id) in m.id:
                    return m
            raise ValueError(f"Could not load anime details for {anime_id}")

        media = self._record_to_media(anime_data)

        # If it's a TV series, fetch episodes for season 1
        if isinstance(media, TvSeries):
            ep_count = int(anime_data.get("episodes_count") or 0)
            season = await self.get_tv_season(numeric_id, 1, total_count=ep_count)
            media.seasons = [season]

        return media

    async def get_tv_season(
        self,
        anime_id: str | int,
        season_number: int = 1,
        total_count: int | None = None,
    ) -> TvSeason:
        """Fetch all episodes for an anime series via chunked info API."""
        clean_id = str(anime_id).replace("anime-", "").split("-")[0]
        season = TvSeason(number=season_number, episodes=[])

        # Step 1: Probe first range to get total count if unknown
        probe_url = f"{self.base_url}/info_api/{clean_id}/1?start_range=1&end_range=120"
        try:
            probe_text = await self._request(probe_url)
            probe_data = json.loads(probe_text)
        except Exception as err:
            _LOGGER.debug("Initial episode probe failed for anime %s: %s", clean_id, err)
            return season

        ep_count = total_count or int(probe_data.get("episodes_count") or 0)
        raw_episodes: list[dict[str, Any]] = probe_data.get("episodes", [])

        # Step 2: Fetch subsequent batches if total exceeds 120
        if ep_count > 120:
            tasks = []
            for start in range(121, ep_count + 1, 120):
                end = min(start + 119, ep_count)
                batch_url = f"{self.base_url}/info_api/{clean_id}/1?start_range={start}&end_range={end}"
                tasks.append(self._request(batch_url))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in batch_results:
                if isinstance(res, str):
                    with contextlib.suppress(Exception):
                        b_data = json.loads(res)
                        raw_episodes.extend(b_data.get("episodes", []))

        # Sort episodes by episode number
        def _get_ep_num(e: dict[str, Any]) -> int:
            with contextlib.suppress(ValueError):
                return int(str(e.get("number", "0")))
            return 0

        raw_episodes.sort(key=_get_ep_num)

        for ep in raw_episodes:
            if not isinstance(ep, dict):
                continue
            ep_id = str(ep.get("id") or "")
            ep_num = _get_ep_num(ep) or 1
            embed_api_url = f"{self.base_url}/embed-url/{ep_id}"

            source = ProviderSource(
                id=f"anime-{clean_id}-{ep_id}",
                media_id=f"anime-{clean_id}",
                provider_id="anime",
                provider_name="Anime HLS",
                page_url=embed_api_url,
                language="ita",
                quality="FHD",
                available=True,
            )

            episode = TvEpisode(
                id=f"anime-{clean_id}-e{ep_num}",
                media_id=f"anime-{clean_id}",
                season_number=season_number,
                episode_number=ep_num,
                title=f"Episodio {ep_num}",
                description=None,
                poster_url=None,
                sources=[source],
            )
            season.episodes.append(episode)

        return season

    async def get_embed_url(self, episode_id_or_url: str) -> str:
        """Fetch signed VixCloud embed URL from embed-url API."""
        if episode_id_or_url.startswith("http") and "vixcloud" in episode_id_or_url:
            return episode_id_or_url

        url = episode_id_or_url
        if not url.startswith("http"):
            url = f"{self.base_url}/embed-url/{episode_id_or_url}"

        text = await self._request(url)
        clean_text = text.strip().strip('"\'')
        if clean_text.startswith("http"):
            return clean_text
        raise ValueError(f"Invalid embed URL returned: {text[:100]}")

    async def resolve_stream(self, watch_or_embed_url: str, prefer_fhd: bool = True) -> tuple[str, dict[str, str]]:
        """Resolve an episode watch URL or embed API URL to playable HLS .m3u8 playlist."""
        target_url = watch_or_embed_url
        if "/embed-url/" in target_url:
            target_url = await self.get_embed_url(target_url)

        # Delegate VixCloud HLS extraction to ReactiveStreamClient
        return await self._reactive_client.resolve_stream(target_url, prefer_fhd=prefer_fhd)

    async def get_homepage_carousels(self) -> tuple[Movie | TvSeries | None, list[dict[str, Any]]]:
        """Fetch homepage anime trending carousels."""
        items = await self.get_latest_releases(page=1)
        if not items:
            return None, []

        hero = items[0] if items else None
        carousel = {
            "id": "anime_latest",
            "title": "Ultime Uscite Anime",
            "count": len(items),
            "items": items,
        }
        return hero, [carousel]

    async def close(self) -> None:
        """Close underlying client session."""
        if not self._custom_session and self._session and not self._session.closed:
            await self._session.close()
        await self._reactive_client.close()
