"""Tests verifying season and series completion logic in continue watching and watch history."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from streaming_hub.backend.database import MediaDatabase
from streaming_hub.backend.models import TvEpisode, TvSeason, TvSeries


class TestSeriesCompletionContinueWatching:
    """Test suite ensuring completed TV series are removed from Continue Watching and marked completed."""

    @pytest.fixture(autouse=True)
    def setup_db(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db = MediaDatabase(self.db_path)
        self.db._init_sync()
        yield
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_completed_final_episode_excluded_from_continue_watching(self) -> None:
        """When the last episode of the last season is finished and no next episode exists,

        the series should NOT appear in continue watching.
        """
        # Create a series with 1 season and 2 episodes
        ep1 = TvEpisode(id="ep1", media_id="series-lioness", season_number=1, episode_number=1, title="Episode 1")
        ep2 = TvEpisode(id="ep2", media_id="series-lioness", season_number=1, episode_number=2, title="Episode 2")
        season1 = TvSeason(number=1, episodes=[ep1, ep2])
        series = TvSeries(id="series-lioness", title="Special Ops: Lioness", seasons=[season1])

        await self.db.save_title(series)
        await self.db.save_season("series-lioness", season1)

        # Watch Ep1 halfway -> should be in continue watching
        await self.db.save_watch_progress(
            media_id="series-lioness",
            title="Special Ops: Lioness",
            media_type="tv",
            season_number=1,
            episode_number=1,
            progress_seconds=600,
            duration_seconds=1200,
            profile_id="default",
        )

        continue_list = await self.db.get_continue_watching(profile_id="default")
        assert len(continue_list) == 1
        assert continue_list[0]["media_id"] == "series-lioness"
        assert continue_list[0]["episode_number"] == 1

        # Now watch Ep2 to 95% (completed)
        await self.db.save_watch_progress(
            media_id="series-lioness",
            title="Special Ops: Lioness",
            media_type="tv",
            season_number=1,
            episode_number=2,
            progress_seconds=1150,
            duration_seconds=1200,
            profile_id="default",
        )

        # Since Ep2 was the last episode and is completed, series must disappear from Continue Watching!
        continue_list = await self.db.get_continue_watching(profile_id="default")
        assert len(continue_list) == 0

        # But it should appear in Watched History (Visti di recente)
        watched_list = await self.db.get_watched_history(profile_id="default")
        assert len(watched_list) == 1
        assert watched_list[0]["media_id"] == "series-lioness"

    @pytest.mark.asyncio
    async def test_media_progress_marks_completed_when_final_episode_finished(self) -> None:
        """Verify that get_media_progress returns is_completed: True when all episodes are watched."""
        ep1 = TvEpisode(id="ep1", media_id="series-done", season_number=1, episode_number=1, title="Episode 1")
        season1 = TvSeason(number=1, episodes=[ep1])
        series = TvSeries(id="series-done", title="Short Series", seasons=[season1])

        await self.db.save_title(series)
        await self.db.save_season("series-done", season1)

        # Complete ep1
        await self.db.save_watch_progress(
            media_id="series-done",
            title="Short Series",
            media_type="tv",
            season_number=1,
            episode_number=1,
            progress_seconds=1150,
            duration_seconds=1200,
            profile_id="default",
        )

        progress = await self.db.get_media_progress("series-done", profile_id="default")
        assert progress is not None
        assert progress["is_completed"] is True
        assert progress["season_number"] == 1
        assert progress["episode_number"] == 1
