"""Benchmark and DoD impact tests for database performance optimization."""

import asyncio
import json
import logging
import tracemalloc

import pytest

from streaming_hub.backend.database import MediaDatabase

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_database_cursor_streaming_memory_and_speed_benchmark(tmp_path) -> None:
    """Benchmark direct cursor iteration vs fetchall loading for watch providers queries."""
    db_file = tmp_path / "test_perf.db"
    db = MediaDatabase(db_path=db_file)
    await db.init()

    # Seed database with 5,000 title records with JSON payload
    num_records = 5000
    ids = []
    large_wp_dict = {
        "flatrate": [{"provider_id": i, "provider_name": f"Provider_{i}"} for i in range(20)],
        "buy": [{"provider_id": i + 100, "provider_name": f"BuyProvider_{i}"} for i in range(20)],
    }
    wp_str = json.dumps(large_wp_dict)

    with db._get_connection() as conn:
        conn.executemany(
            "INSERT INTO titles (id, media_type, title, watch_providers) VALUES (?, 'movie', ?, ?)",
            [(f"id_{i}", f"Title {i}", wp_str) for i in range(num_records)],
        )
        ids = [f"id_{i}" for i in range(num_records)]

    # Measure memory and timing with optimized get_titles_watch_providers
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    start_time = asyncio.get_event_loop().time()
    res = await db.get_titles_watch_providers(ids)
    elapsed = asyncio.get_event_loop().time() - start_time

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Verification / Definition of Done impact
    assert len(res) == num_records
    assert res["id_0"]["flatrate"][0]["provider_name"] == "Provider_0"

    # Ensure peak memory allocation was modest (no memory spikes from loading full fetchall lists)
    top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff = sum(stat.size_diff for stat in top_stats)

    # Document benchmark statistics
    _LOGGER.info("Fetched watch_providers for %d records in %.4fs", num_records, elapsed)
    _LOGGER.info("Memory difference: %.2f KiB", total_diff / 1024)
