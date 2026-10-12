"""DNS-over-HTTPS (DoH) and custom DNS resolver for Streaming Hub."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import logging
import socket
from typing import Any
import urllib.request

import aiohttp
from aiohttp.abc import AbstractResolver

_LOGGER = logging.getLogger(__name__)

DNS_SYSTEM = "system"
DNS_CLOUDFLARE = "cloudflare"
DNS_GOOGLE = "google"
DNS_QUAD9 = "quad9"
DNS_DEFAULT = DNS_CLOUDFLARE

CLOUDFLARE_DOH_URL = "https://1.1.1.1/dns-query"
GOOGLE_DOH_URL = "https://8.8.8.8/resolve"
QUAD9_DOH_URL = "https://9.9.9.9/dns-query"

# Shared global cache across all resolver instances
_GLOBAL_DNS_CACHE: dict[str, tuple[list[str], datetime]] = {}
_CACHE_TTL = timedelta(hours=12)


class DoHResolver(AbstractResolver):
    """Custom aiohttp resolver supporting DNS-over-HTTPS with concurrent race and Quad9."""

    def __init__(self, mode: str = DNS_DEFAULT, provider: str | None = None) -> None:
        """Initialize DoH resolver with mode or legacy provider parameter."""
        self.mode = provider if provider is not None else mode

    def get_connector(self, ssl: bool | None = False) -> aiohttp.TCPConnector:
        """Return an aiohttp TCPConnector configured with this resolver."""
        if ssl is not None:
            return aiohttp.TCPConnector(resolver=self, ssl=ssl)
        return aiohttp.TCPConnector(resolver=self)

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET) -> list[dict[str, Any]]:
        """Resolve a host name to a list of socket address dictionaries."""
        if self.mode == DNS_SYSTEM:
            return await self._resolve_system_once(host, port, family)

        # Check global cache
        now = datetime.now(UTC)
        if host in _GLOBAL_DNS_CACHE:
            ips, timestamp = _GLOBAL_DNS_CACHE[host]
            if now - timestamp < _CACHE_TTL:
                return self._format_results(host, ips, port, family)

        # Resolve via DoH racing
        ips = await self._resolve_doh(host)
        if ips:
            _GLOBAL_DNS_CACHE[host] = (ips, now)
            return self._format_results(host, ips, port, family)

        # Fallback to system DNS once
        _LOGGER.debug("DoH lookup failed for %s, falling back to system DNS", host)
        try:
            return await self._resolve_system_once(host, port, family)
        except OSError:
            if host in _GLOBAL_DNS_CACHE:
                stale_ips, _ = _GLOBAL_DNS_CACHE[host]
                _LOGGER.warning("Using stale DNS cache for %s: %s", host, stale_ips)
                return self._format_results(host, stale_ips, port, family)
            raise

    async def _resolve_doh(self, host: str) -> list[str]:
        """Query DoH endpoints concurrently and return first valid list of A records."""
        try:
            socket.inet_aton(host)
        except OSError:
            pass
        else:
            return [host]

        tasks = []
        if self.mode == DNS_CLOUDFLARE:
            tasks.append(asyncio.to_thread(self._query_cloudflare, host))
            tasks.append(asyncio.to_thread(self._query_google, host))
        elif self.mode == DNS_GOOGLE:
            tasks.append(asyncio.to_thread(self._query_google, host))
            tasks.append(asyncio.to_thread(self._query_cloudflare, host))
        elif self.mode == DNS_QUAD9:
            tasks.append(asyncio.to_thread(self._query_quad9, host))
            tasks.append(asyncio.to_thread(self._query_cloudflare, host))
        else:
            tasks.append(asyncio.to_thread(self._query_cloudflare, host))
            tasks.append(asyncio.to_thread(self._query_google, host))

        for coro in asyncio.as_completed(tasks, timeout=3.0):
            try:
                ips = await coro
                if ips:
                    return ips
            except Exception as err:
                _LOGGER.debug("DoH query error for %s: %s", host, err)

        return []

    def _query_cloudflare(self, host: str) -> list[str]:
        """Fetch A records via Cloudflare DoH JSON API."""
        url = f"{CLOUDFLARE_DOH_URL}?name={host}&type=A"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/dns-json", "User-Agent": "StreamingHub-DoH/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            return [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]

    def _query_google(self, host: str) -> list[str]:
        """Fetch A records via Google DoH JSON API."""
        url = f"{GOOGLE_DOH_URL}?name={host}&type=A"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/dns-json", "User-Agent": "StreamingHub-DoH/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            return [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]

    def _query_quad9(self, host: str) -> list[str]:
        """Fetch A records via Quad9 DoH JSON API."""
        url = f"{QUAD9_DOH_URL}?name={host}&type=A"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/dns-json", "User-Agent": "StreamingHub-DoH/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            return [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]

    async def _resolve_system_once(self, host: str, port: int, family: int) -> list[dict[str, Any]]:
        """Resolve host using standard getaddrinfo."""
        loop = asyncio.get_running_loop()
        addr_infos = await loop.getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        results = []
        for family_, type_, proto, _cname, sockaddr in addr_infos:
            results.append(
                {
                    "hostname": host,
                    "host": sockaddr[0],
                    "port": sockaddr[1],
                    "family": family_,
                    "proto": proto,
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        return results

    def _format_results(self, host: str, ips: list[str], port: int, family: int) -> list[dict[str, Any]]:
        """Format IP list into aiohttp resolver result format."""
        return [
            {
                "hostname": host,
                "host": ip,
                "port": port,
                "family": family,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
            for ip in ips
        ]

    async def close(self) -> None:
        """Close resolver resources."""
