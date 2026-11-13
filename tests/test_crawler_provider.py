"""Unit tests for the Crawler (cb01) catalog parser, stream engine, and Mixdrop provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streaming_hub.backend.crawler_parser import CrawlerCatalogParser
from streaming_hub.backend.engine_crawler import CrawlerStreamClient
from streaming_hub.backend.models import ProviderSource, TvSeries
from streaming_hub.backend.providers.mixdrop import MixdropProvider


class TestCrawlerCatalogParser:
    """Test suite for parsing HTML pages from cb01."""

    def test_clean_title_and_tv_suffix(self) -> None:
        """Test clean_title properly removes dates, quality tags, and TV season suffixes."""
        clean, year, quality, _cert = CrawlerCatalogParser.clean_title("Inception (2010) [HD]")
        assert clean == "Inception"
        assert year == 2010
        assert quality == "HD"

        # TV suffix regex
        clean_tv, _, _, _ = CrawlerCatalogParser.clean_title("Breaking Bad (2008)")
        clean_tv = CrawlerCatalogParser._TV_CLEAN_SUFFIX_PATTERN.sub("", clean_tv).strip()
        assert clean_tv == "Breaking Bad"

        clean_season = CrawlerCatalogParser._TV_CLEAN_SUFFIX_PATTERN.sub(
            "", "House of the Dragon - Stagione 2"
        ).strip()
        assert clean_season == "House of the Dragon"

        clean_complete = CrawlerCatalogParser._TV_CLEAN_SUFFIX_PATTERN.sub(
            "", "The Boys - COMPLETA"
        ).strip()
        assert clean_complete == "The Boys"

        clean_subita = CrawlerCatalogParser._TV_CLEAN_SUFFIX_PATTERN.sub(
            "", "Severance - Sub-ITA"
        ).strip()
        assert clean_subita == "Severance"

    def test_parse_catalog_page_movies(self) -> None:
        """Test extracting movie cards from a catalog page."""
        html = """
        <div class="card mp-post horizontal">
            <div class="card-image">
                <a href="https://cb01one.uno/34521-oppenheimer-hd-2023.html"><img src="https://img.cb01.uno/oppenheimer.jpg" /></a>
            </div>
            <div class="card-stacked">
                <div class="card-content">
                    <h3 class="card-title"><a href="https://cb01one.uno/34521-oppenheimer-hd-2023.html">Oppenheimer (2023) [HD]</a></h3>
                    <div class="card-meta"><strong>Drammatico</strong></div>
                </div>
            </div>
        </div>
        """
        movies = CrawlerCatalogParser.parse_catalog_page(html)
        assert len(movies) == 1
        m = movies[0]
        assert m.id == "34521-oppenheimer-hd-2023.html"
        assert m.title == "Oppenheimer"
        assert m.year == 2023
        assert m.poster_url == "https://img.cb01.uno/oppenheimer.jpg"
        assert "Drammatico" in m.genres

    def test_parse_sources_table_and_tabs(self) -> None:
        """Test parsing sources from HTML table and tabs-catch-all elements."""
        html = """
        <table class="cbtable">
            <tr>
                <td><u><strong>Streaming HD:</strong></u></td>
                <td>
                    <a href="https://stayonline.pro/l/133528/">Mixdrop HD</a>
                    <a href="https://uprot.net/ms/54321/">Maxstream HD</a>
                </td>
            </tr>
            <tr>
                <td><u><strong>Download HD:</strong></u></td>
                <td><a href="https://torrent.example.com">Torrent</a></td>
            </tr>
        </table>
        <div class="tabs-catch-all" data-src="https://stayonline.pro/l/133528/">Mixdrop</div>
        """
        sources = CrawlerCatalogParser.parse_sources(html, media_id="oppenheimer")
        assert len(sources) >= 2
        # Prioritized Mixdrop over Maxstream and labeled as Crawler
        assert sources[0].provider_id == "mixdrop"
        assert sources[0].provider_name == "Crawler"
        assert sources[0].quality == "HD"
        assert sources[0].page_url == "https://stayonline.pro/l/133528/"

        maxstream_src = [s for s in sources if s.provider_id == "maxstream"]
        assert len(maxstream_src) == 1
        assert maxstream_src[0].provider_name == "Crawler (Alt)"
        assert maxstream_src[0].page_url == "https://uprot.net/ms/54321/"

    def test_parse_tv_series_page(self) -> None:
        """Test parsing a TV series details page with seasons and episodes."""
        html = """
        <title>Stranger Things - Serie TV</title>
        <meta property="og:description" content="A Hawkins un ragazzino scompare..." />
        <meta property="og:image" content="https://img.cb01.uno/stranger.jpg" />
        <div class="sp-wrap">
            <div class="sp-head">STAGIONE 1 (ITA)</div>
            <div class="sp-body">
                <p>1x01 Capitolo Uno &ndash; <a href="https://stayonline.pro/l/901/">Mixdrop</a></p>
                <p>1x02 Capitolo Due &ndash; <a href="https://stayonline.pro/l/902/">Mixdrop</a></p>
            </div>
        </div>
        """
        series = CrawlerCatalogParser.parse_tv_series_page(html, series_url="https://cb01one.uno/serietv/stranger-things/")
        assert series.title == "Stranger Things"
        assert series.poster_url == "https://img.cb01.uno/stranger.jpg"
        assert len(series.seasons) == 1
        s1 = series.seasons[0]
        assert s1.number == 1
        assert len(s1.episodes) == 2
        ep1 = s1.episodes[0]
        assert ep1.episode_number == 1
        assert len(ep1.sources) == 1
        assert ep1.sources[0].provider_id == "mixdrop"
        assert ep1.sources[0].provider_name == "Crawler"
        assert ep1.sources[0].page_url == "https://stayonline.pro/l/901/"


class TestMixdropProvider:
    """Test suite for Mixdrop provider unpacking and resolution."""

    def test_dean_edwards_unpacking(self) -> None:
        """Test unpack_packer correctly unpacks packed JavaScript with radix 62."""
        packed = (
            'eval(function(p,a,c,k,e,d){return p}'
            '("0 1 = \\"//2.3.4/5.6?s=xyz&e=789\\";",7,7,'
            '"MDCore|wurl|s42|mxcontent|net|test1234|mp4".split("|"),0,{}))'
        )
        unpacked = MixdropProvider.unpack_packer(packed)
        assert "MDCore wurl =" in unpacked
        assert "//s42.mxcontent.net/test1234.mp4?s=xyz&e=789" in unpacked

    def test_extract_stream_url_from_packed_html(self) -> None:
        """Test _extract_stream_url locates stream within packed script in HTML."""
        html = """
        <html>
        <head><title>Mixdrop Player</title></head>
        <body>
        <script type="text/javascript">
        eval(function(p,a,c,k,e,d){return p}("MDCore.0 = \\"//s52.mxcontent.net/v2/movie_file.mp4?s=token123&e=99999\\";",7,7,"wurl|MDCore|s1|mxcontent|net|test|mp4".split("|"),0,{}))
        </script>
        </body>
        </html>
        """
        provider = MixdropProvider()
        stream_url = provider._extract_stream_url(html, "https://m1xdrop.net/e/abc123xyz")
        assert stream_url == "https://s52.mxcontent.net/v2/movie_file.mp4?s=token123&e=99999"

    @pytest.mark.asyncio
    async def test_resolve_stayonline_to_mixdrop(self) -> None:
        """Test full resolution from stayonline.pro AJAX to Mixdrop embed and direct mp4 stream."""
        provider = MixdropProvider()
        source = ProviderSource(
            id="src_1",
            media_id="movie_1",
            provider_id="mixdrop",
            provider_name="Mixdrop",
            page_url="https://stayonline.pro/l/133528/",
            quality="HD",
        )

        class MockAsyncContext:
            def __init__(self, obj):
                self._obj = obj

            async def __aenter__(self):
                return self._obj

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        # 1. stayonline GET response
        get_stayonline_resp = MagicMock()
        get_stayonline_resp.text = AsyncMock(return_value='<div data-id="133528"></div>')

        # 2. stayonline linkView.php AJAX POST response
        post_ajax_resp = MagicMock()
        post_ajax_resp.status = 200
        post_ajax_resp.json = AsyncMock(return_value={
            "status": 200,
            "data": {"value": "https://m1xdrop.net/f/abc123xyz"},
        })

        # 3. Mixdrop embed GET response
        get_embed_resp = MagicMock()
        get_embed_resp.status = 200
        get_embed_resp.text = AsyncMock(return_value="""
        <script>
        eval(function(p,a,c,k,e,d){return p}("MDCore.0 = \\"//s10.mxcontent.net/v2/stream.mp4?s=abc&e=123\\";",7,7,"wurl|MDCore|s1|mxcontent|net|test|mp4".split("|"),0,{}))
        </script>
        """)

        mock_session = MagicMock()

        def mock_get(url, **kwargs):
            if "stayonline.pro" in url:
                return MockAsyncContext(get_stayonline_resp)
            return MockAsyncContext(get_embed_resp)

        def mock_post(url, **kwargs):
            return MockAsyncContext(post_ajax_resp)

        mock_session.get.side_effect = mock_get
        mock_session.post.side_effect = mock_post

        resolved = await provider.resolve(source, mock_session)
        assert resolved.url == "https://s10.mxcontent.net/v2/stream.mp4?s=abc&e=123"
        assert resolved.mime_type == "video/mp4"
        assert resolved.stream_format == "mp4"
        assert resolved.provider_id == "mixdrop"
        assert resolved.headers.get("Referer") == "https://m1xdrop.net/e/abc123xyz"


class TestCrawlerStreamClient:
    """Test suite for CrawlerStreamClient request routing."""

    @pytest.mark.asyncio
    async def test_get_latest_tv_routing(self) -> None:
        """Test get_latest_tv targets /serietv/ instead of 404 category."""
        client = CrawlerStreamClient(base_url="https://cb01one.uno")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html></html>"
            with patch.object(CrawlerCatalogParser, "parse_catalog_page", return_value=[]):
                # Page 1
                await client.get_latest_tv(page=1)
                mock_req.assert_called_with("https://cb01one.uno/serietv/")

                # Page 2
                await client.get_latest_tv(page=2)
                mock_req.assert_called_with("https://cb01one.uno/serietv/page/2/")

    @pytest.mark.asyncio
    async def test_get_tv_series_slug_routing(self) -> None:
        """Test get_tv_series prepends serietv/ for relative slugs."""
        client = CrawlerStreamClient(base_url="https://cb01one.uno")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html></html>"
            with patch.object(
                CrawlerCatalogParser,
                "parse_tv_series_page",
                return_value=TvSeries(
                    id="severance",
                    title="Severance",
                    year=2022,
                    poster_url=None,
                    description=None,
                    genres=[],
                    source_b_url="https://cb01one.uno/serietv/severance/",
                    catalogs=["crawler"],
                    seasons=[],
                ),
            ):
                await client.get_tv_series("severance")
                mock_req.assert_called_with("https://cb01one.uno/serietv/severance/")

    @pytest.mark.asyncio
    async def test_search_queries_movies_and_series(self) -> None:
        """Test search runs concurrent queries across both movies and TV series."""
        client = CrawlerStreamClient(base_url="https://cb01one.uno")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html></html>"
            with patch.object(CrawlerCatalogParser, "parse_catalog_page", return_value=[]):
                _ = await client.search("alien")
                assert mock_req.call_count == 2
                called_urls = {call.args[0] for call in mock_req.call_args_list}
                assert "https://cb01one.uno/?s=alien" in called_urls
                assert "https://cb01one.uno/serietv/?s=alien" in called_urls
