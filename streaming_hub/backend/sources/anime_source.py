"""Anime catalog and stream source adapter."""

from __future__ import annotations

import logging
from typing import Any

from ..engine_anime import AnimeStreamClient
from ..models import Movie, ProviderSource, ResolvedMedia, TvSeason, TvSeries
from .base import BaseSource

_LOGGER = logging.getLogger(__name__)


class AnimeSource(BaseSource):
    """Source adapter for specialized anime streaming catalogs."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = "cloudflare",
        enabled: bool = True,
        name: str | None = None,
    ) -> None:
        """Initialize anime streaming source."""
        self._enabled = enabled
        self._base_url = (base_url or "").rstrip("/")
        self._name = name or "Sorgente Anime"
        self._client = (
            AnimeStreamClient(base_url=self._base_url, custom_dns=custom_dns)
            if enabled and self._base_url
            else None
        )

    @property
    def source_id(self) -> str:
        """Unique machine identifier for this source."""
        return "anime"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self._name

    @property
    def icon(self) -> str:
        """Icon identifier for UI."""
        return "mdi:animation-play"

    @property
    def supported_types(self) -> list[str]:
        """List of media types supported by this source."""
        return ["tv", "movie", "anime"]

    @property
    def is_enabled(self) -> bool:
        """Check if source is enabled."""
        return self._enabled and self._client is not None

    @property
    def has_carousels(self) -> bool:
        """Return True if this source provides homepage carousels."""
        return self.is_enabled

    async def get_carousels(self) -> tuple[Movie | TvSeries | None, list[dict[str, Any]]]:
        """Fetch homepage carousels from the anime client."""
        if not self.is_enabled or not self._client:
            return None, []
        hero_item, carousels = await self._client.get_homepage_carousels()
        if hero_item and self.source_id not in hero_item.catalogs:
            hero_item.catalogs.append(self.source_id)
        for c in carousels:
            for it in c.get("items", []):
                if self.source_id not in it.catalogs:
                    it.catalogs.append(self.source_id)
        return hero_item, carousels

    async def get_latest_movies(self, page: int = 1) -> list[Movie]:
        """Fetch latest anime movies."""
        if not self.is_enabled or not self._client:
            return []
        items = await self._client.get_latest_releases(page=page)
        movies = [m for m in items if isinstance(m, Movie)]
        for m in movies:
            if self.source_id not in m.catalogs:
                m.catalogs.append(self.source_id)
        return movies

    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch latest anime TV series."""
        if not self.is_enabled or not self._client:
            return []
        items = await self._client.get_latest_releases(page=page)
        series = [s for s in items if isinstance(s, TvSeries)]
        for s in series:
            if self.source_id not in s.catalogs:
                s.catalogs.append(self.source_id)
        return series

    async def get_latest_anime(self, page: int = 1, dub_filter: str = "all") -> list[Movie | TvSeries]:
        """Fetch latest anime releases (movies and series) with optional dub filtering."""
        if not self.is_enabled or not self._client:
            return []
        items = await self._client.get_latest_releases(page=page)
        filtered: list[Movie | TvSeries] = []
        for it in items:
            if self.source_id not in it.catalogs:
                it.catalogs.append(self.source_id)
            if dub_filter == "dub_only" and getattr(it, "dub_type", None) != "dub":
                continue
            if dub_filter == "sub_only" and getattr(it, "dub_type", None) != "sub":
                continue
            filtered.append(it)
        return filtered

    async def search(self, query: str, media_type: str = "all") -> list[Movie | TvSeries]:
        """Search titles by keyword."""
        if not self.is_enabled or not self._client:
            return []
        items = await self._client.search(query)
        filtered: list[Movie | TvSeries] = []
        for item in items:
            if self.source_id not in item.catalogs:
                item.catalogs.append(self.source_id)
            if (
                (media_type == "movie" and isinstance(item, Movie))
                or (media_type in ("tv", "series", "anime") and isinstance(item, TvSeries))
                or media_type == "all"
            ):
                filtered.append(item)
        return filtered

    async def get_details(self, media_type: str, item_id: str) -> Movie | TvSeries:
        """Fetch complete details for an anime title."""
        if not self.is_enabled or not self._client:
            raise ValueError("Anime source is disabled")
        item = await self._client.get_anime_details(item_id)
        if self.source_id not in item.catalogs:
            item.catalogs.append(self.source_id)
        return item

    async def get_season(self, series_id: str, season_number: int) -> TvSeason:
        """Fetch season episodes for an anime series."""
        if not self.is_enabled or not self._client:
            raise ValueError("Anime source is disabled")
        clean_id = series_id.replace("anime-", "").split("-")[0]
        return await self._client.get_tv_season(clean_id, season_number=season_number)

    async def resolve_stream(
        self,
        source: ProviderSource,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve an anime source into a playable HLS m3u8 playlist."""
        if not self.is_enabled or not self._client:
            raise ValueError("Anime source is disabled")

        m3u8_url, headers = await self._client.resolve_stream(source.page_url, prefer_fhd=prefer_fhd)
        if not m3u8_url:
            raise ValueError("Could not resolve stream URL for anime source")

        return ResolvedMedia(
            url=m3u8_url,
            mime_type="application/vnd.apple.mpegurl",
            stream_format="hls",
            provider_id=self.source_id,
            headers=headers,
        )

    async def get_genres(self) -> list[str]:
        """Return genres available for anime titles."""
        return [
            "Anime",
            "Animazione",
            "Azione",
            "Avventura",
            "Commedia",
            "Drammatico",
            "Fantasy",
            "Fantascienza",
            "Mistero",
            "Romance",
            "Shounen",
            "Supernatural",
        ]

    async def get_by_genre(
        self,
        genre: str,
        media_type: str = "tv",
        page: int = 1,
    ) -> list[Movie | TvSeries]:
        """Fetch anime titles matching a genre."""
        if not self.is_enabled or not self._client:
            return []
        all_items = await self._client.get_latest_releases(page=page)
        genre_lower = genre.lower()
        matched = [
            it
            for it in all_items
            if any(genre_lower in g.lower() for g in getattr(it, "genres", []))
            or genre_lower in ("anime", "animazione")
        ]
        for it in matched:
            if self.source_id not in it.catalogs:
                it.catalogs.append(self.source_id)
        return matched

    async def close(self) -> None:
        """Close underlying client session."""
        if self._client:
            await self._client.close()
