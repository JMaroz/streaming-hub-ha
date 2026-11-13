"""Anti-regression test suite for Crawler (cb01) integration across catalog, routing, and playback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from streaming_hub.backend.models import Movie, ProviderSource, ResolvedMedia, TvSeries
from streaming_hub.backend.proxy import StreamProxy
from streaming_hub.backend.sources.base import BaseSource
from streaming_hub.backend.sources.manager import SourceManager
from streaming_hub.backend.utils import CatalogMerger


class TestCatalogMergerRegression:
    """Anti-regression tests for catalog unification between reactive and crawler."""

    def test_merge_movies_reactive_and_crawler(self) -> None:
        """Test CatalogMerger unifies matching movie titles and merges catalogs tags."""
        m_reactive = Movie(
            id="sc-101-matrix",
            title="The Matrix",
            year=1999,
            poster_url="https://img.example.com/matrix.jpg",
            catalogs=["reactive"],
        )
        m_crawler = Movie(
            id="matrix-1999",
            title="The Matrix",
            year=1999,
            poster_url="https://img.cb01.uno/matrix.jpg",
            catalogs=["crawler"],
            source_b_url="https://cb01one.uno/matrix-1999/",
        )
        m_unique_crawler = Movie(
            id="oppenheimer-2023",
            title="Oppenheimer",
            year=2023,
            poster_url="https://img.cb01.uno/oppenheimer.jpg",
            catalogs=["crawler"],
        )

        merged = CatalogMerger.merge_movie_lists([m_reactive], [m_crawler, m_unique_crawler])
        assert len(merged) == 2

        matrix = next(m for m in merged if "Matrix" in m.title)
        assert "reactive" in matrix.catalogs
        assert "crawler" in matrix.catalogs
        assert matrix.source_b_url == "https://cb01one.uno/matrix-1999/"

        opp = next(m for m in merged if m.title == "Oppenheimer")
        assert opp.catalogs == ["crawler"]

    def test_merge_tv_reactive_and_crawler(self) -> None:
        """Test CatalogMerger unifies matching TV series across sources."""
        tv_reactive = TvSeries(
            id="sc-202-stranger-things",
            title="Stranger Things",
            year=2016,
            catalogs=["reactive"],
            seasons=[],
        )
        tv_crawler = TvSeries(
            id="stranger-things",
            title="Stranger Things",
            year=2016,
            catalogs=["crawler"],
            source_b_url="https://cb01one.uno/serietv/stranger-things/",
            seasons=[],
        )

        merged = CatalogMerger.merge_tv_lists([tv_reactive], [tv_crawler])
        assert len(merged) == 1
        st = merged[0]
        assert "reactive" in st.catalogs
        assert "crawler" in st.catalogs
        assert st.source_b_url == "https://cb01one.uno/serietv/stranger-things/"


class TestSourceManagerRoutingRegression:
    """Anti-regression tests for SourceManager routing to CrawlerSource."""

    @pytest.mark.asyncio
    async def test_resolve_stream_routes_mixdrop_to_crawler(self) -> None:
        """Test SourceManager routes mixdrop provider_id directly to crawler adapter."""
        manager = SourceManager()

        mock_crawler = MagicMock(spec=BaseSource)
        mock_crawler.source_id = "crawler"
        mock_crawler.is_enabled = True
        mock_crawler.resolve_stream = AsyncMock(
            return_value=ResolvedMedia(
                url="https://s10.mxcontent.net/v2/video.mp4",
                mime_type="video/mp4",
                stream_format="mp4",
                provider_id="mixdrop",
            )
        )
        manager.register_source(mock_crawler)

        source = ProviderSource(
            id="src_1",
            media_id="item_1",
            provider_id="mixdrop",
            provider_name="Mixdrop",
            page_url="https://stayonline.pro/l/12345/",
        )

        resolved = await manager.resolve_stream(source)
        assert resolved.url == "https://s10.mxcontent.net/v2/video.mp4"
        assert resolved.stream_format == "mp4"
        mock_crawler.resolve_stream.assert_called_once_with(source, prefer_fhd=True)

    @pytest.mark.asyncio
    async def test_failover_from_mixdrop_to_alternate_source(self) -> None:
        """Test SourceManager failover when primary Mixdrop resolution throws."""
        manager = SourceManager()

        failing_mixdrop = ProviderSource(
            id="src_1",
            media_id="item_1",
            provider_id="mixdrop",
            provider_name="Mixdrop",
            page_url="https://stayonline.pro/l/dead_link/",
        )
        backup_source = ProviderSource(
            id="src_2",
            media_id="item_1",
            provider_id="reactive",
            provider_name="Reactive Stream",
            page_url="https://reactive.example.com/stream.m3u8",
        )

        mock_crawler = MagicMock(spec=BaseSource)
        mock_crawler.source_id = "crawler"
        mock_crawler.is_enabled = True
        mock_crawler.resolve_stream = AsyncMock(side_effect=ValueError("Mixdrop stream deleted"))

        mock_reactive = MagicMock(spec=BaseSource)
        mock_reactive.source_id = "reactive"
        mock_reactive.is_enabled = True
        mock_reactive.resolve_stream = AsyncMock(
            return_value=ResolvedMedia(
                url="https://cdn.example.com/stream.m3u8",
                mime_type="application/x-mpegURL",
                stream_format="hls",
                provider_id="reactive",
            )
        )

        manager.register_source(mock_crawler)
        manager.register_source(mock_reactive)

        resolved = await manager.resolve_stream_with_fallback(
            failing_mixdrop, alternate_sources=[backup_source]
        )
        assert resolved.url == "https://cdn.example.com/stream.m3u8"
        assert resolved.stream_format == "hls"

    @pytest.mark.asyncio
    async def test_get_details_cross_enriches_sources(self) -> None:
        """Test SourceManager.get_details cross-enriches primary reactive title with crawler sources."""
        manager = SourceManager()

        primary_movie = Movie(
            id="sc-101-oppenheimer",
            title="Oppenheimer",
            year=2023,
            catalogs=["reactive"],
            sources=[ProviderSource(id="sc_s1", media_id="sc-101-oppenheimer", provider_id="reactive", provider_name="Reactive", page_url="https://sc.test/101")],
        )

        crawler_movie = Movie(
            id="oppenheimer-hd-2023",
            title="Oppenheimer",
            year=2023,
            catalogs=["crawler"],
            source_b_url="https://cb01one.uno/oppenheimer-hd-2023/",
            sources=[
                ProviderSource(id="cb_s1", media_id="oppenheimer-hd-2023", provider_id="mixdrop", provider_name="Mixdrop", page_url="https://stayonline.pro/l/101"),
                ProviderSource(id="cb_s2", media_id="oppenheimer-hd-2023", provider_id="maxstream", provider_name="Maxstream", page_url="https://uprot.net/101"),
            ],
        )

        mock_reactive = MagicMock(spec=BaseSource)
        mock_reactive.source_id = "reactive"
        mock_reactive.is_enabled = True
        mock_reactive.get_details = AsyncMock(return_value=primary_movie)

        mock_crawler = MagicMock(spec=BaseSource)
        mock_crawler.source_id = "crawler"
        mock_crawler.is_enabled = True
        mock_crawler.search = AsyncMock(return_value=[crawler_movie])
        mock_crawler.get_details = AsyncMock(return_value=crawler_movie)

        manager.register_source(mock_reactive)
        manager.register_source(mock_crawler)

        enriched = await manager.get_details("movie", "sc-101-oppenheimer")
        assert "reactive" in enriched.catalogs
        assert "crawler" in enriched.catalogs
        assert len(enriched.sources) == 3
        provider_ids = [s.provider_id for s in enriched.sources]
        assert "reactive" in provider_ids
        assert "mixdrop" in provider_ids
        assert "maxstream" in provider_ids


class TestStreamProxyMp4Regression:
    """Anti-regression tests for StreamProxy handling MP4 direct streams."""

    def test_proxy_token_registration_mp4(self) -> None:
        """Test StreamProxy creates token for MP4 stream with custom headers."""
        media = ResolvedMedia(
            url="https://s10.mxcontent.net/v2/test_stream.mp4?token=abc",
            mime_type="video/mp4",
            stream_format="mp4",
            provider_id="mixdrop",
            headers={"User-Agent": "TestAgent/1.0", "Referer": "https://m1xdrop.net/e/123"},
        )
        proxy = StreamProxy()
        token = proxy.register_stream(media)
        assert token is not None

        retrieved = proxy.get_stream(token)
        assert retrieved is not None
        assert retrieved.url == media.url
        assert retrieved.mime_type == "video/mp4"
        assert retrieved.headers["Referer"] == "https://m1xdrop.net/e/123"
