"""Tests for Home Assistant Cast progress interpolation and BUFFERED stream type."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Self
from unittest.mock import AsyncMock, patch

import pytest

from streaming_hub.backend.ha_client import HACoreClient
from streaming_hub.backend.proxy import StreamProxy


class TestCastProgressInterpolation:
    """Test suite for Cast real-time progress interpolation and VOD buffering."""

    def setup_method(self) -> None:
        self.client = HACoreClient(token="mock_token", base_url="http://mock-ha/core/api")

    @pytest.mark.asyncio
    async def test_cast_status_interpolates_position_when_playing(self) -> None:
        """Verify that media_position is incremented by elapsed time since media_position_updated_at."""
        now = datetime.now(UTC)
        updated_at = (now - timedelta(seconds=15)).isoformat()

        mock_state = {
            "entity_id": "media_player.chromecast",
            "state": "playing",
            "attributes": {
                "media_position": 100.0,
                "media_position_updated_at": updated_at,
                "media_duration": 1800.0,
                "friendly_name": "Living Room Cast",
            },
        }

        with patch.object(self.client, "get_entity_state", new=AsyncMock(return_value=mock_state)):
            status = await self.client.get_cast_status("media_player.chromecast")
            assert status["active"] is True
            assert status["state"] == "playing"
            # Position should be approx 100 + 15 = 115s (within tolerance)
            assert 114.0 <= status["media_position"] <= 116.5
            assert status["media_duration"] == 1800.0

    @pytest.mark.asyncio
    async def test_cast_status_no_interpolation_when_paused(self) -> None:
        """Verify that media_position is NOT incremented when state is paused."""
        now = datetime.now(UTC)
        updated_at = (now - timedelta(seconds=30)).isoformat()

        mock_state = {
            "entity_id": "media_player.chromecast",
            "state": "paused",
            "attributes": {
                "media_position": 100.0,
                "media_position_updated_at": updated_at,
                "media_duration": 1800.0,
            },
        }

        with patch.object(self.client, "get_entity_state", new=AsyncMock(return_value=mock_state)):
            status = await self.client.get_cast_status("media_player.chromecast")
            assert status["active"] is True
            assert status["state"] == "paused"
            assert status["media_position"] == 100.0

    @pytest.mark.asyncio
    async def test_play_on_device_passes_buffered_stream_type(self) -> None:
        """Verify that play_on_device includes stream_type: BUFFERED in extra payload."""
        captured_payloads: list[dict[str, Any]] = []

        class MockResponse:
            status = 200

            async def text(self) -> str:
                return "OK"

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        class MockSession:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def post(self, url: str, json: dict[str, Any], **kwargs: Any) -> Any:
                captured_payloads.append(json)
                return MockResponse()

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

        with patch("aiohttp.ClientSession", MockSession):
            success, _ = await self.client.play_on_device(
                entity_id="media_player.chromecast",
                media_url="http://192.168.1.100:8099/stream/token123",
                title="Test Movie",
                poster_url="http://poster.jpg",
                mime_type="application/vnd.apple.mpegurl",
            )
            assert success is True
            assert len(captured_payloads) == 1
            payload = captured_payloads[0]
            assert "extra" in payload
            assert payload["extra"].get("stream_type") == "BUFFERED"

    def test_proxy_rewrite_m3u8_injects_vod_playlist_type(self) -> None:
        """Verify that StreamProxy injects #EXT-X-PLAYLIST-TYPE:VOD into complete playlists."""
        proxy = StreamProxy()
        raw_m3u8 = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-TARGETDURATION:10\n"
            "#EXTINF:10.0,\n"
            "seg1.ts\n"
            "#EXTINF:10.0,\n"
            "seg2.ts\n"
            "#EXT-X-ENDLIST\n"
        )
        rewritten = proxy.rewrite_m3u8(raw_m3u8, "token123", "http://example.com/playlist.m3u8")
        assert "#EXT-X-PLAYLIST-TYPE:VOD" in rewritten
