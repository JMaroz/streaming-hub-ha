"""Benchmark and performance test for _import_items batch optimization."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from streaming_hub.backend.database import MediaDatabase


class TestImportItemsPerformance:
    """Benchmark test for _import_items performance before and after optimization."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path: Path) -> None:
        self.db_path = tmp_path / "test_perf.db"
        self.db = MediaDatabase(self.db_path)
        self.db._init_sync()

    @pytest.mark.asyncio
    async def test_benchmark_import_items(self) -> None:
        """Benchmark adding 200 favorite items sequentially vs batched to establish baseline and verify speedup."""
        # Create 200 dummy TMDb items
        items = [
            {
                "id": 10000 + i,
                "title": f"Test Movie {i}",
                "poster_path": f"/poster_{i}.jpg",
            }
            for i in range(200)
        ]

        # Standard un-batched implementation for comparison/baseline measurement
        async def _legacy_import_items(items_list: list[dict], media_type: str, profile_id: str = "default") -> int:
            count = 0
            for item in items_list:
                tmdb_id = item.get("id")
                if not tmdb_id:
                    continue
                title = item.get("title") or item.get("name") or "Senza Titolo"
                poster_path = item.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

                existing = await self.db.find_title_by_tmdb_or_query(
                    title=title, media_type=media_type, tmdb_id=tmdb_id
                )
                title_id = existing["id"] if existing else f"tmdb-{tmdb_id}"

                added = await self.db.add_favorite(
                    title_id=title_id,
                    media_type=media_type,
                    title=title,
                    poster_url=poster_url,
                    profile_id=profile_id,
                )
                if added:
                    count += 1
            return count

        start_time = time.perf_counter()
        legacy_count = await _legacy_import_items(items, "movie", "default")
        legacy_duration = time.perf_counter() - start_time
        assert legacy_count == 200

        # Benchmark optimized batched implementation with a second set of 200 items
        items_batch = [
            {
                "id": 20000 + i,
                "title": f"Batch Movie {i}",
                "poster_path": f"/poster_batch_{i}.jpg",
            }
            for i in range(200)
        ]

        start_time = time.perf_counter()
        batch_count = await self.db.import_favorites_batch(items_batch, "movie", "default")
        batch_duration = time.perf_counter() - start_time
        assert batch_count == 200

        speedup = legacy_duration / batch_duration if batch_duration > 0 else 0

        import logging

        logger = logging.getLogger(__name__)
        logger.info("[BASELINE BENCHMARK] Legacy _import_items (200 items): %.4fs", legacy_duration)
        logger.info("[OPTIMIZED BENCHMARK] Batched _import_items (200 items): %.4fs", batch_duration)
        logger.info("[SPEEDUP] %.2fx faster!", speedup)

        assert batch_duration < legacy_duration
