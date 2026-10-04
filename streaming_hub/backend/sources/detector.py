"""Source Detector: auto-detects and fingerprints streaming engine types from URLs."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Internal heuristic keyword patterns
_REACTIVE_KEYWORDS = ("community", "strcom", "sc-", "vix")
_CRAWLER_KEYWORDS = ("crawler", "film-streaming", "streaming-hd")
_ANIME_KEYWORDS = ("anime", "anim")


class SourceDetector:
    """Detects and fingerprints the streaming engine/provider from a given base URL.

    Supports:
    - Explicit type definition ('reactive', 'crawler', 'anime')
    - URL heuristics (matching known domain or path structure)
    - Active HTTP fingerprinting (probing HTML markup, headers, and SPA tags)
    """

    @classmethod
    def detect_by_heuristic(cls, url: str) -> str | None:
        """Attempt fast heuristic detection based on domain and URL keywords."""
        parsed = urlparse(url)
        domain = (parsed.netloc or parsed.path).lower()

        # Anime engine patterns
        if any(keyword in domain for keyword in _ANIME_KEYWORDS):
            return "anime"

        # Reactive engine patterns
        if any(keyword in domain for keyword in _REACTIVE_KEYWORDS):
            return "reactive"

        # Crawler engine patterns
        if any(keyword in domain for keyword in _CRAWLER_KEYWORDS):
            return "crawler"

        return None

    @classmethod
    async def detect_by_probe(cls, url: str, session: aiohttp.ClientSession | None = None) -> str | None:
        """Actively probe the URL via HTTP GET and inspect response HTML and headers.

        Allows detecting arbitrary or new mirrors whose domain names don't match heuristics.
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True

        clean_url = url.rstrip("/")

        try:
            async with session.get(
                clean_url,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Probe to %s returned HTTP %s", clean_url, resp.status)
                    return None

                # Check headers for reactive SPA marker
                if "x-inertia" in resp.headers:
                    return "reactive"

                html = await resp.text(errors="ignore")

                # Check for reactive SPA markers (app root, props, or API scripts)
                if 'id="app"' in html and 'data-page="' in html:
                    return "reactive"
                if "window.props" in html or "inertia" in html.lower():
                    if "streaming" in html.lower() or "vixcloud" in html.lower() or "vixsrc" in html.lower():
                        return "reactive"

                # Check for anime catalog markers
                if (
                    "<archivio" in html
                    or "/info_api/" in html
                    or "video-player anime=" in html
                    or "layout-items" in html
                    or "/archivio/get-animes" in html
                ):
                    return "anime"

                # Check for crawler markers (post cards, video headers, category templates)
                if (
                    "card-video" in html
                    or "sp-head" in html
                    or "/film-streaming/" in html
                    or "/serietv/" in html
                    or "mp-post" in html
                    or "cbtable" in html
                ):
                    return "crawler"

        except Exception as err:
            _LOGGER.debug("HTTP fingerprint probe failed for %s: %s", clean_url, err)
        finally:
            if close_session:
                await session.close()

        return None

    @classmethod
    async def detect(
        cls,
        url: str,
        user_specified_type: str = "auto",
        session: aiohttp.ClientSession | None = None,
    ) -> str:
        """Determine provider type given a URL and optional user override.

        Returns one of: 'reactive', 'crawler', 'anime', or 'unknown'.
        """
        user_type = (user_specified_type or "auto").strip().lower()

        # 1. Explicit user selection (including silent backward compatibility)
        if user_type in ("anime", "anime_engine", "engine_anime", "au"):
            return "anime"
        if user_type in ("reactive", "spa", "engine_alpha", "type_a", "source_alpha", "source_a"):
            return "reactive"
        if user_type in ("crawler", "html", "engine_beta", "type_b", "source_beta", "source_b"):
            return "crawler"

        # 2. Fast domain heuristic
        heuristic = cls.detect_by_heuristic(url)
        if heuristic:
            _LOGGER.info("Detected provider type '%s' for '%s' via heuristic", heuristic, url)
            return heuristic

        # 3. Active HTTP fingerprint probe
        probed = await cls.detect_by_probe(url, session=session)
        if probed:
            _LOGGER.info("Detected provider type '%s' for '%s' via HTTP fingerprinting", probed, url)
            return probed

        _LOGGER.warning("Could not determine provider type for URL '%s'", url)
        return "unknown"
