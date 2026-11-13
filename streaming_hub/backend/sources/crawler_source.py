"""Semantic web catalog and stream source adapter."""

from __future__ import annotations

import logging

from ..engine_crawler import CrawlerStreamClient
from ..models import Movie, ProviderSource, ResolvedMedia, TvSeason, TvSeries
from ..providers.maxstream import MaxstreamProvider
from ..providers.mixdrop import MixdropProvider
from .base import BaseSource

_LOGGER = logging.getLogger(__name__)


class CrawlerSource(BaseSource):
    """Source adapter for semantic web catalogs."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = "cloudflare",
        enabled: bool = True,
        name: str | None = None,
    ) -> None:
        """Initialize crawler source with user-specified base URL."""
        self._enabled = enabled
        self._base_url = base_url
        self._name = name or "Sorgente Web"
        self._client = CrawlerStreamClient(base_url=base_url, custom_dns=custom_dns) if enabled and base_url else None
        self._maxstream = MaxstreamProvider()
        self._mixdrop = MixdropProvider()

    @property
    def source_id(self) -> str:
        """Source identifier."""
        return "crawler"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self._name

    @property
    def icon(self) -> str:
        """Icon identifier."""
        return "mdi:filmstrip"

    @property
    def is_enabled(self) -> bool:
        """Check if source is enabled."""
        return self._enabled and self._client is not None

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
            raise ValueError("Crawler source is disabled")

        clean_id = item_id.removeprefix("crawler-").removeprefix("cb01-")
        if media_type in ("tv", "series"):
            series = await self._client.get_tv_series(clean_id)
            if self.source_id not in series.catalogs:
                series.catalogs.append(self.source_id)
            return series
        movie = await self._client.get_movie(clean_id)
        if self.source_id not in movie.catalogs:
            movie.catalogs.append(self.source_id)
        return movie

    async def get_season(self, series_id: str, season_number: int) -> TvSeason:
        """Fetch season episodes."""
        if not self.is_enabled:
            raise ValueError("Crawler source is disabled")

        clean_id = series_id.removeprefix("crawler-").removeprefix("cb01-")
        series = await self._client.get_tv_series(clean_id)
        for s in series.seasons:
            if s.number == season_number:
                return s

        raise ValueError(f"Season {season_number} not found for {series_id}")

    async def resolve_stream(
        self,
        source: ProviderSource,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve embed video link using appropriate provider adapter."""
        if not self.is_enabled:
            raise ValueError("Crawler source is disabled")

        prov_id = source.provider_id.lower()
        if "maxstream" in prov_id:
            session = await self._client._get_session()
            return await self._maxstream.resolve(source, session, prefer_fhd=prefer_fhd)
        if "mixdrop" in prov_id:
            session = await self._client._get_session()
            return await self._mixdrop.resolve(source, session, prefer_fhd=prefer_fhd)

        raise ValueError(f"No direct stream provider available for crawler host {source.provider_name}")

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
