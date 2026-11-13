"""Mixdrop streaming provider adapter."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import aiohttp

from ..models import ProviderSource, ResolvedMedia
from .base import StreamingProvider

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class MixdropProvider(StreamingProvider):
    """Provider for Mixdrop video streams."""

    @property
    def provider_id(self) -> str:
        """Provider ID."""
        return "mixdrop"

    @property
    def display_name(self) -> str:
        """Display Name."""
        return "Mixdrop"

    async def can_handle(self, url: str) -> bool:
        """Check if this provider handles the URL."""
        lower = url.lower()
        return "mixdrop" in lower or "m1xdrop" in lower or "stayonline.pro" in lower

    async def resolve(
        self,
        source: ProviderSource,
        session: aiohttp.ClientSession,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve Mixdrop source to a playable stream URL."""
        target_url = source.page_url
        parsed_origin = urlparse(target_url)
        referer = f"{parsed_origin.scheme}://{parsed_origin.netloc}/" if parsed_origin.netloc else target_url

        if "stayonline.pro" in target_url:
            link_id_match = re.search(r"/l/([^/?#]+)", target_url)
            link_id = link_id_match.group(1) if link_id_match else None

            # Optional pre-fetch to acquire cookies or parse data-id
            page_headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": referer,
            }
            try:
                async with session.get(
                    target_url, headers=page_headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    page_html = await resp.text()
                    if not link_id:
                        data_id_match = re.search(r'data-id=["\']([^"\']+)["\']', page_html)
                        if data_id_match:
                            link_id = data_id_match.group(1)
            except Exception as err:
                _LOGGER.debug("Failed initial GET on stayonline.pro (%s): %s", target_url, err)

            if link_id:
                ajax_url = urljoin(target_url, "/ajax/linkView.php")
                ajax_headers = {
                    "User-Agent": USER_AGENT,
                    "Referer": target_url,
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                }
                async with session.post(
                    ajax_url,
                    data={"id": link_id, "ref": referer},
                    headers=ajax_headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as ajax_resp:
                    if ajax_resp.status == 200:
                        try:
                            ajax_json = await ajax_resp.json(content_type=None)
                            if isinstance(ajax_json, dict):
                                data_val = ajax_json.get("data")
                                if isinstance(data_val, dict):
                                    target_url = data_val.get("value") or target_url
                                elif isinstance(data_val, str):
                                    target_url = data_val
                                elif "url" in ajax_json:
                                    target_url = ajax_json["url"]
                                elif "value" in ajax_json:
                                    target_url = ajax_json["value"]
                        except Exception:
                            ajax_text = await ajax_resp.text()
                            url_match = re.search(r'https?://[^\s"\'<>]+(?:m1xdrop|mixdrop)[^\s"\'<>]+', ajax_text)
                            if url_match:
                                target_url = url_match.group(0)

        # Normalize escaped slashes
        target_url = target_url.replace(r"\/", "/")

        # Convert /f/ or /v/ to /e/ embed URL for Mixdrop
        if "mixdrop" in target_url.lower() or "m1xdrop" in target_url.lower():
            target_url = re.sub(r"/(?:f|v)/", "/e/", target_url)

        embed_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://stayonline.pro/",
        }
        async with session.get(
            target_url, headers=embed_headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"Mixdrop returned status {resp.status} for {target_url}")
            html_text = await resp.text()

        stream_url = self._extract_stream_url(html_text, target_url)
        if not stream_url:
            raise ValueError(f"Could not extract playable media from Mixdrop ({target_url})")

        mime_type = "application/x-mpegURL" if ".m3u8" in stream_url else "video/mp4"
        stream_format = "hls" if ".m3u8" in stream_url else "mp4"

        return ResolvedMedia(
            url=stream_url,
            mime_type=mime_type,
            stream_format=stream_format,
            provider_id=self.provider_id,
            headers={"User-Agent": USER_AGENT, "Referer": target_url},
        )

    @staticmethod
    def _int_to_base(n: int, base: int) -> str:
        """Convert integer to base-N string (radix 2..62)."""
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if n == 0:
            return alphabet[0]
        digits = []
        while n > 0:
            digits.append(alphabet[n % base])
            n //= base
        return "".join(reversed(digits))

    @classmethod
    def unpack_packer(cls, packed: str) -> str:
        """Unpack Dean Edwards packed JavaScript code."""
        eval_idx = packed.find("eval(function(")
        if eval_idx == -1:
            return packed

        tail = packed[eval_idx:]
        split_match = re.search(r",\s*(\d+)\s*,\s*(\d+)\s*,\s*([\"\'])(.*?)\3\s*\.split\(\s*([\"\'])\|", tail)
        if not split_match:
            return packed

        radix = int(split_match.group(1))
        count = int(split_match.group(2))
        symtab = split_match.group(4).split("|")

        brace_idx = tail.find("}")
        if brace_idx == -1:
            return packed

        paren_idx = tail.find("(", brace_idx)
        if paren_idx == -1:
            return packed

        raw_payload = tail[paren_idx + 1 : split_match.start()].strip()
        if raw_payload.endswith(","):
            raw_payload = raw_payload[:-1].strip()
        if (raw_payload.startswith('"') and raw_payload.endswith('"')) or (
            raw_payload.startswith("'") and raw_payload.endswith("'")
        ):
            raw_payload = raw_payload[1:-1]

        lookup = {
            cls._int_to_base(i, radix): symtab[i]
            for i in range(min(count, len(symtab)))
            if symtab[i]
        }
        unpacked = re.sub(r"\b\w+\b", lambda m: lookup.get(m.group(0), m.group(0)), raw_payload)
        return unpacked.replace(r"\"", '"').replace(r"\'", "'").replace(r"\/", "/")

    @classmethod
    def _unpack_all_packers(cls, html_text: str) -> list[str]:
        """Find and unpack all Dean Edwards packed scripts in the text."""
        unpacked_list: list[str] = []
        idx = 0
        while True:
            eval_idx = html_text.find("eval(function(", idx)
            if eval_idx == -1:
                break
            script = html_text[eval_idx : eval_idx + 12000]
            unpacked = cls.unpack_packer(script)
            if unpacked != script:
                unpacked_list.append(unpacked)
            idx = eval_idx + len("eval(function(")
        return unpacked_list

    def _extract_stream_url(self, html_text: str, base_url: str) -> str | None:
        """Extract media URL from page HTML or embedded packed script."""
        candidates = [html_text]
        candidates.extend(self._unpack_all_packers(html_text))

        patterns = [
            r'(?:MDCore\.wurl|wurl)\s*=\s*["\']*(https?://[^\s"\'<>]+|//[^\s"\'<>]+)',
            r'<source[^>]*src=["\'](https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)["\']',
            r'["\'](https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)["\']',
            r'["\'](//[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)["\']',
        ]
        for candidate in candidates:
            for pat in patterns:
                match = re.search(pat, candidate, re.IGNORECASE)
                if match:
                    url = match.group(1).rstrip("\"';\\")
                    if url.startswith("//"):
                        url = "https:" + url
                    return urljoin(base_url, url)

        return None
