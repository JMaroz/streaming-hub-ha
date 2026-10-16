import asyncio
import time

import pytest

from streaming_hub.backend.database import MediaDatabase
from streaming_hub.backend.models import ProviderSource, TvEpisode, TvSeason, TvSeries


@pytest.mark.asyncio
async def test_save_seasons_benchmark(tmp_path):
    db = MediaDatabase(db_path=tmp_path / "test_perf.db")
    await db.init()

    # Create TV series with 20 seasons, each having 20 episodes
    seasons = []
    for s_num in range(1, 21):
        episodes = [
            TvEpisode(
                id=f"ep_{s_num}_{e_num}",
                media_id="test_series",
                season_number=s_num,
                episode_number=e_num,
                title=f"Episode {e_num}",
                sources=[
                    ProviderSource(
                        id=f"src_{s_num}_{e_num}",
                        media_id="test_series",
                        provider_id="test_provider",
                        provider_name="Test Provider",
                        page_url="http://example.com",
                    )
                ],
            )
            for e_num in range(1, 21)
        ]
        seasons.append(TvSeason(number=s_num, episodes=episodes))

    series = TvSeries(id="test_series", title="Test Series", seasons=seasons)

    # Measure sequential save
    start_seq = time.perf_counter()
    for s in series.seasons:
        if s.episodes:
            await db.save_season(series.id, s)
    seq_duration = time.perf_counter() - start_seq

    # Clear seasons DB
    db_path = tmp_path / "test_perf_gather.db"
    db_gather = MediaDatabase(db_path=db_path)
    await db_gather.init()

    # Measure gather save
    start_gather = time.perf_counter()
    await asyncio.gather(*[db_gather.save_season(series.id, s) for s in series.seasons if s.episodes])
    gather_duration = time.perf_counter() - start_gather

    assert gather_duration <= seq_duration * 1.5  # Safety check
