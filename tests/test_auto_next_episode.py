"""Unit tests for automatic next-episode determination and binge-watching logic."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile

from streaming_hub.backend.database import MediaDatabase


class TestAutoNextEpisode:
    """Test suite ensuring sequential episode determination and season boundaries."""

    def setup_method(self, method=None) -> None:
        """Create a temporary database with prepopulated series."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_next_ep.db"
        self.db = MediaDatabase(self.db_path)
        asyncio.run(self.db.init())

        # Seed series with season 1 (2 episodes) and season 2 (1 episode)
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO titles (id, media_type, title) VALUES (?, ?, ?)",
                ("series_test", "tv", "Stranger Things"),
            )
            s1_eps = [
                {"episode_number": 1, "title": "Chapter One", "poster_url": "s1e1.jpg"},
                {"episode_number": 2, "title": "Chapter Two", "poster_url": "s1e2.jpg"},
            ]
            conn.execute(
                "INSERT INTO seasons (id, series_id, season_number, episodes_json) VALUES (?, ?, ?, ?)",
                ("series_test_s1", "series_test", 1, json.dumps(s1_eps)),
            )
            s2_eps = [
                {"episode_number": 1, "title": "Madmax", "poster_url": "s2e1.jpg"},
            ]
            conn.execute(
                "INSERT INTO seasons (id, series_id, season_number, episodes_json) VALUES (?, ?, ?, ?)",
                ("series_test_s2", "series_test", 2, json.dumps(s2_eps)),
            )

    def teardown_method(self, method=None) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_next_episode_within_same_season(self) -> None:
        """Test transitioning from S1E1 to S1E2."""
        res = asyncio.run(self.db.get_next_episode("series_test", 1, 1))
        assert res is not None
        assert res["season_number"] == 1
        assert res["episode_number"] == 2
        assert res["episode"]["title"] == "Chapter Two"

    def test_next_episode_across_season_boundary(self) -> None:
        """Test transitioning from S1E2 to S2E1."""
        res = asyncio.run(self.db.get_next_episode("series_test", 1, 2))
        assert res is not None
        assert res["season_number"] == 2
        assert res["episode_number"] == 1
        assert res["episode"]["title"] == "Madmax"

    def test_end_of_series_returns_none(self) -> None:
        """Test that the final episode returns None when no further episodes exist."""
        res = asyncio.run(self.db.get_next_episode("series_test", 2, 1))
        assert res is None

    def test_end_of_series_with_known_seasons_returns_none(self) -> None:
        """Test that end of series returns None when titles table has known seasons."""
        # Update titles table with known seasons [1, 2]
        title_dict = {
            "id": "series_test",
            "media_type": "tv",
            "title": "Stranger Things",
            "seasons": [{"number": 1}, {"number": 2}],
        }
        with self.db._get_connection() as conn:
            conn.execute(
                "UPDATE titles SET raw_json = ? WHERE id = ?",
                (json.dumps(title_dict), "series_test"),
            )

        res = asyncio.run(self.db.get_next_episode("series_test", 2, 1))
        assert res is None
