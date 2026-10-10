"""HTTP Media Stream Proxy and HLS playlist rewriter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
import re
import secrets
import urllib.parse

import aiohttp
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from .models import ResolvedMedia

_LOGGER = logging.getLogger(__name__)


@dataclass
class StreamSession:
    """Active streaming session with target URL and required headers."""

    token: str
    url: str
    headers: dict[str, str]
    mime_type: str
    created_at: datetime
    expires_at: datetime
    remux_audio: bool = False


class StreamProxy:
    """In-memory manager for proxied media streams."""

    def __init__(self, ttl_seconds: int = 14400) -> None:
        """Initialize the stream proxy manager."""
        self.ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[str, StreamSession] = {}
        self._http_session: aiohttp.ClientSession | None = None

    async def _get_client_session(self) -> aiohttp.ClientSession:
        """Get or initialize aiohttp ClientSession."""
        if self._http_session and not self._http_session.closed:
            return self._http_session
        self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        """Close client session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    def register_stream(self, resolved: ResolvedMedia, remux_audio: bool = False) -> str:
        """Register a resolved media stream and return a secure access token."""
        self._purge_expired()
        token = secrets.token_urlsafe(16)
        now = datetime.now(UTC)
        headers = dict(resolved.headers) if resolved.headers else {}

        mime_type = "video/mp4" if remux_audio else (resolved.mime_type or "application/vnd.apple.mpegurl")

        session = StreamSession(
            token=token,
            url=resolved.url,
            headers=headers,
            mime_type=mime_type,
            created_at=now,
            expires_at=now + self.ttl,
            remux_audio=remux_audio,
        )
        self._sessions[token] = session
        return token

    def get_stream(self, token: str) -> StreamSession | None:
        """Retrieve a stream session if active and unexpired."""
        session = self._sessions.get(token)
        if not session:
            return None
        if datetime.now(UTC) > session.expires_at:
            self._sessions.pop(token, None)
            return None
        return session

    def _purge_expired(self) -> None:
        """Remove all expired stream sessions."""
        now = datetime.now(UTC)
        expired = [token for token, sess in self._sessions.items() if now > sess.expires_at]
        for token in expired:
            self._sessions.pop(token, None)

    def rewrite_m3u8(self, text: str, base_url: str, token: str, root_path: str = "") -> str:
        """Rewrite M3U8 playlist URIs to point to proxy endpoints."""
        lines = text.splitlines()
        rewritten: list[str] = []

        prefix = root_path.rstrip("/")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                rewritten.append(line)
                continue

            if stripped.startswith("#"):
                if 'URI="' in stripped:

                    def _replace_uri(match: re.Match[str]) -> str:
                        orig = match.group(1)
                        abs_uri = urllib.parse.urljoin(base_url, orig)
                        lower_orig = orig.lower()
                        is_playlist = (
                            ".m3u8" in lower_orig
                            or "playlist" in lower_orig
                            or "rendition=" in lower_orig
                            or "type=audio" in lower_orig
                            or "type=subtitle" in lower_orig
                            or "type=subtitles" in lower_orig
                            or "type=video" in lower_orig
                        )
                        endpoint = "stream" if is_playlist else "segment"
                        proxy_uri = f"{prefix}/{endpoint}/{token}?url={urllib.parse.quote(abs_uri, safe='')}"
                        return f'URI="{proxy_uri}"'

                    line = re.sub(r'URI=["\']([^"\']+)["\']', _replace_uri, stripped)
                rewritten.append(line)
            else:
                abs_uri = urllib.parse.urljoin(base_url, stripped)
                lower_stripped = stripped.lower()
                is_playlist = (
                    ".m3u8" in lower_stripped
                    or "playlist" in lower_stripped
                    or "rendition=" in lower_stripped
                    or "type=video" in lower_stripped
                    or "type=audio" in lower_stripped
                    or "type=subtitle" in lower_stripped
                    or "type=subtitles" in lower_stripped
                )
                endpoint = "stream" if is_playlist else "segment"
                proxy_uri = f"{prefix}/{endpoint}/{token}?url={urllib.parse.quote(abs_uri, safe='')}"
                rewritten.append(proxy_uri)

        has_extinf = any(line.startswith("#EXTINF") for line in lines)
        has_playlist_type = any(line.startswith("#EXT-X-PLAYLIST-TYPE") for line in lines)
        has_endlist = any(line.startswith("#EXT-X-ENDLIST") for line in lines)
        if has_extinf and has_endlist and not has_playlist_type:
            for idx, r_line in enumerate(rewritten):
                if r_line.strip().startswith("#EXTM3U"):
                    rewritten.insert(idx + 1, "#EXT-X-PLAYLIST-TYPE:VOD")
                    break

        return "\n".join(rewritten)

    async def get_stream_response(
        self,
        token: str,
        target_url: str | None = None,
        root_path: str = "",
        headers_override: dict[str, str] | None = None,
        method: str = "GET",
    ) -> Response:
        """Fetch and rewrite master or media HLS playlist with HEAD support."""
        session = self.get_stream(token)
        if not session:
            raise HTTPException(status_code=404, detail="Stream session not found or expired")

        actual_url = target_url or session.url
        client = await self._get_client_session()

        headers = dict(session.headers)
        if headers_override:
            for k in ("Range", "range", "Accept-Encoding"):
                if k in headers_override:
                    headers[k] = headers_override[k]

        try:
            async with client.get(
                actual_url,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as upstream:
                if upstream.status >= 400:
                    if upstream.status == 403:
                        _LOGGER.error(
                            "Stream access denied (403) by CDN/Upstream for %s. Causa Nota: Token scaduto, firma non valida o parametro h=1 mancante.",
                            actual_url,
                        )
                    elif upstream.status == 404:
                        _LOGGER.error(
                            "Stream not found (404) by CDN/Upstream for %s. Causa Nota: Il contenuto potrebbe essere stato rimosso o l'URL è errato.",
                            actual_url,
                        )
                    else:
                        _LOGGER.error("Upstream returned HTTP %s for stream %s.", upstream.status, actual_url)

                    raise HTTPException(
                        status_code=upstream.status,
                        detail=f"Upstream returned HTTP {upstream.status}",
                    )

                if method.upper() == "HEAD":
                    return Response(
                        status_code=upstream.status,
                        media_type="application/vnd.apple.mpegurl",
                        headers={
                            "Cache-Control": "no-cache, no-store, must-revalidate",
                            "Access-Control-Allow-Origin": "*",
                        },
                    )

                raw_text = await upstream.text()
                rewritten = self.rewrite_m3u8(raw_text, str(upstream.url), token, root_path=root_path)

                return Response(
                    content=rewritten,
                    media_type="application/vnd.apple.mpegurl",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Access-Control-Allow-Origin": "*",
                    },
                )
        except HTTPException:
            raise
        except Exception as err:
            _LOGGER.error("Error fetching upstream stream %s: %s", actual_url, err)
            raise HTTPException(status_code=502, detail=f"Bad Gateway: {err}")

    async def get_segment_response(
        self,
        token: str,
        segment_url: str,
        headers_override: dict[str, str] | None = None,
        root_path: str = "",
        method: str = "GET",
    ) -> Response | StreamingResponse:
        """Proxy binary TS or M4S chunk with range headers, delegating playlists to get_stream_response."""
        session = self.get_stream(token)
        if not session:
            raise HTTPException(status_code=404, detail="Stream session not found or expired")

        # If this URL is actually an HLS sub-playlist, delegate to get_stream_response
        lower_url = segment_url.lower()
        if (
            ".m3u8" in lower_url
            or "playlist" in lower_url
            or "rendition=" in lower_url
            or "type=video" in lower_url
            or "type=audio" in lower_url
            or "type=subtitle" in lower_url
            or "type=subtitles" in lower_url
        ):
            return await self.get_stream_response(
                token, target_url=segment_url, root_path=root_path, headers_override=headers_override, method=method
            )

        client = await self._get_client_session()

        upstream_headers = dict(session.headers)
        if headers_override and "range" in headers_override:
            upstream_headers["Range"] = headers_override["range"]
        elif headers_override and "Range" in headers_override:
            upstream_headers["Range"] = headers_override["Range"]

        upstream_resp = None
        for attempt in range(2):
            try:
                upstream_resp = await client.get(
                    segment_url,
                    headers=upstream_headers,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=25),
                )
                if upstream_resp.status < 500:
                    break
                # Upstream server error, retry once
                upstream_resp.close()
                await asyncio.sleep(0.3)
            except Exception as err:
                if attempt == 1:
                    raise HTTPException(status_code=502, detail=f"Segment fetch error: {err}")
                await asyncio.sleep(0.3)

        if not upstream_resp:
            raise HTTPException(status_code=502, detail="Failed to fetch segment from upstream")

        try:
            status_code = upstream_resp.status
            if status_code >= 400:
                upstream_resp.close()
                if status_code == 403:
                    if ".key" in lower_url:
                        _LOGGER.error(
                            "AES Key access denied (403). Causa Nota: Il provider blocca il download della chiave (es. Referer mancante o CORS). Chromecast fallira'."
                        )
                    else:
                        _LOGGER.error(
                            "Segment access denied (403) for %s. Causa Nota: Token scaduto o leech protection attivata.",
                            segment_url,
                        )
                elif status_code == 404:
                    _LOGGER.error("Segment/Key not found (404) for %s.", segment_url)
                else:
                    _LOGGER.error("Upstream returned HTTP %s for segment %s", status_code, segment_url)

                raise HTTPException(
                    status_code=status_code,
                    detail=f"Upstream returned HTTP {status_code}",
                )

            raw_content_type = upstream_resp.headers.get("Content-Type", "")

            # Classify content type according to segment format
            if lower_url.endswith(".key") or "/enc.key" in lower_url or ".key?" in lower_url:
                content_type = "application/octet-stream"
            elif lower_url.endswith(".vtt") or ".vtt?" in lower_url or "subs-" in lower_url:
                content_type = "text/vtt"
            elif ".m4s" in lower_url or ".mp4" in lower_url:
                content_type = "video/mp4"
            elif raw_content_type.lower().startswith("text/") or not raw_content_type:
                # CDN disguised media chunk (e.g. video/audio chunk disguised as .html)
                content_type = "video/MP2T"
            else:
                content_type = raw_content_type

            out_headers: dict[str, str] = {
                "Content-Type": content_type,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=3600",
            }

            # Forward Content-Range and Accept-Ranges
            for header_name in ("Content-Range", "Accept-Ranges"):
                if header_name in upstream_resp.headers:
                    out_headers[header_name] = upstream_resp.headers[header_name]

            # If client made a HEAD request (e.g. Philips TV or Chromecast probing chunk)
            if method.upper() == "HEAD":
                upstream_resp.close()
                # Forward Content-Length from upstream so ExoPlayer / Cast does not receive length 0
                if "Content-Length" in upstream_resp.headers:
                    out_headers["Content-Length"] = upstream_resp.headers["Content-Length"]
                return Response(
                    status_code=status_code,
                    headers=out_headers,
                    media_type=content_type,
                )

            raw_bytes = await upstream_resp.read()
            upstream_resp.close()

            # Check if upstream returned a text M3U8 playlist
            if b"#EXTM3U" in raw_bytes[:512]:
                raw_text = raw_bytes.decode("utf-8", errors="replace")
                rewritten = self.rewrite_m3u8(raw_text, str(upstream_resp.url), token, root_path=root_path)
                return Response(
                    content=rewritten,
                    media_type="application/vnd.apple.mpegurl",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Access-Control-Allow-Origin": "*",
                    },
                )

            # Refine media content type based on binary signature if applicable
            if not (
                lower_url.endswith(".key")
                or "/enc.key" in lower_url
                or ".key?" in lower_url
                or lower_url.endswith(".vtt")
                or ".vtt?" in lower_url
            ):
                if raw_bytes.startswith(b"\x00\x00\x00") or b"ftyp" in raw_bytes[:32]:
                    content_type = "video/mp4"
                elif b"WEBVTT" in raw_bytes[:32]:
                    content_type = "text/vtt"
                elif content_type.lower().startswith("text/"):
                    content_type = "video/MP2T"
                out_headers["Content-Type"] = content_type

            out_headers["Content-Length"] = str(len(raw_bytes))

            return Response(
                content=raw_bytes,
                status_code=status_code,
                headers=out_headers,
                media_type=content_type,
            )
        except HTTPException:
            raise
        except Exception as err:
            _LOGGER.error("Error fetching segment %s: %s", segment_url, err)
            raise HTTPException(status_code=502, detail=f"Bad Gateway: {err}")
