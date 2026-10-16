"""Tests for playback and catalog metadata enhancements (TMDb, Cinemeta, TVmaze, Cast, Proxy)."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streaming_hub.backend.database import MediaDatabase, slug_to_title
from streaming_hub.backend.ha_client import HACoreClient
from streaming_hub.backend.metadata import MetadataEnricher
from streaming_hub.backend.models import Movie, ResolvedMedia, TvEpisode, TvSeason
from streaming_hub.backend.proxy import StreamProxy


class TestMetadataAndPlayback:
    """Test suite verifying metadata enrichment fallbacks, slug parsing, and cast metadata."""

    def test_slug_to_title_handling(self) -> None:
        """Test slug derivation without stripping non-numeric leading tokens."""
        # Multi-word slugs without numeric prefix
        assert slug_to_title("breaking-bad") == "Breaking Bad"
        assert slug_to_title("better-call-saul") == "Better Call Saul"
        assert slug_to_title("sc-peaky-blinders") == "Peaky Blinders"

        # Slugs with numeric prefix (e.g. from scrapers)
        assert slug_to_title("sc-12345-il-gladiatore") == "Il Gladiatore"
        assert slug_to_title("999-inception") == "Inception"

        # Slugs with season/episode suffix
        assert slug_to_title("breaking-bad_s01e01") == "Breaking Bad"

        # Pure numeric strings should return empty string
        assert slug_to_title("12345") == ""
        assert slug_to_title("") == ""

    def test_metadata_slug_to_search_title(self) -> None:
        """Test MetadataEnricher._slug_to_search_title logic."""
        assert MetadataEnricher._slug_to_search_title("breaking-bad") == "breaking bad"
        assert MetadataEnricher._slug_to_search_title("sc-123-il-padrino") == "il padrino"
        assert MetadataEnricher._slug_to_search_title("game-of-thrones_s02e05") == "game of thrones"
        assert MetadataEnricher._slug_to_search_title("55555") == ""

    def test_clean_title_removes_noise(self) -> None:
        """Test _clean_title removes tags, season suffixes, and marketing phrases."""
        clean = MetadataEnricher._clean_title
        assert clean("Breaking Bad - Serie TV") == "Breaking Bad"
        assert clean("Stranger Things - Stagione 4") == "Stranger Things"
        assert clean("Chernobyl - Miniserie") == "Chernobyl"
        assert clean("Inception [ITA 1080p FHD]") == "Inception"
        assert clean("The Matrix (1999) - Film Completo Altadefinizione") == "The Matrix"
        assert clean("Dune 4K Streaming Ita -") == "Dune"

    @pytest.mark.asyncio
    async def test_cast_metadata_structure(self) -> None:
        """Test that play_on_device structures Google Cast metadata dictionary for movies and TV."""
        client = HACoreClient(token="mock_token", base_url="http://mock-supervisor/core/api")

        class MockResponse:
            def __init__(self, status: int = 200) -> None:
                self.status = status

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

            async def text(self) -> str:
                return "ok"

        mock_post = MagicMock(return_value=MockResponse(200))

        with patch("aiohttp.ClientSession.post", mock_post):
            # 1. Movie playback
            ok, target = await client.play_on_device(
                entity_id="media_player.living_room_tv",
                media_url="http://192.168.1.5:8099/stream/hls/test/index.m3u8",
                title="Inception (2010)",
                media_type="movie",
                poster_url="https://image.tmdb.org/t/p/w500/inception.jpg",
            )
            assert ok is True
            assert target == "media_player.living_room_tv"
            assert mock_post.called
            call_payload = mock_post.call_args[1].get("json") or mock_post.call_args[0][1]
            extra = call_payload.get("extra", {})
            metadata = extra.get("metadata", {})
            assert metadata.get("metadataType") == 1
            assert metadata.get("title") == "Inception (2010)"
            assert metadata.get("images") == [{"url": "https://image.tmdb.org/t/p/w500/inception.jpg"}]

            # 2. TV Show episode playback
            mock_post.reset_mock()
            ok_tv, target_tv = await client.play_on_device(
                entity_id="media_player.living_room_tv",
                media_url="http://192.168.1.5:8099/stream/hls/test2/index.m3u8",
                title="Pilot",
                media_type="tv",
                series_title="Breaking Bad",
                season_number=1,
                episode_number=1,
                poster_url="https://image.tmdb.org/t/p/w500/bb.jpg",
            )
            assert ok_tv is True
            assert target_tv == "media_player.living_room_tv"
            call_tv_payload = mock_post.call_args[1].get("json") or mock_post.call_args[0][1]
            extra_tv = call_tv_payload.get("extra", {})
            meta_tv = extra_tv.get("metadata", {})
            assert meta_tv.get("metadataType") == 2
            assert meta_tv.get("seriesTitle") == "Breaking Bad"
            assert meta_tv.get("season") == 1
            assert meta_tv.get("episode") == 1
            assert meta_tv.get("title") == "Pilot"
            assert meta_tv.get("images") == [{"url": "https://image.tmdb.org/t/p/w500/bb.jpg"}]

    @pytest.mark.asyncio
    async def test_stream_proxy_content_disposition(self) -> None:
        """Test stream proxy sets content-disposition header with sanitized media title."""
        proxy = StreamProxy()
        token = proxy.register_stream(
            ResolvedMedia(url="http://upstream.com/live.m3u8"),
            media_title='Breaking Bad - S01E01: "Pilot"',
        )
        session = proxy.get_stream(token)
        assert session is not None
        assert session.media_title == 'Breaking Bad - S01E01: "Pilot"'

        clean_filename = re.sub(r'["\r\n\\]', "", session.media_title).strip()
        assert clean_filename == "Breaking Bad - S01E01: Pilot"

        class MockUpstream:
            status = 200
            url = "http://upstream.com/live.m3u8"

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def text(self):
                return "#EXTM3U\n#EXT-X-VERSION:3\nchunk.ts"

        mock_client = MagicMock()
        mock_client.get = MagicMock(return_value=MockUpstream())

        with patch.object(proxy, "_get_client_session", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_client
            resp = await proxy.get_stream_response(token)
            assert resp.headers["Content-Disposition"] == 'inline; filename="Breaking Bad - S01E01: Pilot.m3u8"'

    @pytest.mark.asyncio
    async def test_enrich_tv_season_cinemeta_fallback(self) -> None:
        """Test fallback to Cinemeta when TMDb API is unavailable."""
        enricher = MetadataEnricher(tmdb_api_key="")

        season = TvSeason(
            number=1,
            episodes=[
                TvEpisode(id="ep1", media_id="bb", season_number=1, episode_number=1, title="Episodio 1"),
                TvEpisode(id="ep2", media_id="bb", season_number=1, episode_number=2, title="Episodio 2"),
            ],
        )

        mock_cinemeta_videos = [
            {
                "season": 1,
                "episode": 1,
                "name": "Pilot Episode",
                "overview": "A chemistry teacher discovers his diagnosis.",
                "thumbnail": "https://images.metahub.space/thumb1.jpg",
            },
            {
                "season": 1,
                "episode": 2,
                "name": "Cat's in the Bag...",
                "overview": "Walt and Jesse deal with their first cook.",
                "thumbnail": "https://images.metahub.space/thumb2.jpg",
            },
        ]

        with patch.object(enricher, "_fetch_cinemeta_series_videos", new_callable=AsyncMock) as mock_cm:
            mock_cm.return_value = mock_cinemeta_videos

            res = await enricher.enrich_tv_season(
                series_tmdb_id=None,
                season=season,
                imdb_id="tt0903747",
                series_title="Breaking Bad",
            )
            assert res.episodes[0].title == "Episodio 1: Pilot Episode"
            assert res.episodes[0].description == "A chemistry teacher discovers his diagnosis."
            assert res.episodes[0].poster_url == "https://images.metahub.space/thumb1.jpg"
            assert res.episodes[1].title == "Episodio 2: Cat's in the Bag..."

    @pytest.mark.asyncio
    async def test_enrich_tv_season_tvmaze_fallback(self) -> None:
        """Test fallback to TVmaze when TMDb and Cinemeta are unavailable."""
        enricher = MetadataEnricher(tmdb_api_key="")

        season = TvSeason(
            number=1,
            episodes=[
                TvEpisode(id="ep1", media_id="got", season_number=1, episode_number=1, title=""),
            ],
        )

        mock_tvmaze_episodes = [
            {
                "season": 1,
                "number": 1,
                "name": "Winter Is Coming",
                "summary": "<p>Lord Stark is asked to serve as the Hand of the King.</p>",
                "image": {
                    "medium": "https://static.tvmaze.com/ep1.jpg",
                    "original": "https://static.tvmaze.com/ep1_orig.jpg",
                },
            }
        ]

        with patch.object(enricher, "_fetch_tvmaze_episodes", new_callable=AsyncMock) as mock_tvm:
            mock_tvm.return_value = mock_tvmaze_episodes

            res = await enricher.enrich_tv_season(
                series_tmdb_id=None,
                season=season,
                imdb_id=None,
                series_title="Game of Thrones - Serie TV",
            )
            mock_tvm.assert_called_once_with("Game of Thrones")
            assert res.episodes[0].title == "Episodio 1: Winter Is Coming"
            assert res.episodes[0].description == "Lord Stark is asked to serve as the Hand of the King."
            assert res.episodes[0].poster_url == "https://static.tvmaze.com/ep1_orig.jpg"

    @pytest.mark.asyncio
    async def test_database_cached_enrichment_hydrates_metadata(self, tmp_path: Path) -> None:
        """Test that enrich_items_with_cached_metadata populates titles, descriptions, and IDs."""
        db_file = tmp_path / "test_enrich.db"
        db = MediaDatabase(db_path=db_file)
        await db.init()

        # Save a rich movie in database
        movie = Movie(
            id="sc-12345-oppenheimer",
            title="Oppenheimer",
            year=2023,
            description="The story of American scientist J. Robert Oppenheimer.",
            tmdb_id=872585,
            imdb_id="tt15398776",
            poster_url="https://image.tmdb.org/t/p/opp.jpg",
            rating=8.9,
        )
        await db.save_title(movie)

        # Batch items: one cached with incomplete data, one uncached with informative slug
        items = [
            {
                "id": "sc-12345-oppenheimer",
                "title": "Senza Titolo",
            },
            {
                "id": "better-call-saul",
                "title": "",
            },
        ]

        await db.enrich_items_with_cached_metadata(items)

        # First item hydrated from SQLite
        assert items[0]["title"] == "Oppenheimer"
        assert items[0]["description"] == "The story of American scientist J. Robert Oppenheimer."
        assert items[0]["year"] == 2023
        assert items[0]["tmdb_id"] == 872585
        assert items[0]["imdb_id"] == "tt15398776"
        assert items[0]["poster_url"] == "https://image.tmdb.org/t/p/opp.jpg"
        assert items[0]["rating"] == 8.9

        # Second item hydrated from slug_to_title
        assert items[1]["title"] == "Better Call Saul"
