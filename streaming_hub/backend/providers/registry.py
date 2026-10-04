"""Provider registry and resolver pipeline for media streams."""

from __future__ import annotations

import logging

import aiohttp

from ..models import ProviderSource, ResolvedMedia
from .base import StreamingProvider
from .maxstream import MaxstreamProvider
from .mixdrop import MixdropProvider
from .reactive_provider import ReactiveStreamProvider

_LOGGER = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry managing streaming providers and resolution order."""

    def __init__(self, reactive_client=None) -> None:
        """Initialize provider registry with default adapters."""
        self._providers: dict[str, StreamingProvider] = {}
        self.register(ReactiveStreamProvider(client=reactive_client))
        self.register(MaxstreamProvider())
        self.register(MixdropProvider())

    def register(self, provider: StreamingProvider) -> None:
        """Register a new streaming provider."""
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> StreamingProvider | None:
        """Get provider by its identifier."""
        return self._providers.get(provider_id)

    async def find_for_url(self, url: str) -> StreamingProvider | None:
        """Find the first provider capable of handling the URL."""
        for provider in self._providers.values():
            if await provider.can_handle(url):
                return provider
        return None

    def get_ordered_sources(self, sources: list[ProviderSource], preferred: str = "automatic") -> list[ProviderSource]:
        """Return sources sorted by quality and user preference."""
        sources = [s for s in sources if s.available]

        def sort_key(s: ProviderSource) -> tuple[int, int, int]:
            pref_score = 0
            if preferred != "automatic" and s.provider_id == preferred:
                pref_score = 2
            elif s.provider_id in ("reactive", "engine_alpha"):
                pref_score = 1

            quality_order = {"4k": 4, "fhd": 3, "hd": 2, "sd": 1}
            q_score = quality_order.get((s.quality or "").lower(), 0)

            lang_score = 1 if (s.language or "").lower() in ("ita", "it") else 0
            return (pref_score, q_score, lang_score)

        return sorted(sources, key=sort_key, reverse=True)

    async def resolve_source(
        self,
        source: ProviderSource,
        session: aiohttp.ClientSession,
        prefer_fhd: bool = True,
    ) -> ResolvedMedia:
        """Resolve a specific source using its registered provider or URL match."""
        provider = self.get(source.provider_id)
        if not provider:
            provider = await self.find_for_url(source.page_url)

        if not provider:
            raise ValueError(f"No compatible provider found for {source.provider_name} ({source.page_url})")

        return await provider.resolve(source, session, prefer_fhd=prefer_fhd)
