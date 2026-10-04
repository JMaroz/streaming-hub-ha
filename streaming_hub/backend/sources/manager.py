"""Source Manager coordinating multi-site catalog aggregation and stream resolution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..models import Movie, ProviderSource, ResolvedMedia, TvSeason, TvSeries
from ..utils import CatalogMerger
from .base import BaseSource

_LOGGER = logging.getLogger(__name__)


class SourceManager:
    """Manages all registered streaming sources (reactive, crawler, etc.).

    Coordinates concurrent queries, translates all results into the common
    Streaming Hub data models, and unifies duplicates across providers.
    """

    def __init__(self) -> None:
        """Initialize SourceManager with an empty registry."""
        self._sources: dict[str, BaseSource] = {}

    def register_source(self, source: BaseSource) -> None:
        """Register a new catalog/streaming source."""
        self._sources[source.source_id] = source
        _LOGGER.debug("Registered source: %s (enabled=%s)", source.source_id, source.is_enabled)

    def get_source(self, source_id: str) -> BaseSource | None:
        """Retrieve a specific registered source by ID."""
        return self._sources.get(source_id)

    def list_sources(self) -> list[dict[str, Any]]:
        """Return metadata list of all registered sources."""
        return [
            {
                "id": s.source_id,
                "name": s.display_name,
                "icon": s.icon,
                "enabled": s.is_enabled,
                "supported_types": s.supported_types,
            }
            for s in self._sources.values()
        ]

    def get_enabled_sources(self, filter_id: str = "all") -> list[BaseSource]:
        """Return active sources, optionally filtered by ID."""
        if filter_id != "all":
            src = self.get_source(filter_id)
            return [src] if src and src.is_enabled else []
        return [s for s in self._sources.values() if s.is_enabled]

    async def get_latest(
        self,
        media_type: str = "all",
        source_filter: str = "all",
        page: int = 1,
    ) -> list[Movie | TvSeries]:
        """Retrieve latest titles across enabled sources with deduplication."""
        sources = self.get_enabled_sources(source_filter)
        if not sources:
            return []

        all_movies: list[Movie] = []
        all_series: list[TvSeries] = []

        # Run movie and TV queries concurrently across all active sources
        tasks = []
        for src in sources:
            if media_type in ("all", "movie") and "movie" in src.supported_types:
                tasks.append(self._safe_call(src.get_latest_movies(page=page), f"{src.source_id}:latest_movies"))
            if media_type in ("all", "tv") and "tv" in src.supported_types:
                tasks.append(self._safe_call(src.get_latest_tv(page=page), f"{src.source_id}:latest_tv"))

        results = await asyncio.gather(*tasks)

        for res in results:
            if not res or not isinstance(res, list):
                continue
            for item in res:
                if isinstance(item, Movie):
                    all_movies.append(item)
                elif isinstance(item, TvSeries):
                    all_series.append(item)

        # Merge and deduplicate across sources
        merged_movies = CatalogMerger.merge_movie_lists([], all_movies)
        merged_series = CatalogMerger.merge_tv_lists([], all_series)

        if media_type == "movie":
            return merged_movies
        if media_type == "tv":
            return merged_series

        # Interleave movies and series for home feed
        interleaved: list[Movie | TvSeries] = []
        max_len = max(len(merged_movies), len(merged_series))
        for i in range(max_len):
            if i < len(merged_movies):
                interleaved.append(merged_movies[i])
            if i < len(merged_series):
                interleaved.append(merged_series[i])
        return interleaved

    async def get_home_carousels(
        self,
        source_filter: str = "all",
    ) -> tuple[Movie | TvSeries | None, list[dict[str, Any]]]:
        """Fetch home carousels and hero title from enabled carousel-capable sources."""
        sources = self.get_enabled_sources(source_filter)
        if not sources:
            return None, []

        carousel_sources = [s for s in sources if getattr(s, "has_carousels", False)]
        if not carousel_sources:
            return None, []

        combined_carousels: list[dict[str, Any]] = []
        primary_hero: Movie | TvSeries | None = None

        for src in carousel_sources:
            try:
                hero, carousels = await src.get_carousels()
                if not primary_hero and hero:
                    primary_hero = hero
                if carousels:
                    combined_carousels.extend(carousels)
            except Exception as err:
                _LOGGER.warning("Error fetching home carousels from %s: %s", src.source_id, err)

        return primary_hero, combined_carousels

    async def search(
        self,
        query: str,
        media_type: str = "all",
        source_filter: str = "all",
    ) -> list[Movie | TvSeries]:
        """Search titles across enabled sources with cross-catalog unification."""
        sources = self.get_enabled_sources(source_filter)
        if not sources or not query.strip():
            return []

        tasks = [
            self._safe_call(src.search(query, media_type=media_type), f"{src.source_id}:search") for src in sources
        ]
        results = await asyncio.gather(*tasks)

        movies: list[Movie] = []
        series: list[TvSeries] = []

        for res in results:
            if not res or not isinstance(res, list):
                continue
            for item in res:
                if isinstance(item, Movie):
                    movies.append(item)
                elif isinstance(item, TvSeries):
                    series.append(item)

        merged_movies = CatalogMerger.merge_movie_lists([], movies)
        merged_series = CatalogMerger.merge_tv_lists([], series)

        if media_type == "movie":
            return merged_movies
        if media_type == "tv":
            return merged_series

        return merged_movies + merged_series

    async def get_details(self, media_type: str, item_id: str) -> Movie | TvSeries:
        """Fetch details from the source managing this ID, or try available sources."""
        # Check source prefix routing
        for source_id, src in self._sources.items():
            if not src.is_enabled:
                continue
            if item_id.startswith(f"{source_id}-") or (
                source_id in ("reactive", "engine_alpha") and item_id.startswith("sc-")
            ):
                return await src.get_details(media_type, item_id)

        # Fallback: query enabled sources until found
        for src in self.get_enabled_sources():
            try:
                return await src.get_details(media_type, item_id)
            except Exception:
                continue

        raise ValueError(f"Title {item_id} not found on any active source")

    async def get_season(self, series_id: str, season_number: int) -> TvSeason:
        """Fetch season details from the appropriate source."""
        for source_id, src in self._sources.items():
            if not src.is_enabled:
                continue
            if series_id.startswith(f"{source_id}-") or (
                source_id in ("reactive", "engine_alpha") and series_id.startswith("sc-")
            ):
                return await src.get_season(series_id, season_number)

        for src in self.get_enabled_sources():
            try:
                return await src.get_season(series_id, season_number)
            except Exception:
                continue

        raise ValueError(f"Season {season_number} for {series_id} not found")

    async def resolve_stream(
        self,
        source: ProviderSource,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve a ProviderSource to a playable HLS stream via its source adapter."""
        # 1. Match by provider_id
        src = self.get_source(source.provider_id)
        if src and src.is_enabled:
            return await src.resolve_stream(source, prefer_fhd=prefer_fhd)

        # 2. Match by URL keyword
        url_lower = source.page_url.lower()
        for s in self.get_enabled_sources():
            if s.source_id in url_lower:
                return await s.resolve_stream(source, prefer_fhd=prefer_fhd)

        # 3. Fallback: try each enabled source
        for s in self.get_enabled_sources():
            try:
                return await s.resolve_stream(source, prefer_fhd=prefer_fhd)
            except Exception:
                continue

        raise ValueError(f"No suitable source adapter could resolve {source.provider_name} ({source.page_url})")

    async def resolve_stream_with_fallback(
        self,
        source: ProviderSource,
        alternate_sources: list[ProviderSource] | None = None,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve primary source with transparent automatic failover to alternate sources on failure."""
        sources_to_try = [source] + (alternate_sources or [])
        last_error: Exception | None = None

        for s in sources_to_try:
            try:
                resolved = await self.resolve_stream(s, prefer_fhd=prefer_fhd)
                if resolved and resolved.url:
                    return resolved
            except Exception as err:
                _LOGGER.info(
                    "Source resolution failed for %s (%s): %s. Attempting failover...",
                    s.provider_name,
                    s.page_url,
                    err,
                )
                last_error = err

        raise ValueError(f"All {len(sources_to_try)} streaming sources failed to resolve: {last_error}")

    async def get_all_genres(self) -> list[str]:
        """Return combined unique list of genres across all active sources."""
        genres_set: set[str] = set()
        for src in self.get_enabled_sources():
            try:
                g_list = await src.get_genres()
                genres_set.update(g_list)
            except Exception:
                continue

        if not genres_set:
            return [
                "Animazione",
                "Avventura",
                "Azione",
                "Commedia",
                "Documentario",
                "Drammatico",
                "Fantascienza",
                "Horror",
                "Thriller",
            ]
        return sorted(genres_set)

    async def get_by_genre(
        self,
        genre: str,
        media_type: str = "movie",
        source_filter: str = "all",
        page: int = 1,
    ) -> list[Movie | TvSeries]:
        """Fetch titles matching a genre across sources."""
        sources = self.get_enabled_sources(source_filter)
        tasks = [
            self._safe_call(src.get_by_genre(genre, media_type=media_type, page=page), f"{src.source_id}:genre")
            for src in sources
        ]
        results = await asyncio.gather(*tasks)

        collected: list[Movie | TvSeries] = []
        for res in results:
            if isinstance(res, list):
                collected.extend(res)

        if media_type == "tv":
            tv_items = [item for item in collected if isinstance(item, TvSeries)]
            return CatalogMerger.merge_tv_lists([], tv_items)
        movie_items = [item for item in collected if isinstance(item, Movie)]
        return CatalogMerger.merge_movie_lists([], movie_items)

    async def _safe_call(self, coro, label: str) -> Any:
        """Execute a coroutine safely with error logging and fallback to empty list."""
        try:
            return await coro
        except Exception as err:
            _LOGGER.debug("Source call '%s' failed: %s", label, err)
            return []

    async def close_all(self) -> None:
        """Close all sources."""
        for s in self._sources.values():
            await s.close()
