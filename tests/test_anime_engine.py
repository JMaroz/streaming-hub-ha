"""Unit tests for the Anime streaming engine and integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from streaming_hub.backend.dns_resolver import DoHResolver
from streaming_hub.backend.engine_anime import AnimeStreamClient
from streaming_hub.backend.engine_crawler import CrawlerStreamClient
from streaming_hub.backend.models import Movie, ProviderSource, ResolvedMedia, TvEpisode, TvSeason, TvSeries
from streaming_hub.backend.sources.anime_source import AnimeSource
from streaming_hub.backend.sources.detector import SourceDetector
from streaming_hub.backend.sources.manager import SourceManager


class TestAnimeStreamClient:
    """Test suite for AnimeStreamClient parsing and models."""

    def test_clean_title_sub(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        title, _year, dub_type = client._clean_title("Solo Leveling (SUB ITA)")
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

    @pytest.mark.asyncio
    async def test_get_session_custom_doh(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local", custom_dns="cloudflare")
        session = await client._get_session()
        assert session is not None
        assert client._resolver is not None
        assert client._resolver.mode == "cloudflare"
        assert isinstance(session.connector, aiohttp.TCPConnector)
        await client.close()

    @pytest.mark.asyncio
    async def test_crawler_get_session_custom_doh(self) -> None:
        crawler = CrawlerStreamClient(base_url="https://crawler.local", custom_dns="google")
        session = await crawler._get_session()
        assert session is not None
        assert crawler._resolver is not None
        assert crawler._resolver.mode == "google"
        assert isinstance(session.connector, aiohttp.TCPConnector)
        await crawler.close()

    @pytest.mark.asyncio
    async def test_doh_resolver_provider_and_connector_compatibility(self) -> None:
        # Legacy/alternate provider keyword argument
        res_provider = DoHResolver(provider="quad9")
        assert res_provider.mode == "quad9"
        conn1 = res_provider.get_connector()
        assert isinstance(conn1, aiohttp.TCPConnector)

        # Standard mode argument
        res_mode = DoHResolver(mode="cloudflare")
        assert res_mode.mode == "cloudflare"
        conn2 = res_mode.get_connector(ssl=True)
        assert isinstance(conn2, aiohttp.TCPConnector)

        await res_provider.close()
        await res_mode.close()
        await conn1.close()
        await conn2.close()

    def test_clean_title_variations(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        t1, _y1, d1 = client._clean_title("Attack on Titan (SUB ITA)")
        assert t1 == "Attack on Titan"
        assert d1 == "sub"

        t2, _y2, d2 = client._clean_title("One Piece - SUB ITA")
        assert t2 == "One Piece"
        assert d2 == "sub"

        t3, y3, d3 = client._clean_title("Jujutsu Kaisen 0 (2021) (ITA)")
        assert t3 == "Jujutsu Kaisen 0"
        assert y3 == 2021
        assert d3 == "dub"

        t4, _y4, d4 = client._clean_title("Dragon Ball Super: Super Hero [ITA]")
        assert t4 == "Dragon Ball Super: Super Hero"
        assert d4 == "dub"

    @pytest.mark.asyncio
    async def test_get_anime_details_tv_series_with_vue_props(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        anime_record = {
            "id": 4290,
            "title": "Ore dake Level Up na Ken",
            "title_eng": "Solo Leveling",
            "slug": "solo-leveling",
            "type": "TV",
            "date": "2024",
            "episodes_count": 2,
            "dub": 0,
            "score": "8.87",
            "imageurl": "https://cdn.example.com/cover.png",
            "plot": "Cacciatori e portali...",
            "genres": [{"name": "Action"}, {"name": "Fantasy"}],
        }
        episodes_record = [
            {
                "id": 101,
                "number": "1",
                "title": "Io sono abituato",
                "plot": "Jinwoo affronta il dungeon...",
                "imageurl": "https://cdn.example.com/ep1.jpg",
            },
            {
                "id": 102,
                "number": "2",
                "title": "Se avessi un'altra possibilità",
                "plot": "Il re dei demoni...",
                "imageurl": "https://cdn.example.com/ep2.jpg",
            },
        ]
        escaped_anime = json.dumps(anime_record).replace('"', "&quot;")
        escaped_eps = json.dumps(episodes_record).replace('"', "&quot;")
        html_page = f'<video-player :anime="{escaped_anime}" :episodes="{escaped_eps}"></video-player>'

        client._request = AsyncMock(return_value=html_page)

        details = await client.get_anime_details("4290", slug="solo-leveling")

        assert isinstance(details, TvSeries)
        assert details.id == "anime-4290-solo-leveling"
        assert details.title == "Solo Leveling"
        assert details.original_title == "Ore dake Level Up na Ken"
        assert details.year == 2024
        assert details.rating == 8.9
        assert details.is_anime is True
        assert details.dub_type == "sub"
        assert "Animazione" in details.genres
        assert "Action" in details.genres
        assert len(details.seasons) == 1

        season = details.seasons[0]
        assert season.number == 1
        assert len(season.episodes) == 2

        ep1 = season.episodes[0]
        assert ep1.episode_number == 1
        assert ep1.title == "Io sono abituato"
        assert ep1.description == "Jinwoo affronta il dungeon..."
        assert ep1.poster_url == "https://cdn.example.com/ep1.jpg"
        assert len(ep1.sources) == 1
        assert ep1.sources[0].provider_id == "anime"
        assert ep1.sources[0].page_url == "https://anime.local/embed-url/101"

    @pytest.mark.asyncio
    async def test_get_anime_details_movie_with_sources(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        movie_record = {
            "id": 5500,
            "title": "Kimetsu no Yaiba: Mugen Ressha-hen",
            "title_eng": "Demon Slayer: Il treno Mugen",
            "slug": "demon-slayer-mugen-train-ita",
            "type": "Movie",
            "date": "2020",
            "dub": 1,
            "score": "9.1",
            "imageurl": "https://cdn.example.com/mugen.jpg",
            "plot": "Tanjiro sale a bordo del treno Mugen...",
            "genres": [{"name": "Azione"}, {"name": "Fantasy"}],
        }
        movie_eps = [
            {"id": 9001, "number": "1", "title": "Film Completo"},
        ]
        escaped_anime = json.dumps(movie_record).replace('"', "&quot;")
        escaped_eps = json.dumps(movie_eps).replace('"', "&quot;")
        html_page = f'<video-player :anime="{escaped_anime}" :episodes="{escaped_eps}"></video-player>'

        client._request = AsyncMock(return_value=html_page)

        details = await client.get_anime_details("5500", slug="demon-slayer-mugen-train-ita")

        assert isinstance(details, Movie)
        assert details.id == "anime-5500-demon-slayer-mugen-train-ita"
        assert "(ITA)" in details.title
        assert details.is_anime is True
        assert details.dub_type == "dub"
        assert details.year == 2020
        assert details.rating == 9.1
        assert len(details.sources) == 1
        assert details.sources[0].provider_id == "anime"
        assert details.sources[0].page_url == "https://anime.local/embed-url/9001"
        assert details.source_a_url == "https://anime.local/embed-url/9001"

    @pytest.mark.asyncio
    async def test_get_latest_releases_parsing(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        sample_records = [
            {
                "id": 1,
                "title": "Anime Series One",
                "slug": "anime-series-one",
                "type": "TV",
                "dub": 0,
                "date": "2024",
                "score": "8.5",
                "imageurl": "https://cdn.example.com/1.jpg",
                "plot": "Trama serie...",
            },
            {
                "id": 2,
                "title": "Anime Movie One",
                "slug": "anime-movie-one",
                "type": "Movie",
                "dub": 1,
                "date": "2023",
                "score": "8.0",
                "imageurl": "https://cdn.example.com/2.jpg",
                "plot": "Trama film...",
            },
        ]
        escaped_json = json.dumps(sample_records).replace('"', "&quot;")
        mock_html = f'<div id="app"><archivio :records="{escaped_json}"></archivio></div>'

        client._request = AsyncMock(return_value=mock_html)
        releases = await client.get_latest_releases(page=1)

        assert len(releases) == 2
        assert isinstance(releases[0], TvSeries)
        assert releases[0].id == "anime-1-anime-series-one"
        assert releases[0].dub_type == "sub"
        assert isinstance(releases[1], Movie)
        assert releases[1].id == "anime-2-anime-movie-one"
        assert releases[1].dub_type == "dub"

    @pytest.mark.asyncio
    async def test_get_latest_releases_layout_items_unwrap(self) -> None:
        """Test that layout-items paginated data unwraps item['anime'] and deduplicates by ID."""
        client = AnimeStreamClient(base_url="https://anime.local")
        items_payload = {
            "current_page": 1,
            "data": [
                {
                    "id": 9901,
                    "number": "5",
                    "anime": {"id": 10, "title_eng": "One Piece", "slug": "one-piece", "type": "TV", "dub": 0},
                },
                {
                    "id": 9902,
                    "number": "4",
                    "anime": {"id": 10, "title_eng": "One Piece", "slug": "one-piece", "type": "TV", "dub": 0},
                },
                {
                    "id": 9903,
                    "number": "2",
                    "anime": {"id": 20, "title_eng": "Psyren", "slug": "psyren", "type": "TV", "dub": 0},
                },
            ],
        }
        escaped = json.dumps(items_payload).replace('"', "&quot;")
        mock_html = f'<layout-items items-json="{escaped}"></layout-items>'

        client._request = AsyncMock(return_value=mock_html)
        releases = await client.get_latest_releases(page=1)

        assert len(releases) == 2
        assert releases[0].title == "One Piece"
        assert releases[1].title == "Psyren"

    @pytest.mark.asyncio
    async def test_get_homepage_carousels_extracts_latest_and_featured(self) -> None:
        """Test that get_homepage_carousels returns both Ultime Uscite Anime and Anime in Evidenza from homepage."""
        client = AnimeStreamClient(base_url="https://anime.local")
        layout_payload = {
            "current_page": 1,
            "data": [
                {
                    "id": 101,
                    "number": "1",
                    "anime": {"id": 10, "title_eng": "Latest Anime", "slug": "latest-anime", "type": "TV"},
                }
            ],
        }
        carousel_payload = [
            {"id": 20, "title_eng": "Featured Anime", "slug": "featured-anime", "type": "TV"},
        ]
        escaped_layout = json.dumps(layout_payload).replace('"', "&quot;")
        escaped_carousel = json.dumps(carousel_payload).replace('"', "&quot;")
        mock_html = (
            f'<the-carousel animes="{escaped_carousel}"></the-carousel>'
            f'<layout-items items-json="{escaped_layout}"></layout-items>'
        )

        client._request = AsyncMock(return_value=mock_html)
        hero, carousels = await client.get_homepage_carousels()

        assert hero is not None
        assert hero.title == "Latest Anime"
        assert len(carousels) == 2
        assert carousels[0]["id"] == "anime_latest"
        assert carousels[0]["title"] == "Ultime Uscite Anime"
        assert carousels[0]["items"][0].title == "Latest Anime"
        assert carousels[1]["id"] == "anime_featured"
        assert carousels[1]["title"] == "Anime in Evidenza"
        assert carousels[1]["items"][0].title == "Featured Anime"

    @pytest.mark.asyncio
    async def test_resolve_stream_vixcloud_flow(self) -> None:
        client = AnimeStreamClient(base_url="https://anime.local")
        client.get_embed_url = AsyncMock(return_value="https://vixcloud.co/embed/abc123xyz")
        client._reactive_client.resolve_stream = AsyncMock(
            return_value=("https://vix-content.net/playlist.m3u8", {"Referer": "https://vixcloud.co/"})
        )

        m3u8_url, headers = await client.resolve_stream("https://anime.local/embed-url/9001")
        assert m3u8_url == "https://vix-content.net/playlist.m3u8"
        assert headers == {"Referer": "https://vixcloud.co/"}
        client.get_embed_url.assert_called_once_with("https://anime.local/embed-url/9001")
        client._reactive_client.resolve_stream.assert_called_once_with(
            "https://vixcloud.co/embed/abc123xyz", prefer_fhd=True
        )


class TestSourceDetectorAnime:
    """Test suite for anime engine detection."""

    def test_heuristic_detection(self) -> None:
        assert SourceDetector.detect_by_heuristic("https://animeserver.com") == "anime"
        assert SourceDetector.detect_by_heuristic("https://reactive-community.org") == "reactive"
        assert SourceDetector.detect_by_heuristic("https://film-streaming-crawler.org") == "crawler"

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

    @pytest.mark.asyncio
    async def test_anime_source_get_details_and_season(self) -> None:
        anime_source = AnimeSource(base_url="https://anime.local", enabled=True)
        sample_series = TvSeries(id="anime-123", title="Sample", catalogs=[])
        sample_season = TvSeason(
            number=1,
            episodes=[
                TvEpisode(
                    id="anime-123-e1",
                    media_id="anime-123",
                    season_number=1,
                    episode_number=1,
                    title="Ep 1",
                    sources=[
                        ProviderSource(
                            id="anime-123-1",
                            media_id="anime-123",
                            provider_id="anime",
                            provider_name="Anime HLS",
                            page_url="https://anime.local/embed-url/1",
                        )
                    ],
                )
            ],
        )

        anime_source._client.get_anime_details = AsyncMock(return_value=sample_series)
        anime_source._client.get_tv_season = AsyncMock(return_value=sample_season)

        details = await anime_source.get_details("tv", "anime-123")
        assert "anime" in details.catalogs

        season = await anime_source.get_season("anime-123", season_number=1)
        assert len(season.episodes) == 1
        assert season.episodes[0].sources[0].provider_id == "anime"

    @pytest.mark.asyncio
    async def test_anime_source_resolve_stream(self) -> None:
        anime_source = AnimeSource(base_url="https://anime.local", enabled=True)
        source = ProviderSource(
            id="anime-1-10",
            media_id="anime-1",
            provider_id="anime",
            provider_name="Anime HLS",
            page_url="https://anime.local/embed-url/10",
        )
        anime_source._client.resolve_stream = AsyncMock(
            return_value=("https://vix-content.net/master.m3u8", {"User-Agent": "Test"})
        )

        resolved = await anime_source.resolve_stream(source)
        assert isinstance(resolved, ResolvedMedia)
        assert resolved.url == "https://vix-content.net/master.m3u8"
        assert resolved.stream_format == "hls"
        assert resolved.provider_id == "anime"
        assert resolved.headers == {"User-Agent": "Test"}

    @pytest.mark.asyncio
    async def test_source_manager_search_preserves_anime_sequels_and_parts(self) -> None:
        """Test that search does not accidentally merge split-cours/sequels (e.g., Gate Part 1 and Gate Part 2)."""
        source_manager = SourceManager()
        anime_source = AnimeSource(base_url="https://anime.local", enabled=True, name="Test Anime")

        gate_s1 = TvSeries(
            id="anime-15-gate",
            title="GATE",
            original_title="Gate: Jieitai Kanochi nite, Kaku Tatakaeri",
            year=2015,
            is_anime=True,
            dub_type="sub",
            catalogs=["anime"],
        )
        gate_s2 = TvSeries(
            id="anime-166-gate-part-2",
            title="GATE Part 2",
            original_title="Gate: Jieitai Kanochi nite, Kaku Tatakaeri Part 2",
            year=2016,
            is_anime=True,
            dub_type="sub",
            catalogs=["anime"],
        )
        steins_gate = TvSeries(
            id="anime-50-steins-gate",
            title="Steins;Gate",
            original_title="Steins;Gate",
            year=2011,
            is_anime=True,
            dub_type="sub",
            catalogs=["anime"],
        )

        anime_source._client.search = AsyncMock(return_value=[gate_s1, gate_s2, steins_gate])
        source_manager.register_source(anime_source)

        results = await source_manager.search("gate")
        result_ids = [r.id for r in results]

        assert len(results) == 3
        assert "anime-15-gate" in result_ids
        assert "anime-166-gate-part-2" in result_ids
        assert "anime-50-steins-gate" in result_ids

    @pytest.mark.asyncio
    async def test_source_manager_search_preserves_sub_and_dub_anime_releases(self) -> None:
        """Test that SUB ITA and DUB ITA anime with distinct catalog IDs are both preserved."""
        source_manager = SourceManager()
        anime_source = AnimeSource(base_url="https://anime.local", enabled=True, name="Test Anime")

        solo_sub = TvSeries(
            id="anime-4290-solo-leveling",
            title="Solo Leveling",
            original_title="Ore dake Level Up na Ken",
            year=2024,
            is_anime=True,
            dub_type="sub",
            catalogs=["anime"],
        )
        solo_dub = TvSeries(
            id="anime-4500-solo-leveling-ita",
            title="Solo Leveling (ITA)",
            original_title="Ore dake Level Up na Ken",
            year=2024,
            is_anime=True,
            dub_type="dub",
            catalogs=["anime"],
        )

        anime_source._client.search = AsyncMock(return_value=[solo_sub, solo_dub])
        source_manager.register_source(anime_source)

        results = await source_manager.search("solo leveling")
        result_ids = [r.id for r in results]

        assert len(results) == 2
        assert "anime-4290-solo-leveling" in result_ids
        assert "anime-4500-solo-leveling-ita" in result_ids
