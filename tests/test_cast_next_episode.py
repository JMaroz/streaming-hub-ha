"""Tests for Cast next episode autoplay, countdown synchronization, and progress normalization."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock

import pytest

from streaming_hub.backend.database import MediaDatabase
from streaming_hub.backend.ha_client import HACoreClient
from streaming_hub.backend.models import TvEpisode, TvSeason, TvSeries


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cast_next.db"
        db = MediaDatabase(db_path)
        db._init_sync()
        yield db


@pytest.mark.asyncio
async def test_watch_history_normalization_prevents_duplicate_card(temp_db):
    """Ensure saving progress with an episode ID (e.g. sc-13083_s1e9) normalizes to series ID."""
    # 1. Save TV series
    series = TvSeries(
        id="sc-13083",
        title="Lo straordinario mondo di Gumball",
        media_type="tv",
        seasons=[
            TvSeason(
                number=1,
                episodes=[
                    TvEpisode(
                        id="sc-13083_s1e8",
                        media_id="sc-13083",
                        season_number=1,
                        episode_number=8,
                        title="Il terzo",
                    ),
                    TvEpisode(
                        id="sc-13083_s1e9",
                        media_id="sc-13083",
                        season_number=1,
                        episode_number=9,
                        title="Il debito",
                    ),
                ],
            )
        ],
    )
    await temp_db.save_title(series)
    await temp_db.save_season("sc-13083", series.seasons[0])

    # 2. Simulate complete watching of S1E8
    await temp_db.save_watch_progress(
        media_id="sc-13083",
        title="Lo straordinario mondo di Gumball",
        media_type="tv",
        season_number=1,
        episode_number=8,
        progress_seconds=660,
        duration_seconds=700,
        profile_id="leandro",
    )

    # 3. Simulate Cast playback where bug previously saved media_id="sc-13083_s1e9" and media_type="movie"
    await temp_db.save_watch_progress(
        media_id="sc-13083_s1e9",
        title="Serie TV - S1E9",
        media_type="movie",
        season_number=None,
        episode_number=None,
        progress_seconds=300,
        duration_seconds=700,
        profile_id="leandro",
    )

    # 4. Verify Continue Watching list has exactly 1 entry for the TV series, NOT two entries!
    continue_list = await temp_db.get_continue_watching(profile_id="leandro")
    assert len(continue_list) == 1
    item = continue_list[0]
    assert item["media_id"] == "sc-13083"
    assert item["media_type"] == "tv"
    assert item["season_number"] == 1
    assert item["episode_number"] == 9
    assert item["progress_seconds"] == 300


@pytest.mark.asyncio
async def test_watch_history_heals_corrupted_legacy_movie_records(temp_db):
    """Ensure _migrate_and_heal_sync purges existing spurious movie records ending in _sXeY."""
    with temp_db._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO watch_history (id, profile_id, media_id, title, media_type, progress_seconds, duration_seconds)
            VALUES ('leandro:sc-13083_s1e9', 'leandro', 'sc-13083_s1e9', 'Serie TV - S1E9', 'movie', 300, 700)
            """
        )

    # Re-run healing
    with temp_db._get_connection() as conn:
        temp_db._migrate_and_heal_sync(conn)

    # Verify spurious record is purged
    continue_list = await temp_db.get_continue_watching(profile_id="leandro")
    assert len(continue_list) == 0


@pytest.mark.asyncio
async def test_ha_client_next_episode_countdown_and_action():
    """Test countdown triggering, status reporting, and actionable notification confirmation."""
    client = HACoreClient(token="mock_token", base_url="http://mock-supervisor/core/api")
    client.call_service = AsyncMock(return_value=True)

    play_handler_mock = AsyncMock(return_value=True)
    client.set_play_next_handler(play_handler_mock)

    entity_id = "media_player.living_room_tv"
    session_data = {
        "entity_id": entity_id,
        "media_id": "sc-13083",
        "title": "Gumball - S1E8",
        "media_type": "tv",
        "poster_url": "https://example.com/poster.jpg",
        "season_number": 1,
        "episode_number": 8,
        "seek_position": 0,
        "profile_id": "leandro",
        "next_episode": {
            "has_next": True,
            "season_number": 1,
            "episode_number": 9,
            "episode": {"title": "Il debito", "poster_url": "https://example.com/ep9.jpg"},
        },
        "outro_start": 650.0,
        "countdown_active": False,
        "countdown_remaining": 15,
        "notified": False,
        "next_dismissed": False,
    }
    client._active_cast_sessions[entity_id] = session_data

    # Trigger countdown
    await client.trigger_next_episode_countdown(entity_id)
    assert session_data["countdown_active"] is True
    assert session_data["notified"] is True

    # Check status
    client.get_entity_state = AsyncMock(
        return_value={
            "state": "playing",
            "attributes": {
                "friendly_name": "Living Room TV",
                "media_position": 660.0,
                "media_duration": 700.0,
            },
        }
    )
    status = await client.get_cast_status(entity_id)
    assert status["active"] is True
    assert status["next_episode"] is not None
    assert status["next_episode"]["countdown_active"] is True
    assert status["next_episode"]["season_number"] == 1
    assert status["next_episode"]["episode_number"] == 9

    # Trigger action: play_now
    action_success = await client.handle_next_episode_action(entity_id, "play_now")
    assert action_success is True
    play_handler_mock.assert_awaited_once_with(entity_id, session_data)

    # Cancel countdown task
    if entity_id in client._countdown_tasks:
        client._countdown_tasks[entity_id].cancel()
