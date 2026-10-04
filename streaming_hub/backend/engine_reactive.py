"""Async HTTP and API client for reactive SPA catalog and streams."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
import html
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

import aiohttp

from .crawler_parser import CrawlerCatalogParser
from .dns_resolver import DNS_DEFAULT, DoHResolver
from .models import Movie, ProviderSource, TvEpisode, TvSeason, TvSeries
from .utils import genre_matches

_LOGGER = logging.getLogger(__name__)

CATALOG_REACTIVE = "reactive"
PROVIDER_REACTIVE = "reactive"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class ReactiveStreamClient:
    """Asynchronous client for interacting with ReactiveEngine."""

    def __init__(
        self,
        base_url: str,
        custom_dns: str = DNS_DEFAULT,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the reactive stream client with user-specified base URL."""
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.custom_dns = custom_dns
        self._session = session
        self._own_session = False
        self._resolver: DoHResolver | None = None
        self._inertia_version: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or initialize the aiohttp ClientSession with DoH."""
        if self._session and not self._session.closed:
            return self._session

        self._resolver = DoHResolver(mode=self.custom_dns)
        connector = aiohttp.TCPConnector(resolver=self._resolver, ssl=False)
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close the underlying session if owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def _ensure_inertia_version(self) -> str:
        """Fetch base page to obtain current Inertia asset version if not set."""
        if self._inertia_version:
            return self._inertia_version
        try:
            session = await self._get_session()
            async with asyncio.timeout(10):
                async with session.get(f"{self.base_url}it", headers={"User-Agent": USER_AGENT}) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        page_data = self.extract_data_page(html_text)
                        ver = page_data.get("version")
                        if ver:
                            self._inertia_version = str(ver)
        except Exception as err:
            _LOGGER.debug("Could not fetch Inertia version: %s", err)
        return self._inertia_version or ""

    async def _request(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> str:
        """Fetch content from a URL with timeout and 409 Inertia version refresh."""
        session = await self._get_session()
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            req_headers.update(headers)

        if req_headers.get("X-Inertia") == "true" and "X-Inertia-Version" not in req_headers:
            ver = await self._ensure_inertia_version()
            if ver:
                req_headers["X-Inertia-Version"] = ver

        try:
            async with asyncio.timeout(15):
                if method.upper() == "POST":
                    async with session.post(url, headers=req_headers, json=data, allow_redirects=True) as resp:
                        if resp.status == 409 and req_headers.get("X-Inertia") == "true":
                            self._inertia_version = None
                            ver = await self._ensure_inertia_version()
                            if ver:
                                req_headers["X-Inertia-Version"] = ver
                            async with session.post(url, headers=req_headers, json=data, allow_redirects=True) as r2:
                                if r2.status != 200:
                                    raise ValueError(f"Reactive stream status {r2.status} for {url}")
                                return await r2.text()
                        if resp.status != 200:
                            raise ValueError(f"Reactive stream returned status {resp.status} for URL {url}")
                        return await resp.text()
                else:
                    async with session.get(url, headers=req_headers, allow_redirects=True) as resp:
                        if resp.status == 409 and req_headers.get("X-Inertia") == "true":
                            self._inertia_version = None
                            ver = await self._ensure_inertia_version()
                            if ver:
                                req_headers["X-Inertia-Version"] = ver
                            async with session.get(url, headers=req_headers, allow_redirects=True) as r2:
                                if r2.status != 200:
                                    raise ValueError(f"Reactive stream status {r2.status} for {url}")
                                return await r2.text()
                        if resp.status != 200:
                            raise ValueError(f"Reactive stream returned status {resp.status} for URL {url}")
                        return await resp.text()
        except TimeoutError as err:
            raise ValueError(f"Timeout requesting {url}") from err
        except aiohttp.ClientError as err:
            raise ValueError(f"HTTP client error requesting {url}: {err}") from err

    @staticmethod
    def extract_data_page(html_content: str) -> dict[str, Any]:
        """Extract and parse Inertia.js data-page attribute from HTML or raw JSON."""
        stripped = html_content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and ("props" in parsed or "component" in parsed or "data" in parsed):
                    return parsed

        match = re.search(r'data-page\s*=\s*"([^"]+)"', html_content)
        if not match:
            match = re.search(r"data-page\s*=\s*'([^']+)'", html_content)
        if not match:
            script_match = re.search(
                r'<script[^>]*type="application/json"[^>]*id="[^"]*inertia[^"]*"[^>]*>(.*?)</script>',
                html_content,
                re.DOTALL,
            )
            if script_match:
                with contextlib.suppress(Exception):
                    return json.loads(script_match.group(1))
            raise ValueError("Inertia data-page attribute not found in HTML")

        unescaped = html.unescape(match.group(1))
        try:
            return json.loads(unescaped)
        except Exception as err:
            raise ValueError(f"Failed to parse Inertia data-page JSON: {err}") from err

    @staticmethod
    def extract_js_object(html_text: str, var_name: str) -> str:
        """Extract a raw JS object literal from html_text using balanced braces."""
        marker = f"window.{var_name}"
        start = html_text.find(marker)
        if start == -1:
            marker = var_name
            start = html_text.find(marker)
            if start == -1:
                raise ValueError(f"JS variable '{var_name}' not found")
        brace_start = html_text.find("{", start)
        if brace_start == -1:
            raise ValueError(f"Opening brace for '{var_name}' not found")
        depth = 0
        for i in range(brace_start, len(html_text)):
            ch = html_text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return html_text[brace_start : i + 1]
        raise ValueError(f"Unbalanced braces for '{var_name}'")

    @staticmethod
    def js_object_to_dict(js_obj: str) -> dict[str, Any]:
        """Convert a JS object literal string into a Python dict."""
        s = js_obj
        s = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)\s*:", r'\1"\2":', s)
        s = re.sub(r"'((?:[^'\\]|\\.)*)'", lambda m: json.dumps(m.group(1)), s)
        s = re.sub(r",\s*([}\]])", r"\1", s)
        return json.loads(s)

    @staticmethod
    def extract_bool(html_text: str, var_name: str) -> bool:
        """Extract a boolean value assigned to window.<var_name>."""
        match = re.search(rf"(?:window\.)?{re.escape(var_name)}\s*=\s*(true|false)", html_text, re.IGNORECASE)
        return match.group(1).lower() == "true" if match else False

    @staticmethod
    def build_master_playlist_url(
        master_playlist: dict[str, Any],
        can_play_fhd: bool = False,
        prefer_fhd: bool = True,
    ) -> str:
        """Construct the resolved m3u8 playlist URL by combining masterPlaylist and params."""
        base_url = str(master_playlist.get("url") or "")
        raw_params = master_playlist.get("params") or {}
        params: dict[str, str] = {str(k): str(v) for k, v in raw_params.items() if v is not None and v != ""}

        if can_play_fhd:
            params["h"] = "1"

        parts = urlsplit(base_url)
        existing = dict(parse_qsl(parts.query))
        existing.update(params)
        final_query = urlencode(existing)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, final_query, parts.fragment))

    def _get_image_url(self, images: list[dict[str, Any]] | None, prefer_type: str = "poster") -> str | None:
        """Find best image URL from images array."""
        if not isinstance(images, list) or not images:
            if isinstance(images, str) and images.startswith(("http://", "https://")):
                return images
            return None

        valid_images = [img for img in images if isinstance(img, dict)]
        if not valid_images:
            return None

        target = next((img for img in valid_images if img.get("type") == prefer_type), None)
        if not target and prefer_type == "poster":
            target = next(
                (img for img in valid_images if img.get("type") in ("cover_mobile", "background", "cover")), None
            )
        if not target:
            target = valid_images[0]

        filename = target.get("filename")
        if not filename:
            for k in ("url", "original_url", "path", "src", "original_url_field"):
                val = target.get(k)
                if val and isinstance(val, str):
                    if val.startswith(("http://", "https://")):
                        return val
                    filename = val
                    break

        if not filename:
            return None

        if isinstance(filename, str) and filename.startswith(("http://", "https://")):
            return filename

        clean_fn = str(filename).lstrip("/")
        clean_fn = clean_fn.removeprefix("images/")

        clean_base = self.base_url.rstrip("/")
        cdn_host = clean_base.replace("://", "://cdn.")
        return f"{cdn_host}/images/{clean_fn}"

    @staticmethod
    def _extract_genre_names(item: dict[str, Any]) -> list[str]:
        """Extract genre name strings from an item dictionary."""
        raw_genres = item.get("genres")
        if not isinstance(raw_genres, list):
            return []
        names: list[str] = []
        for g in raw_genres:
            if isinstance(g, dict) and g.get("name"):
                names.append(str(g["name"]))
            elif isinstance(g, str) and g:
                names.append(g)
        return names

    def _item_to_movie(self, item: dict[str, Any]) -> Movie:
        """Convert a ReactiveEngine search or title dict into a Movie object."""
        sc_id = str(item.get("id"))
        slug = item.get("slug", "")
        name = item.get("name", "")
        release_date = item.get("last_air_date") or item.get("release_date")
        year = None
        if release_date:
            with contextlib.suppress(ValueError, IndexError):
                year = int(str(release_date).split("-")[0])

        score = item.get("score")
        rating = None
        if score is not None:
            with contextlib.suppress(ValueError):
                rating = round(float(score), 1)

        poster_url = self._get_image_url(item.get("images"), "poster")
        backdrop_url = self._get_image_url(item.get("images"), "background")

        genres = self._extract_genre_names(item)
        media_type = item.get("type", "movie")
        if media_type == "tv" or item.get("seasons") or CrawlerCatalogParser.is_tv_item(name, genres=genres):
            genres.append("serie tv")

        raw_cast = item.get("actors") or item.get("cast") or []
        cast_list: list[str] = []
        if isinstance(raw_cast, list):
            for c in raw_cast:
                if isinstance(c, dict) and c.get("name"):
                    cast_list.append(str(c["name"]))
                elif isinstance(c, str) and c:
                    cast_list.append(c)

        director_name = None
        raw_directors = item.get("directors") or item.get("director")
        if isinstance(raw_directors, list) and raw_directors:
            first = raw_directors[0]
            director_name = str(first.get("name") if isinstance(first, dict) else first)
        elif isinstance(raw_directors, dict) and raw_directors.get("name"):
            director_name = str(raw_directors["name"])
        elif isinstance(raw_directors, str):
            director_name = raw_directors

        sc_url = f"{self.base_url}it/titles/{sc_id}-{slug}" if slug else f"{self.base_url}it/titles/{sc_id}"
        watch_url = f"{self.base_url}it/watch/{sc_id}"

        is_available = not item.get("coming_soon", False)
        if "uploaded_at" in item and item["uploaded_at"] is None:
            is_available = False

        source = ProviderSource(
            id=f"sc-movie-{sc_id}",
            media_id=f"sc-{sc_id}",
            provider_id=PROVIDER_REACTIVE,
            provider_name="Reactive",
            page_url=watch_url,
            language="ita",
            quality="1080p FHD",
            available=is_available,
        )

        raw_age = item.get("age")
        certification = None
        if raw_age is not None:
            clean_age = str(raw_age).strip().lstrip("+")
            certification = f"{clean_age}+" if clean_age.isdigit() else str(raw_age)
        elif item.get("adult") or item.get("is_adult"):
            certification = "VM18"

        return Movie(
            id=f"sc-{sc_id}",
            title=name,
            year=year,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            description=item.get("plot"),
            genres=genres,
            duration=item.get("runtime"),
            rating=rating,
            certification=certification,
            cast=cast_list,
            director=director_name,
            source_a_url=sc_url,
            tmdb_id=item.get("tmdb_id"),
            imdb_id=item.get("imdb_id"),
            catalogs=[CATALOG_REACTIVE],
            sources=[source],
            added_at=datetime.now(UTC),
        )

    def _item_to_tv_series(self, item: dict[str, Any]) -> TvSeries:
        """Convert a ReactiveEngine search or title dict into a TvSeries object."""
        sc_id = str(item.get("id"))
        slug = item.get("slug", "")
        name = item.get("name", "")
        release_date = item.get("last_air_date") or item.get("release_date")
        year = None
        if release_date:
            with contextlib.suppress(ValueError, IndexError):
                year = int(str(release_date).split("-")[0])

        score = item.get("score")
        rating = None
        if score is not None:
            with contextlib.suppress(ValueError):
                rating = round(float(score), 1)

        poster_url = self._get_image_url(item.get("images"), "poster")
        backdrop_url = self._get_image_url(item.get("images"), "background")
        genres = self._extract_genre_names(item)

        raw_cast = item.get("actors") or item.get("cast") or []
        cast_list: list[str] = []
        if isinstance(raw_cast, list):
            for c in raw_cast:
                if isinstance(c, dict) and c.get("name"):
                    cast_list.append(str(c["name"]))
                elif isinstance(c, str) and c:
                    cast_list.append(c)

        director_name = None
        raw_directors = item.get("directors") or item.get("director")
        if isinstance(raw_directors, list) and raw_directors:
            first = raw_directors[0]
            director_name = str(first.get("name") if isinstance(first, dict) else first)
        elif isinstance(raw_directors, dict) and raw_directors.get("name"):
            director_name = str(raw_directors["name"])
        elif isinstance(raw_directors, str):
            director_name = raw_directors

        sc_url = f"{self.base_url}it/titles/{sc_id}-{slug}" if slug else f"{self.base_url}it/titles/{sc_id}"

        seasons: list[TvSeason] = []
        raw_seasons = item.get("seasons", [])
        if isinstance(raw_seasons, list):
            for s in raw_seasons:
                if isinstance(s, dict):
                    s_num = s.get("number")
                    if s_num is not None:
                        with contextlib.suppress(ValueError):
                            seasons.append(TvSeason(number=int(s_num), episodes=[]))
                elif isinstance(s, int):
                    seasons.append(TvSeason(number=s, episodes=[]))

        raw_age = item.get("age")
        certification = None
        if raw_age is not None:
            clean_age = str(raw_age).strip().lstrip("+")
            certification = f"{clean_age}+" if clean_age.isdigit() else str(raw_age)
        elif item.get("adult") or item.get("is_adult"):
            certification = "VM18"

        series_id = f"sc-{sc_id}-{slug}" if slug else f"sc-{sc_id}"
        return TvSeries(
            id=series_id,
            title=name,
            year=year,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            description=item.get("plot"),
            genres=genres,
            rating=rating,
            certification=certification,
            cast=cast_list,
            director=director_name,
            source_a_url=sc_url,
            tmdb_id=item.get("tmdb_id"),
            imdb_id=item.get("imdb_id"),
            catalogs=[CATALOG_REACTIVE],
            seasons=seasons,
            added_at=datetime.now(UTC),
        )

    @staticmethod
    def _extract_titles_from_props(props: dict[str, Any], allow_sliders: bool = False) -> list[dict[str, Any]]:
        """Safely extract list of title dicts from Inertia props."""
        if not isinstance(props, dict):
            return []

        titles_prop = props.get("titles")
        if isinstance(titles_prop, dict):
            data = titles_prop.get("data")
            if isinstance(data, list):
                return [t for t in data if isinstance(t, dict)]
        elif isinstance(titles_prop, list):
            return [t for t in titles_prop if isinstance(t, dict)]

        for key in ("latest", "records", "items", "results"):
            val = props.get(key)
            if isinstance(val, dict) and isinstance(val.get("data"), list):
                return [t for t in val["data"] if isinstance(t, dict)]
            if isinstance(val, list) and val:
                return [t for t in val if isinstance(t, dict)]

        if allow_sliders:
            sliders = props.get("sliders")
            if isinstance(sliders, list):
                collected: list[dict[str, Any]] = []
                seen_ids: set[Any] = set()
                for slider in sliders:
                    if isinstance(slider, dict):
                        st = slider.get("titles")
                        if isinstance(st, list):
                            for t in st:
                                if isinstance(t, dict):
                                    tid = t.get("id")
                                    if tid is not None:
                                        if tid not in seen_ids:
                                            seen_ids.add(tid)
                                            collected.append(t)
                                    else:
                                        collected.append(t)
                if collected:
                    return collected

        return []

    async def get_title_preview(self, sc_id: str | int) -> dict[str, Any] | None:
        """Fetch fast structured metadata preview from internal REST API."""
        clean_id = str(sc_id).replace("sc-", "").split("-")[0]
        url = f"{self.base_url}api/titles/preview/{clean_id}"
        headers = {"Accept": "application/json"}
        try:
            raw = await self._request(url, method="POST", headers=headers)
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception as err:
            _LOGGER.debug("Could not fetch preview for %s: %s", sc_id, err)
        return None

    async def search(self, query: str) -> list[Movie | TvSeries]:
        """Search titles by keyword."""
        if not query.strip():
            return []

        search_url = f"{self.base_url}it/search?q={quote_plus(query.strip())}"
        raw_response = await self._request(search_url, headers={"Accept": "application/json"})

        data: dict[str, Any] | None = None
        try:
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict) and "data" in parsed:
                data = parsed
        except (json.JSONDecodeError, ValueError):
            pass

        if not data:
            try:
                page_data = self.extract_data_page(raw_response)
                props = page_data.get("props", {})
                titles = self._extract_titles_from_props(props)
                data = {"data": titles}
            except Exception as err:
                _LOGGER.debug("Search parsing fallback error: %s", err)
                return []

        results: list[Movie | TvSeries] = []
        raw_items = data.get("data", [])
        items = raw_items if isinstance(raw_items, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            media_type = item.get("type", "movie")
            if media_type == "tv":
                results.append(self._item_to_tv_series(item))
            else:
                results.append(self._item_to_movie(item))

        return results

    async def get_homepage_carousels(self) -> tuple[Movie | TvSeries | None, list[dict[str, Any]]]:
        """Fetch editorial and thematic sliders from the homepage or media catalog hubs."""
        inertia_headers = {
            "Accept": "text/html,application/xhtml+xml",
            "X-Inertia": "true",
            "X-Requested-With": "XMLHttpRequest",
        }
        candidate_urls = [f"{self.base_url}it/browse", f"{self.base_url}browse", f"{self.base_url}it", self.base_url]

        label_translations = {
            "latest": "Nuove Uscite",
            "trending": "Di Tendenza",
            "top_10": "Top 10 della Settimana",
            "top10": "Top 10",
            "popular": "I Più Popolari",
            "movies": "Film del Momento",
            "tv": "Serie TV del Momento",
            "series": "Serie TV del Momento",
            "suggested": "Consigliati per Te",
            "recommended": "Consigliati",
        }

        def _parse_sliders_and_hero(
            props: dict[str, Any], default_hero: Movie | TvSeries | None = None
        ) -> tuple[Movie | TvSeries | None, list[dict[str, Any]]]:
            hero_item: Movie | TvSeries | None = default_hero
            billboard_raw = props.get("billboard") or props.get("featured") or props.get("hero")
            if (
                hero_item is None
                and isinstance(billboard_raw, dict)
                and billboard_raw.get("id")
                and not billboard_raw.get("coming_soon")
                and not ("uploaded_at" in billboard_raw and billboard_raw["uploaded_at"] is None)
            ):
                if billboard_raw.get("type") == "tv":
                    hero_item = self._item_to_tv_series(billboard_raw)
                else:
                    hero_item = self._item_to_movie(billboard_raw)

            sliders = props.get("sliders")
            if not sliders or not isinstance(sliders, list):
                return hero_item, []

            parsed: list[dict[str, Any]] = []
            for slider in sliders:
                if not isinstance(slider, dict):
                    continue
                name = str(slider.get("name") or "").strip()
                if name.lower() in ("upcoming", "coming_soon", "prossimamente", "in_arrivo", "in-arrivo"):
                    continue

                title = str(slider.get("label") or slider.get("title") or "").strip()
                if not title and name:
                    title = label_translations.get(name.lower(), name.replace("_", " ").title())
                if not title:
                    title = "In Evidenza"

                raw_titles = slider.get("titles") or []
                if not isinstance(raw_titles, list) or not raw_titles:
                    continue

                items: list[Movie | TvSeries] = []
                for t in raw_titles:
                    if not isinstance(t, dict) or not t.get("id"):
                        continue
                    if t.get("coming_soon") is True or ("uploaded_at" in t and t.get("uploaded_at") is None):
                        continue
                    if t.get("type") == "tv":
                        items.append(self._item_to_tv_series(t))
                    else:
                        items.append(self._item_to_movie(t))

                if items:
                    if hero_item is None and name in ("billboard", "featured", "hero", "trending"):
                        hero_item = items[0]
                    parsed.append(
                        {
                            "id": name or f"slider_{len(parsed) + 1}",
                            "title": title,
                            "items": items,
                        }
                    )
            return hero_item, parsed

        # 1. First attempt candidate home/browse URLs
        for url in candidate_urls:
            try:
                html_text = await self._request(url, headers=inertia_headers)
                page_data = self.extract_data_page(html_text)
                props = page_data.get("props", {})
                if not props and html_text.strip().startswith("{"):
                    with contextlib.suppress(Exception):
                        props = json.loads(html_text).get("props", {})

                hero_item, carousels = _parse_sliders_and_hero(props)
                if carousels:
                    if hero_item is None and carousels[0]["items"]:
                        hero_item = carousels[0]["items"][0]
                    return hero_item, carousels
            except Exception as err:
                _LOGGER.debug("Could not fetch carousels from %s: %s", url, err)

        # 2. Resilient fallback: fetch sliders from /it/movies and /it/tv-shows in parallel
        try:
            movie_task = self._request(f"{self.base_url}it/movies", headers=inertia_headers)
            tv_task = self._request(f"{self.base_url}it/tv-shows", headers=inertia_headers)
            movie_html, tv_html = await asyncio.gather(movie_task, tv_task, return_exceptions=True)

            combined_carousels: list[dict[str, Any]] = []
            selected_hero: Movie | TvSeries | None = None

            if isinstance(movie_html, str):
                m_props = {}
                with contextlib.suppress(Exception):
                    m_props = json.loads(movie_html).get("props", {})
                if not m_props:
                    with contextlib.suppress(Exception):
                        m_props = self.extract_data_page(movie_html).get("props", {})
                m_hero, m_carousels = _parse_sliders_and_hero(m_props)
                if m_hero and not selected_hero:
                    selected_hero = m_hero
                for c in m_carousels:
                    cid = c.get("id")
                    if cid == "trending":
                        c["title"] = "Film del Momento"
                    elif cid == "latest":
                        c["title"] = "Nuove Uscite Film"
                    combined_carousels.append(c)

            if isinstance(tv_html, str):
                tv_props = {}
                with contextlib.suppress(Exception):
                    tv_props = json.loads(tv_html).get("props", {})
                if not tv_props:
                    with contextlib.suppress(Exception):
                        tv_props = self.extract_data_page(tv_html).get("props", {})
                tv_hero, tv_carousels = _parse_sliders_and_hero(tv_props)
                if tv_hero and not selected_hero:
                    selected_hero = tv_hero
                for c in tv_carousels:
                    cid = c.get("id")
                    if cid == "trending":
                        c["title"] = "Serie TV del Momento"
                    elif cid == "latest":
                        c["title"] = "Nuove Uscite Serie TV"
                    combined_carousels.append(c)

            if combined_carousels:
                if selected_hero is None and combined_carousels[0]["items"]:
                    selected_hero = combined_carousels[0]["items"][0]
                return selected_hero, combined_carousels
        except Exception as err:
            _LOGGER.debug("Could not fetch carousels fallback from /it/movies and /it/tv-shows: %s", err)

        return None, []

    async def get_latest_movies(self, page: int = 1) -> list[Movie]:
        """Fetch latest movies."""
        inertia_headers = {
            "Accept": "text/html,application/xhtml+xml",
            "X-Inertia": "true",
            "X-Requested-With": "XMLHttpRequest",
        }

        if page == 1:
            try:
                html_text = await self._request(f"{self.base_url}it/movies", headers=inertia_headers)
                props = json.loads(html_text).get("props", {})
                sliders = props.get("sliders", [])
                latest_titles: list[dict[str, Any]] = []
                seen_ids: set[Any] = set()
                for slider in sliders:
                    if isinstance(slider, dict) and slider.get("name") in ("latest", "trending"):
                        for t in slider.get("titles", []):
                            if isinstance(t, dict) and t.get("id") not in seen_ids:
                                seen_ids.add(t.get("id"))
                                latest_titles.append(t)
                if latest_titles:
                    movies = [self._item_to_movie(t) for t in latest_titles if t.get("id")]
                    movies.sort(key=lambda m: (m.year or 0, m.rating or 0.0), reverse=True)
                    return movies
            except Exception as err:
                _LOGGER.debug("Could not fetch latest movies from /it/movies: %s", err)

        archive_urls = [f"{self.base_url}it/archive?type=movie&sort=uploaded_at&page={page}"]
        for url in archive_urls:
            try:
                html_text = await self._request(url)
                page_data = self.extract_data_page(html_text)
                props = page_data.get("props", {})
                raw_titles = self._extract_titles_from_props(props, allow_sliders=(page == 1))
                movies = [self._item_to_movie(t) for t in raw_titles if t.get("id") and t.get("type", "movie") != "tv"]
                if movies:
                    movies.sort(key=lambda m: (m.year or 0, m.rating or 0.0), reverse=True)
                    return movies
            except Exception as err:
                _LOGGER.debug("Could not fetch latest movies from %s: %s", url, err)

        return []

    async def get_latest_tv(self, page: int = 1) -> list[TvSeries]:
        """Fetch latest TV series."""
        inertia_headers = {
            "Accept": "text/html,application/xhtml+xml",
            "X-Inertia": "true",
            "X-Requested-With": "XMLHttpRequest",
        }

        if page == 1:
            try:
                html_text = await self._request(f"{self.base_url}it/tv-shows", headers=inertia_headers)
                props = json.loads(html_text).get("props", {})
                sliders = props.get("sliders", [])
                latest_titles: list[dict[str, Any]] = []
                seen_ids: set[Any] = set()
                for slider in sliders:
                    if isinstance(slider, dict) and slider.get("name") in ("latest", "trending"):
                        for t in slider.get("titles", []):
                            if isinstance(t, dict) and t.get("id") not in seen_ids:
                                seen_ids.add(t.get("id"))
                                latest_titles.append(t)
                if latest_titles:
                    series = [self._item_to_tv_series(t) for t in latest_titles if t.get("id")]
                    series.sort(key=lambda s: (s.year or 0, s.rating or 0.0), reverse=True)
                    return series
            except Exception as err:
                _LOGGER.debug("Could not fetch latest tv from /it/tv-shows: %s", err)

        archive_urls = [f"{self.base_url}it/archive?type=tv&sort=uploaded_at&page={page}"]
        for url in archive_urls:
            try:
                html_text = await self._request(url)
                page_data = self.extract_data_page(html_text)
                props = page_data.get("props", {})
                raw_titles = self._extract_titles_from_props(props, allow_sliders=(page == 1))
                series = [self._item_to_tv_series(t) for t in raw_titles if t.get("id") and t.get("type") != "movie"]
                if series:
                    series.sort(key=lambda s: (s.year or 0, s.rating or 0.0), reverse=True)
                    return series
            except Exception as err:
                _LOGGER.debug("Could not fetch latest tv from %s: %s", url, err)

        return []

    async def get_genres(self) -> list[str]:
        """Return the list of available genres."""
        return [
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

    GENRE_ID_MAP: dict[str, int] = {
        "animazione": 19,
        "avventura": 11,
        "azione": 4,
        "action & adventure": 13,
        "commedia": 12,
        "comico": 12,
        "crime": 2,
        "poliziesco": 2,
        "documentario": 24,
        "dramma": 1,
        "drammatico": 1,
        "famiglia": 16,
        "fantasy": 8,
        "storia": 22,
        "storico": 22,
        "biografico": 22,
        "horror": 7,
        "kids": 25,
        "korean drama": 26,
        "musica": 14,
        "musicale": 14,
        "mistero": 6,
        "giallo": 6,
        "reality": 18,
        "romance": 15,
        "sentimentale": 15,
        "sci-fi & fantasy": 3,
        "fantascienza": 10,
        "soap": 23,
        "thriller": 5,
        "televisione film": 21,
        "guerra": 9,
        "war & politics": 17,
        "western": 20,
    }

    def resolve_genre_id(self, genre: str) -> int | None:
        """Resolve genre name or slug to ReactiveEngine numerical genre ID."""
        clean = genre.strip().lower()
        if clean in self.GENRE_ID_MAP:
            return self.GENRE_ID_MAP[clean]
        for k, v in self.GENRE_ID_MAP.items():
            if k in clean or clean in k:
                return v
        return None

    async def get_by_genre(
        self,
        genre: str,
        media_type: str = "movie",
        page: int = 1,
    ) -> list[Movie | TvSeries]:
        """Fetch titles by genre from archive using genre[] numerical ID or search fallback."""
        m_type = "tv" if media_type == "tv" else "movie"
        genre_id = self.resolve_genre_id(genre)
        headers = {"X-Inertia": "true", "Accept": "text/html, application/xhtml+xml"}

        candidate_urls: list[str] = []
        if genre_id is not None:
            candidate_urls.append(f"{self.base_url}it/archive?type={m_type}&genre[]={genre_id}&page={page}")
        candidate_urls.append(
            f"{self.base_url}it/archive?type={m_type}&genre[]={quote_plus(genre.strip())}&page={page}"
        )

        for url in candidate_urls:
            try:
                html_text = await self._request(url, headers=headers)
                page_data = self.extract_data_page(html_text)
                props = page_data.get("props", {})
                # Note: DO NOT allow sliders for genre archive to prevent returning generic home items!
                raw_titles = self._extract_titles_from_props(props, allow_sliders=False)
                if raw_titles:
                    results: list[Movie | TvSeries] = []
                    for t in raw_titles:
                        if not isinstance(t, dict) or not t.get("id"):
                            continue
                        t_type = t.get("type", "movie")
                        if m_type == "tv" and t_type != "movie":
                            item = self._item_to_tv_series(t)
                            if not item.genres:
                                item.genres = [genre.capitalize()]
                            results.append(item)
                        elif m_type == "movie" and t_type != "tv":
                            item = self._item_to_movie(t)
                            if not item.genres:
                                item.genres = [genre.capitalize()]
                            results.append(item)
                    if results:
                        return results
            except Exception as err:
                _LOGGER.debug("Archive genre fetch failed on %s: %s", url, err)

        # Fallback: search by genre keyword and filter
        try:
            search_items = await self.search(genre)
            filtered: list[Movie | TvSeries] = []
            for item in search_items:
                if (m_type == "tv" and isinstance(item, TvSeries)) or (m_type == "movie" and isinstance(item, Movie)):
                    if not item.genres or any(genre_matches(genre, g) for g in item.genres):
                        if not item.genres:
                            item.genres = [genre.capitalize()]
                        filtered.append(item)
            return filtered
        except Exception as err:
            _LOGGER.debug("Search fallback for genre '%s' failed: %s", genre, err)

        return []

    async def get_movies_by_genre(
        self,
        genre: str,
        page: int = 1,
        is_tv: bool = False,
    ) -> list[Movie | TvSeries]:
        """Compatibility wrapper for get_by_genre."""
        return await self.get_by_genre(genre, media_type="tv" if is_tv else "movie", page=page)

    async def get_movie(self, media_id: str, slug: str = "") -> Movie:
        """Fetch complete movie details."""
        clean_id = media_id.replace("sc-", "")
        if not slug and "-" in clean_id:
            parts = clean_id.split("-", 1)
            clean_sc_id = parts[0]
            slug = parts[1]
        else:
            clean_sc_id = clean_id.split("-")[0]

        preview: dict[str, Any] | None = None
        if not slug and clean_sc_id:
            preview = await self.get_title_preview(clean_sc_id)
            if preview and isinstance(preview, dict) and preview.get("slug"):
                slug = str(preview["slug"])

        title_url = (
            f"{self.base_url}it/titles/{clean_sc_id}-{slug}" if slug else f"{self.base_url}it/titles/{clean_sc_id}"
        )

        title_data: dict[str, Any] | None = None
        if slug:
            try:
                html_text = await self._request(title_url)
                page_data = self.extract_data_page(html_text)
                title_data = page_data.get("props", {}).get("title")
            except Exception as err:
                _LOGGER.debug("Direct request for movie %s failed: %s", media_id, err)

        if not title_data and preview:
            title_data = preview
        elif not title_data and clean_sc_id:
            preview = await self.get_title_preview(clean_sc_id)
            if preview and isinstance(preview, dict):
                title_data = preview

        if not title_data or not isinstance(title_data, dict):
            raise ValueError(f"No title data found for movie {media_id}")

        return self._item_to_movie(title_data)

    def _parse_loaded_season(self, sc_id: str, season_num: int, loaded_season: dict[str, Any]) -> TvSeason:
        """Parse season and episodes from an Inertia loadedSeason dictionary."""
        if not isinstance(loaded_season, dict):
            return TvSeason(number=season_num, episodes=[])

        # Validate that loadedSeason actually belongs to the requested season_num
        loaded_num = loaded_season.get("number")
        if loaded_num is not None and int(loaded_num) != int(season_num):
            _LOGGER.debug(
                "loadedSeason number %s does not match requested season %s for %s",
                loaded_num,
                season_num,
                sc_id,
            )
            return TvSeason(number=season_num, episodes=[])

        raw_episodes = loaded_season.get("episodes", [])
        episodes: list[TvEpisode] = []
        for ep in raw_episodes:
            if not isinstance(ep, dict):
                continue
            ep_id = str(ep.get("id"))
            ep_num = ep.get("number")
            if ep_num is None:
                continue
            name = ep.get("name") or f"Episodio {ep_num}"
            plot = ep.get("plot")
            poster_url = self._get_image_url(ep.get("images"), "cover")
            # Use direct iframe URL to prevent Inertia SSR from defaulting to S01E01
            watch_url = f"{self.base_url}it/iframe/{sc_id}?episode_id={ep_id}"

            source = ProviderSource(
                id=f"sc-ep-{ep_id}",
                media_id=f"sc-{sc_id}_s{season_num}e{ep_num}",
                provider_id=PROVIDER_REACTIVE,
                provider_name="Reactive",
                page_url=watch_url,
                language="ita",
                quality="1080p FHD",
                available=True,
            )

            episodes.append(
                TvEpisode(
                    id=f"sc-{sc_id}_s{season_num}e{ep_num}",
                    media_id=f"sc-{sc_id}",
                    season_number=season_num,
                    episode_number=int(ep_num),
                    title=name,
                    description=plot,
                    poster_url=poster_url,
                    sources=[source],
                )
            )

        return TvSeason(number=season_num, episodes=sorted(episodes, key=lambda e: e.episode_number))

    async def get_tv_series(self, media_id: str, slug: str = "") -> TvSeries:
        """Fetch complete TV series details with all seasons."""
        clean_id = media_id.replace("sc-", "")
        if not slug and "-" in clean_id:
            parts = clean_id.split("-", 1)
            clean_sc_id = parts[0]
            slug = parts[1]
        else:
            clean_sc_id = clean_id.split("-")[0]

        preview: dict[str, Any] | None = None
        if not slug and clean_sc_id:
            preview = await self.get_title_preview(clean_sc_id)
            if preview and isinstance(preview, dict) and preview.get("slug"):
                slug = str(preview["slug"])

        series_url = (
            f"{self.base_url}it/titles/{clean_sc_id}-{slug}" if slug else f"{self.base_url}it/titles/{clean_sc_id}"
        )

        title_data: dict[str, Any] | None = None
        props: dict[str, Any] = {}
        if slug:
            try:
                html_text = await self._request(series_url)
                page_data = self.extract_data_page(html_text)
                props = page_data.get("props", {})
                title_data = props.get("title")
            except Exception as err:
                _LOGGER.debug("Direct request for TV series %s failed: %s", media_id, err)

        if not title_data and preview:
            title_data = preview
        elif not title_data and clean_sc_id:
            preview = await self.get_title_preview(clean_sc_id)
            if preview and isinstance(preview, dict):
                title_data = preview

        if not title_data or not isinstance(title_data, dict):
            raise ValueError(f"No title data found for series {media_id}")

        series = self._item_to_tv_series(title_data)
        actual_slug = str(title_data.get("slug") or slug)
        raw_seasons = title_data.get("seasons", [])
        series.seasons = []

        loaded_season = props.get("loadedSeason") if isinstance(props, dict) else None
        loaded_season_num: int | None = None
        if isinstance(loaded_season, dict) and loaded_season.get("number") is not None:
            with contextlib.suppress(ValueError):
                loaded_season_num = int(loaded_season["number"])

        for s in raw_seasons if isinstance(raw_seasons, list) else []:
            if not isinstance(s, dict):
                continue
            s_num = s.get("number")
            if s_num is not None:
                s_int = int(s_num)
                if loaded_season and loaded_season_num == s_int:
                    season = self._parse_loaded_season(clean_sc_id, s_int, loaded_season)
                else:
                    season = await self.get_tv_season(clean_sc_id, actual_slug, s_int)
                series.seasons.append(season)

        # Fallback if no seasons were in raw_seasons but loadedSeason exists
        if not series.seasons and loaded_season and loaded_season_num is not None:
            series.seasons.append(self._parse_loaded_season(clean_sc_id, loaded_season_num, loaded_season))

        return series

    async def get_tv_season(self, sc_id: str, slug: str, season_num: int) -> TvSeason:
        """Fetch episodes for a specific TV season."""
        clean_sc_id = str(sc_id).replace("sc-", "")
        if not slug and "-" in clean_sc_id:
            parts = clean_sc_id.split("-", 1)
            clean_sc_id = parts[0]
            slug = parts[1]
        elif "-" in clean_sc_id:
            clean_sc_id = clean_sc_id.split("-")[0]

        if not slug:
            preview = await self.get_title_preview(clean_sc_id)
            if preview and preview.get("slug"):
                slug = str(preview["slug"])

        slug_part = f"{clean_sc_id}-{slug}" if slug else clean_sc_id
        candidates = [
            f"{self.base_url}it/titles/{slug_part}/season-{season_num}",
            f"{self.base_url}it/titles/{slug_part}/stagione-{season_num}",
        ]
        if slug:
            candidates.append(f"{self.base_url}it/titles/{clean_sc_id}/season-{season_num}")
            candidates.append(f"{self.base_url}it/titles/{clean_sc_id}/stagione-{season_num}")

        html_text = ""
        for season_url in candidates:
            try:
                html_text = await self._request(season_url)
                if html_text:
                    break
            except Exception:
                continue

        if not html_text:
            return TvSeason(number=season_num, episodes=[])

        try:
            page_data = self.extract_data_page(html_text)
            props = page_data.get("props", {})
            title_obj = props.get("title", {})
            available_seasons = [
                int(s["number"])
                for s in title_obj.get("seasons", [])
                if isinstance(s, dict) and s.get("number") is not None
            ]
            if available_seasons and int(season_num) not in available_seasons:
                _LOGGER.debug(
                    "Season %s not in available seasons %s for %s",
                    season_num,
                    available_seasons,
                    clean_sc_id,
                )
                return TvSeason(number=season_num, episodes=[])

            loaded_season = props.get("loadedSeason")
            if isinstance(loaded_season, dict):
                loaded_num = loaded_season.get("number")
                if loaded_num is not None and int(loaded_num) != int(season_num):
                    _LOGGER.warning(
                        "Server returned loadedSeason number %s but requested %s for %s (season does not exist)",
                        loaded_num,
                        season_num,
                        clean_sc_id,
                    )
                    return TvSeason(number=season_num, episodes=[])
                return self._parse_loaded_season(clean_sc_id, season_num, loaded_season)
        except Exception as err:
            _LOGGER.debug("Error parsing season %s: %s", season_num, err)

        return TvSeason(number=season_num, episodes=[])

    async def resolve_stream(
        self,
        watch_url: str,
        prefer_fhd: bool = True,
    ) -> tuple[str, dict[str, str]]:
        """Resolve a ReactiveEngine watch URL to an HLS .m3u8 playlist URL and required headers."""
        current_url = watch_url
        # If this is an episode watch URL, transform to iframe directly to avoid Inertia SSR defaulting to S01E01
        if "episode_id=" in current_url and "/it/watch/" in current_url:
            current_url = current_url.replace("/it/watch/", "/it/iframe/")
        headers = {"User-Agent": USER_AGENT}
        visited: set[str] = set()
        vix_html: str | None = None
        final_iframe_url: str = current_url

        for _ in range(3):
            if current_url in visited:
                break
            visited.add(current_url)

            html_text = await self._request(current_url, headers=headers)
            if "masterPlaylist" in html_text:
                vix_html = html_text
                final_iframe_url = current_url
                break

            next_url: str | None = None
            page_data: dict[str, Any] | None = None
            with contextlib.suppress(Exception):
                page_data = self.extract_data_page(html_text)

            if page_data:
                next_url = page_data.get("props", {}).get("embedUrl")

            if not next_url:
                match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_text)
                if match:
                    next_url = html.unescape(match.group(1))

            if not next_url:
                break

            if next_url.startswith("//"):
                next_url = f"https:{next_url}"
            elif next_url.startswith("/"):
                next_url = urljoin(current_url, next_url)

            headers = {
                "Referer": current_url,
                "User-Agent": USER_AGENT,
            }
            final_iframe_url = next_url
            current_url = next_url

        if not vix_html:
            _LOGGER.error(
                "Causa Nota: Impossibile trovare l'iframe del player. Il provider di streaming potrebbe aver cambiato la struttura HTML/JS o l'IP di Home Assistant e' bloccato."
            )
            raise ValueError(f"Could not locate player iframe with masterPlaylist on {watch_url}")

        can_play_fhd = self.extract_bool(vix_html, "canPlayFHD")
        m3u8_url: str | None = None

        try:
            raw_js = self.extract_js_object(vix_html, "masterPlaylist")
            master_data = self.js_object_to_dict(raw_js)
            if master_data.get("url"):
                m3u8_url = self.build_master_playlist_url(
                    master_data,
                    can_play_fhd=can_play_fhd,
                    prefer_fhd=prefer_fhd,
                )
        except Exception as err:
            _LOGGER.debug("Balanced-brace JS parsing failed, falling back to regex: %s", err)

        if not m3u8_url:
            match_params = re.search(r"params\s*:\s*(\{[^}]+\})", vix_html)
            match_url = re.search(r"url\s*:\s*['\"]([^'\"]+)['\"]", vix_html)
            if not can_play_fhd:
                can_play_fhd = bool(re.search(r"window\.canPlayFHD\s*=\s*true", vix_html))

            if not match_url:
                raise ValueError("masterPlaylist url not found in player iframe")

            base_playlist_url = match_url.group(1)
            params: dict[str, Any] = {}
            if match_params:
                raw_params_str = match_params.group(1)
                raw_params_str = re.sub(r"([{,]\s*)([A-Za-z0-9_]+)\s*:", r'\1"\2":', raw_params_str)
                raw_params_str = raw_params_str.replace("'", '"')
                raw_params_str = re.sub(r",\s*}", "}", raw_params_str)
                with contextlib.suppress(Exception):
                    params = json.loads(raw_params_str)

            params_dict = {str(k): str(v) for k, v in params.items() if v}
            if can_play_fhd:
                params_dict["h"] = "1"

            parts = urlsplit(base_playlist_url)
            existing = dict(parse_qsl(parts.query))
            existing.update(params_dict)
            final_query = urlencode(existing)
            m3u8_url = urlunsplit((parts.scheme, parts.netloc, parts.path, final_query, parts.fragment))

        stream_headers = {
            "Referer": final_iframe_url,
            "User-Agent": USER_AGENT,
        }

        return m3u8_url, stream_headers
