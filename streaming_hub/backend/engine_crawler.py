"""Async HTTP client for web catalog and metadata extraction."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote_plus, urljoin

import aiohttp

from .crawler_parser import CrawlerCatalogParser
from .dns_resolver import DNS_DEFAULT, DoHResolver
from .models import Movie, TvSeries

_LOGGER = logging.getLogger(__name__)

GENRES_LIST = [
    "Animazione",
    "Avventura",
    "Azione",
    "Biografico",
    "Comico",
    "Commedia",
    "Documentario",
    "Drammatico",
    "Fantascienza",
    "Fantasy",
    "Giallo",
    "Guerra",
    "Horror",
    "Musicale",
    "Poliziesco",
    "Sentimentale",
    "Storico",
    "Thriller",
    "Western",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class CrawlerStreamClient:
    """Asynchronous client for extracting media from HTML web catalogs."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = DNS_DEFAULT,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the crawler client with user-specified base URL."""
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.custom_dns = custom_dns
        self._session = session
        self._own_session = False
        self._resolver: DoHResolver | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session

        connector = None
        if self.custom_dns and self.custom_dns != "system":
            self._resolver = DoHResolver(mode=self.custom_dns)
            connector = self._resolver.get_connector()

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        self._session = aiohttp.ClientSession(
            connector=connector,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        self._own_session = True
        return self._session

    async def _request(self, url: str) -> str:
        session = await self._get_session()
        try:
            async with asyncio.timeout(10):
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    _LOGGER.debug("Crawler source returned status %s for %s", resp.status, url)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.debug("Crawler source request failed for %s: %s", url, err)

        raise ValueError(f"Could not connect to catalog source for {url}")

    async def get_latest_movies(self, page: int = 1) -> list[Movie]:
        """Fetch the most recent movies."""
        url = self.base_url
        if page > 1:
            url = urljoin(self.base_url, f"page/{page}/")

        html_text = await self._request(url)
        movies = CrawlerCatalogParser.parse_catalog_page(html_text)
        return [m for m in movies if not CrawlerCatalogParser.is_tv_item(m.title, m.source_b_url, m.genres)]

    async def get_by_genre(self, genre: str, media_type: str = "movie", page: int = 1) -> list[Movie | TvSeries]:
        """Fetch titles matching a specific genre."""
        slug = genre.lower().replace(" ", "-")
        path = f"category/{slug}/"
        if page > 1:
            path += f"page/{page}/"
        url = urljoin(self.base_url, path)

        try:
            html_text = await self._request(url)
            movies = CrawlerCatalogParser.parse_catalog_page(html_text)
            return [m for m in movies if not CrawlerCatalogParser.is_tv_item(m.title, m.source_b_url, m.genres)]
        except Exception as err:
            _LOGGER.debug("Genre '%s' fetch failed on %s: %s", genre, url, err)
            return []

    async def get_latest(self, page: int = 1) -> list[Movie]:
        """Alias for get_latest_movies."""
        return await self.get_latest_movies(page=page)

    async def search(self, query: str) -> list[Movie | TvSeries]:
        """Search titles by keyword."""
        url = f"{self.base_url}?s={quote_plus(query)}"
        html_text = await self._request(url)

        parsed = CrawlerCatalogParser.parse_catalog_page(html_text)
        results: list[Movie | TvSeries] = []
        for item in parsed:
            if CrawlerCatalogParser.is_tv_item(item.title, item.source_b_url, item.genres):
                results.append(
                    TvSeries(
                        id=item.id,
                        title=item.title,
                        year=item.year,
                        poster_url=item.poster_url,
                        description=item.description,
                        genres=item.genres,
                        source_b_url=item.source_b_url,
                        catalogs=["crawler"],
                        seasons=[],
                    )
                )
            else:
                results.append(item)
        return results

    async def get_movie(self, media_id_or_url: str) -> Movie:
        """Fetch complete movie details and sources."""
        if media_id_or_url.startswith(("http://", "https://")):
            url = media_id_or_url
        else:
            url = urljoin(self.base_url, f"{media_id_or_url}/")

        html_text = await self._request(url)
        return CrawlerCatalogParser.parse_movie_page(html_text, movie_url=url)

    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch the most recent TV series."""
        path = "category/serie-tv/"
        if page > 1:
            path += f"page/{page}/"
        url = urljoin(self.base_url, path)

        html_text = await self._request(url)
        movies = CrawlerCatalogParser.parse_catalog_page(html_text)
        return [
            TvSeries(
                id=m.id,
                title=m.title,
                year=m.year,
                poster_url=m.poster_url,
                description=m.description,
                genres=m.genres,
                source_b_url=m.source_b_url,
                catalogs=["crawler"],
                seasons=[],
            )
            for m in movies
        ]

    get_latest_tv_series = get_latest_tv

    async def get_tv_series(self, media_id_or_url: str) -> TvSeries:
        """Fetch complete TV series details and episodes."""
        if media_id_or_url.startswith(("http://", "https://")):
            url = media_id_or_url
        else:
            url = urljoin(self.base_url, f"{media_id_or_url}/")

        html_text = await self._request(url)
        return CrawlerCatalogParser.parse_tv_series_page(html_text, series_url=url)

    async def get_genres(self) -> list[str]:
        """Return the list of available genres."""
        return list(GENRES_LIST)

    async def close(self) -> None:
        """Close client and underlying connections."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
        if self._resolver:
            await self._resolver.close()
