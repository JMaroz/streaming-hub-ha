"""Performance benchmark test for bidirectional TMDb favorites synchronization."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import pytest

from streaming_hub.backend.database import MediaDatabase
from streaming_hub.backend.main import TmdbAccountSyncRequest, sync_tmdb_account
from streaming_hub.backend.models import Movie

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_tmdb_sync_performance_benchmark() -> None:
    """Benchmark the performance and database query count of sync_tmdb_account."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "bench_tmdb.db"
        test_db = MediaDatabase(db_path)
        await test_db.init()

        profile_id = "default"
        await test_db.save_tmdb_session(
            profile_id=profile_id,
            session_id="mock_session_123",
            account_id=4567,
            username="bench_user",
        )

        num_favorites = 30
        for i in range(num_favorites):
            title_id = f"movie-{i}"
            movie = Movie(
                id=title_id,
                title=f"Benchmark Movie {i}",
                year=2024,
                tmdb_id=1000 + i,
            )
            await test_db.save_title(movie)
            await test_db.add_favorite(
                title_id=title_id,
                media_type="movie",
                title=movie.title,
                profile_id=profile_id,
            )

        db_get_title_call_count = 0
        original_get_title = test_db.get_title

        async def tracked_get_title(title_id: str):
            nonlocal db_get_title_call_count
            db_get_title_call_count += 1
            return await original_get_title(title_id)

        test_db.get_title = tracked_get_title  # type: ignore[assignment]

        async def mock_post_account_favorite(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms network latency simulation
            return True

        async def mock_get_account_favorites(*args, **kwargs):
            return []

        async def mock_get_account_watchlist(*args, **kwargs):
            return []

        req = TmdbAccountSyncRequest(profile_id=profile_id)

        with (
            patch("streaming_hub.backend.main.db", test_db),
            patch("streaming_hub.backend.main.CONFIG", {"tmdb_api_key": "mock_key"}),
            patch(
                "streaming_hub.backend.main.metadata_enricher.get_account_favorites",
                side_effect=mock_get_account_favorites,
            ),
            patch(
                "streaming_hub.backend.main.metadata_enricher.get_account_watchlist",
                side_effect=mock_get_account_watchlist,
            ),
            patch(
                "streaming_hub.backend.main.metadata_enricher.post_account_favorite",
                side_effect=mock_post_account_favorite,
            ),
        ):
            start_time = time.perf_counter()
            result = await sync_tmdb_account(req)
            elapsed = time.perf_counter() - start_time

        _LOGGER.info(
            "Benchmark: favorites=%d, elapsed=%.4fs, get_title_calls=%d, pushed=%s",
            num_favorites,
            elapsed,
            db_get_title_call_count,
            result.get("pushed_to_tmdb"),
        )

        assert result.get("pushed_to_tmdb") == num_favorites
        assert db_get_title_call_count == 0
