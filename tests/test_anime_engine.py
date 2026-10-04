"""Unit tests for the Anime streaming engine and integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streaming_hub.backend.engine_anime import AnimeStreamClient
from streaming_hub.backend.models import Movie, TvSeries
from streaming_hub.backend.sources.anime_source import AnimeSource
from streaming_hub.backend.sources.detector import SourceDetector
from streaming_hub.backend.sources.manager import SourceManager


class TestAnimeStreamClient:
    """Test suite for AnimeStreamClient parsing and models."""

    def test_clean_title_sub(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        title, year, dub_type = client._clean_title("Solo Leveling (SUB ITA)")
        assert title == "Solo Leveling"
        assert dub_type == "sub"

    def test_clean_title_dub(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        title, year, dub_type = client._clean_title("Ranma ½ (2024) (ITA)")
        assert title == "Ranma ½"
        assert year == 2024
        assert dub_type == "dub"

    def test_record_to_media_tv_series(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        record = {
            "id": 4290,
            "title": "Ore dake Level Up na Ken",
            "title_eng": "Solo Leveling",
            "slug": "solo-leveling",
            "type": "TV",
            "date": "2024",
            "episodes_count": 12,
            "dub": 0,
            "score": "8.87",
            "imageurl": "https://cdn.example.com/cover.png",
            "imageurl_cover": "https://cdn.example.com/banner.jpg",
            "plot": "In un mondo dove cacciatori...",
            "genres": [{"name": "Action"}, {"name": "Fantasy"}],
        }

        media = client._record_to_media(record)
        assert isinstance(media, TvSeries)
        assert media.id == "anime-4290-solo-leveling"
        assert media.title == "Solo Leveling"
        assert media.year == 2024
        assert media.rating == 8.9
        assert media.is_anime is True
        assert media.dub_type == "sub"
        assert "Animazione" in media.genres
        assert "Action" in media.genres
        assert media.catalogs == ["anime"]

    def test_record_to_media_movie_dub(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        record = {
            "id": 5500,
            "title": "Demon Slayer: Il treno Mugen",
            "title_eng": "Demon Slayer: Mugen Train",
            "slug": "demon-slayer-mugen-train-ita",
            "type": "Movie",
            "date": "2020",
            "dub": 1,
            "score": "9.1",
            "imageurl": "https://cdn.example.com/movie.png",
        }

        media = client._record_to_media(record)
        assert isinstance(media, Movie)
        assert media.id == "anime-5500-demon-slayer-mugen-train-ita"
        assert "(ITA)" in media.title
        assert media.is_anime is True
        assert media.dub_type == "dub"

    def test_extract_embedded_records(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        sample_records = [
            {"id": 1, "title": "Anime One", "slug": "anime-one"},
            {"id": 2, "title": "Anime Two", "slug": "anime-two"},
        ]
        escaped_json = json.dumps(sample_records).replace('"', "&quot;")
        html_doc = f"""
        <html>
            <body>
                <div id="app">
                    <archivio records="{escaped_json}" count="2"></archivio>
                </div>
            </body>
        </html>
        """
        records = client._extract_embedded_records(html_doc, tag_name="archivio")
        assert len(records) == 2
        assert records[0]["title"] == "AnimeOne" or records[0]["title"] == "Anime One"

    @pytest.mark.asyncio
    async def test_search_embedded_archivio(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        sample_records = [{"id": 4290, "title_eng": "Solo Leveling", "slug": "solo-leveling", "type": "TV", "dub": 0}]
        escaped = json.dumps(sample_records).replace('"', "&quot;")
        mock_html = f'<archivio records="{escaped}"></archivio>'

        client._request = AsyncMock(return_value=mock_html)
        results = await client.search("Solo Leveling")

        assert len(results) == 1
        assert results[0].id == "anime-4290-solo-leveling"
        assert results[0].title == "Solo Leveling"
        assert results[0].is_anime is True

    @pytest.mark.asyncio
    async def test_get_tv_season_chunked_api(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")

        # Mock first batch returning 2 episodes
        batch_1 = {
            "episodes_count": 2,
            "current_episode": 1,
            "episodes": [
                {"id": 101, "number": "1", "scws_id": 901},
                {"id": 102, "number": "2", "scws_id": 902},
            ],
        }

        client._request = AsyncMock(return_value=json.dumps(batch_1))
        season = await client.get_tv_season("4290", season_number=1)

        assert season.number == 1
        assert len(season.episodes) == 2
        assert season.episodes[0].episode_number == 1
        assert season.episodes[0].id == "anime-4290-e1"
        assert len(season.episodes[0].sources) == 1
        assert season.episodes[0].sources[0].provider_id == "anime"


class TestSourceDetectorAnime:
    """Test suite for anime engine detection."""

    def test_heuristic_detection(self) -> None:
        assert SourceDetector.detect_by_heuristic("https://animeserver.com") == "anime"
        assert SourceDetector.detect_by_heuristic("https://streamingcommunity.buzz") == "reactive"
        assert SourceDetector.detect_by_heuristic("https://cb01.movie") == "crawler"

    @pytest.mark.asyncio
    async def test_explicit_detection(self) -> None:
        assert await SourceDetector.detect("https://example.org", user_specified_type="anime") == "anime"
        assert await SourceDetector.detect("https://example.org", user_specified_type="anime_engine") == "anime"

    @pytest.mark.asyncio
    async def test_probe_detection(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {}
        mock_resp.text = AsyncMock(return_value='<html><div id="app"><archivio records="[]"></archivio></div></html>')

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        detected = await SourceDetector.detect_by_probe("https://unknown-mirror.com", session=mock_session)
        assert detected == "anime"


class TestAnimeSourceIntegration:
    """Test suite for AnimeSource adapter in SourceManager."""

    @pytest.mark.asyncio
    async def test_source_manager_registration_and_search(self) -> None:
        source_manager = SourceManager()
        anime_source = AnimeSource(base_url="https://anime.local", enabled=True, name="Test Anime")

        sample_item = TvSeries(
            id="anime-1-naruto",
            title="Naruto",
            year=2002,
            is_anime=True,
            dub_type="sub",
            catalogs=["anime"],
        )
        anime_source._client.search = AsyncMock(return_value=[sample_item])

        source_manager.register_source(anime_source)
        assert source_manager.get_source("anime") is not None
        assert source_manager.get_source("anime").is_enabled is True

        results = await source_manager.search("Naruto")
        assert len(results) == 1
        assert results[0].id == "anime-1-naruto"
        assert getattr(results[0], "is_anime", False) is True

    @pytest.mark.asyncio
    async def test_get_home_carousels_combining(self) -> None:
        source_manager = SourceManager()
        anime_source = AnimeSource(base_url="https://anime.local", enabled=True)

        sample_hero = TvSeries(id="anime-1", title="Hero Anime", catalogs=["anime"])
        sample_carousel = {"id": "anime_latest", "title": "Ultime Uscite Anime", "items": [sample_hero]}
        anime_source.get_carousels = AsyncMock(return_value=(sample_hero, [sample_carousel]))

        source_manager.register_source(anime_source)
        hero, carousels = await source_manager.get_home_carousels()

        assert hero is not None
        assert hero.title == "Hero Anime"
        assert len(carousels) == 1
        assert carousels[0]["id"] == "anime_latest"
