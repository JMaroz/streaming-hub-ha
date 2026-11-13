"""Reactive catalog and stream source adapter."""

from __future__ import annotations

import logging
from typing import Any

from ..engine_reactive import ReactiveStreamClient
from ..models import Movie, ProviderSource, ResolvedMedia, TvSeason, TvSeries
from .base import BaseSource

_LOGGER = logging.getLogger(__name__)


class ReactiveSource(BaseSource):
    """Source adapter for reactive SPA streaming catalogs."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = "cloudflare",
        enabled: bool = True,
        name: str | None = None,
    ) -> None:
        """Initialize reactive source."""
        self._enabled = enabled
        self._base_url = base_url
        self._name = name or "Sorgente Reattiva"
        self._client = ReactiveStreamClient(base_url=base_url, custom_dns=custom_dns) if enabled and base_url else None

    @property
    def source_id(self) -> str:
        """Source identifier."""
        return "reactive"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self._name

    @property
    def icon(self) -> str:
        """Icon identifier."""
        return "mdi:play-circle-outline"

    @property
    def is_enabled(self) -> bool:
        """Check if source is enabled."""
        return self._enabled and self._client is not None

    @property
    def has_carousels(self) -> bool:
        """Return True if this source provides thematic/editorial homepage carousels."""
        return self.is_enabled

    async def get_carousels(self) -> tuple[Movie | TvSeries | None, list[dict[str, Any]]]:
        """Fetch homepage carousels from the reactive client."""
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
        """Fetch latest movies."""
        if not self.is_enabled:
            return []
        movies = await self._client.get_latest_movies(page=page)
        for m in movies:
            if self.source_id not in m.catalogs:
                m.catalogs.append(self.source_id)
        return movies

    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch latest TV series."""
        if not self.is_enabled:
            return []
        series = await self._client.get_latest_tv(page=page)
        for s in series:
            if self.source_id not in s.catalogs:
                s.catalogs.append(self.source_id)
        return series

    async def search(self, query: str, media_type: str = "all") -> list[Movie | TvSeries]:
        """Search titles by keyword."""
        if not self.is_enabled:
            return []
        items = await self._client.search(query)
        filtered: list[Movie | TvSeries] = []
        for item in items:
            if self.source_id not in item.catalogs:
                item.catalogs.append(self.source_id)
            if (
                (media_type == "movie" and isinstance(item, Movie))
                or (media_type == "tv" and isinstance(item, TvSeries))
                or media_type == "all"
            ):
                filtered.append(item)
        return filtered

    async def get_details(self, media_type: str, item_id: str) -> Movie | TvSeries:
        """Fetch complete title details."""
        if not self.is_enabled:
            raise ValueError("Reactive source is disabled")

        if not (
            item_id.startswith("sc-")
            or item_id.startswith("reactive-")
            or (item_id.isdigit() and len(item_id) >= 1)
        ):
            raise ValueError(f"ID {item_id} does not belong to reactive source")

        if media_type in ("tv", "series"):
            series = await self._client.get_tv_series(item_id)
            if self.source_id not in series.catalogs:
                series.catalogs.append(self.source_id)
            return series
        movie = await self._client.get_movie(item_id)
        if self.source_id not in movie.catalogs:
            movie.catalogs.append(self.source_id)
        return movie

    async def get_season(self, series_id: str, season_number: int) -> TvSeason:
        """Fetch season episodes."""
        if not self.is_enabled:
            raise ValueError("Reactive source is disabled")

        clean_id = series_id.replace("sc-", "")
        parts = clean_id.split("-", 1)
        sc_id = parts[0]
        slug = parts[1] if len(parts) > 1 else ""
        return await self._client.get_tv_season(sc_id, slug, season_number)

    async def resolve_stream(
        self,
        source: ProviderSource,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve watch URL to playable HLS m3u8 playlist."""
        if not self.is_enabled:
            raise ValueError("Reactive source is disabled")

        m3u8_url, headers = await self._client.resolve_stream(source.page_url, prefer_fhd=prefer_fhd)
        if not m3u8_url:
            raise ValueError("Could not resolve stream URL for reactive source")

        return ResolvedMedia(
            url=m3u8_url,
            mime_type="application/vnd.apple.mpegurl",
            stream_format="hls",
            provider_id=self.source_id,
            headers=headers,
        )

    async def get_genres(self) -> list[str]:
        """Return available genres."""
        if not self.is_enabled:
            return []
        return await self._client.get_genres()

    async def get_by_genre(self, genre: str, media_type: str = "movie", page: int = 1) -> list[Movie | TvSeries]:
        """Fetch titles by genre."""
        if not self.is_enabled:
            return []
        items = await self._client.get_by_genre(genre, media_type=media_type, page=page)
        for item in items:
            if self.source_id not in item.catalogs:
                item.catalogs.append(self.source_id)
        return items

    async def close(self) -> None:
        """Close underlying client."""
        if self._client:
            await self._client.close()
