"""Unit tests for StreamProxy DoH support and image proxy fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from fastapi import HTTPException
import pytest

from streaming_hub.backend.main import FALLBACK_POSTER_SVG, proxy_image
from streaming_hub.backend.proxy import StreamProxy


class TestStreamProxyDoH:
    """Test suite verifying StreamProxy custom DNS and DoH resolution."""

    @pytest.mark.asyncio
    async def test_stream_proxy_initializes_with_doh(self) -> None:
        proxy = StreamProxy(custom_dns="cloudflare")
        session = await proxy._get_client_session()
        try:
            assert proxy.custom_dns == "cloudflare"
            assert proxy._resolver is not None
            assert proxy._resolver.mode == "cloudflare"
            assert isinstance(session.connector, aiohttp.TCPConnector)
        finally:
            await proxy.close()

    @pytest.mark.asyncio
    async def test_stream_proxy_system_dns_mode(self) -> None:
        proxy = StreamProxy(custom_dns="system")
        session = await proxy._get_client_session()
        try:
            assert proxy.custom_dns == "system"
            assert proxy._resolver is None
            assert isinstance(session.connector, aiohttp.TCPConnector)
        finally:
            await proxy.close()

    @pytest.mark.asyncio
    async def test_stream_proxy_set_custom_dns_updates_session(self) -> None:
        proxy = StreamProxy(custom_dns="system")
        await proxy._get_client_session()
        old_session = proxy._http_session

        proxy.set_custom_dns("google")
        assert proxy.custom_dns == "google"
        assert proxy._http_session is None

        new_session = await proxy._get_client_session()
        try:
            assert proxy._resolver is not None
            assert proxy._resolver.mode == "google"
            assert new_session is not old_session
        finally:
            await proxy.close()


class TestProxyImageEndpoint:
    """Test suite for /api/proxy/image endpoint resilience and fallbacks."""

    @pytest.mark.asyncio
    async def test_proxy_image_invalid_url_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await proxy_image(url="ftp://invalid-url.com/pic.jpg")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_proxy_image_success_returns_image_bytes(self) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"fake-image-bytes")
        mock_response.headers = {"Content-Type": "image/webp"}

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("streaming_hub.backend.main.stream_proxy._get_client_session", AsyncMock(return_value=mock_session)):
            resp = await proxy_image(url="https://streamingcommunityz.photos/images/poster.webp")
            assert resp.status_code == 200
            assert resp.body == b"fake-image-bytes"
            assert resp.media_type == "image/webp"

    @pytest.mark.asyncio
    async def test_proxy_image_fallback_removes_cdn_on_dns_failure(self) -> None:
        """When cdn.domain fails with DNS error, fallback to apex domain without cdn."""
        mock_fail = MagicMock()
        mock_fail.status = 502

        mock_ok = MagicMock()
        mock_ok.status = 200
        mock_ok.read = AsyncMock(return_value=b"recovered-image-bytes")
        mock_ok.headers = {"Content-Type": "image/webp"}

        # Simulate first call (cdn.) raising ClientConnectorDNSError, second call (apex) succeeding
        def side_effect(url, **kwargs):
            cm = MagicMock()
            if "://cdn." in url:
                cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("DNS error")))
            else:
                cm.__aenter__ = AsyncMock(return_value=mock_ok)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        mock_session = MagicMock()
        mock_session.get.side_effect = side_effect

        with patch("streaming_hub.backend.main.stream_proxy._get_client_session", AsyncMock(return_value=mock_session)):
            resp = await proxy_image(url="https://cdn.streamingcommunityz.photos/images/poster.webp")
            assert resp.status_code == 200
            assert resp.body == b"recovered-image-bytes"
            assert resp.media_type == "image/webp"

    @pytest.mark.asyncio
    async def test_proxy_image_returns_svg_placeholder_on_total_failure(self) -> None:
        """When all candidates fail, returns neutral SVG placeholder instead of 502."""
        mock_session = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Host unreachable")))
        cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = cm

        with patch("streaming_hub.backend.main.stream_proxy._get_client_session", AsyncMock(return_value=mock_session)):
            resp = await proxy_image(url="https://broken-mirror.photos/images/missing.webp")
            assert resp.status_code == 200
            assert resp.media_type == "image/svg+xml"
            assert FALLBACK_POSTER_SVG.encode("utf-8") == resp.body
