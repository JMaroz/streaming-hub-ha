"""Metadata enrichment service using TMDb API with free public Cinemeta/TVmaze fallback."""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any
from urllib.parse import quote_plus

import aiohttp

from .models import Movie, TvSeries

_LOGGER = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"
CINEMETA_BASE_URL = "https://v3-cinemeta.strem.io/meta"
USER_AGENT = "Mozilla/5.0 (HomeAssistant/StreamingHub; it-IT)"


class MetadataEnricher:
    """Enriches Movie and TvSeries models with plot, cast, director, high-res posters, and ratings."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        tmdb_api_key: str | None = None,
    ) -> None:
        """Initialize the metadata enricher."""
        self._session = session
        self._own_session = False
        raw_key = (tmdb_api_key or "").strip().strip("\"'")
        if raw_key.lower().startswith("bearer "):
            raw_key = raw_key[7:].strip()
        self.tmdb_api_key = raw_key
        self._cache: dict[str, dict[str, Any]] = {}

    def _is_bearer_token(self) -> bool:
        """Determine if the TMDb key is a v4 Read Access Token."""
        return self.tmdb_api_key.startswith("eyJ") or len(self.tmdb_api_key) > 40 or "." in self.tmdb_api_key

    def _get_tmdb_auth(self, custom_key: str | None = None) -> tuple[dict[str, str], dict[str, Any]]:
        """Return (headers, params) tuple for TMDb authentication."""
        key = (custom_key or self.tmdb_api_key or "").strip().strip("\"'")
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        if not key:
            return {}, {}
        if key.startswith("eyJ") or len(key) > 40 or "." in key:
            return {"Authorization": f"Bearer {key}"}, {}
        return {}, {"api_key": key}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ensure an active aiohttp session."""
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
        self._own_session = True
        return self._session

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip quality and noise from title for cleaner metadata search."""
        t = re.sub(r"\[.*?\]", "", title)
        t = re.sub(r"\(.*?\)", "", t)
        t = re.sub(r"\b(4k|fhd|hd|sd|streaming|ita|subita)\b", "", t, flags=re.IGNORECASE)
        return " ".join(t.split())

    async def _get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch JSON helper from given URL."""
        session = await self._get_session()
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            req_headers.update(headers)
        try:
            async with session.get(
                url, params=params, headers=req_headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as err:
            _LOGGER.debug("Request failed for %s: %s", url, err)
        return None

    async def _post_json(
        self,
        url: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Post JSON helper to given URL."""
        session = await self._get_session()
        req_headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        try:
            async with session.post(
                url, json=json_data, params=params, headers=req_headers, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                _LOGGER.debug("POST %s failed with status %s", url, resp.status)
        except Exception as err:
            _LOGGER.debug("POST failed for %s: %s", url, err)
        return None

    async def close(self) -> None:
        """Close session if internally owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def _search_cinemeta_imdb_id(self, media_type: str, title: str) -> str | None:
        """Search Cinemeta by title to resolve an IMDb ID."""
        clean = self._clean_title(title)
        query = quote_plus(clean)
        url = f"{CINEMETA_BASE_URL}/catalog/{media_type}/top/search={query}.json"
        try:
            data = await self._get_json(url)
            if data and isinstance(data, dict):
                metas = data.get("metas", [])
                if metas and isinstance(metas[0], dict) and metas[0].get("id"):
                    return metas[0]["id"]
        except Exception as err:
            _LOGGER.debug("Cinemeta title search failed for %s: %s", title, err)
        return None

    async def get_imdb_id(self, media_type: str, tmdb_id: int) -> str | None:
        """Fetch IMDb ID for a given TMDb ID from TMDb external_ids endpoint."""
        endpoint_type = "tv" if media_type in ("tv", "series") else "movie"
        url = f"{TMDB_BASE_URL}/{endpoint_type}/{tmdb_id}/external_ids"
        headers, params = self._get_tmdb_auth()
        data = await self._get_json(url, params=params, headers=headers)
        if data and isinstance(data, dict):
            clean = data.get("imdb_id")
            if clean and str(clean).startswith("tt"):
                return str(clean)
        return None

    def clear_cache(self) -> None:
        """Clear the in-memory metadata cache."""
        self._cache.clear()

    async def validate_api_key(self, api_key: str | None = None) -> tuple[bool, str]:
        """Validate a TMDb API key or v4 Bearer token against TMDb authentication endpoint."""
        key_to_test = (api_key if api_key is not None else self.tmdb_api_key or "").strip().strip("\"'")
        if key_to_test.lower().startswith("bearer "):
            key_to_test = key_to_test[7:].strip()
        if not key_to_test:
            return False, "La chiave API TMDb non è stata inserita o è vuota."

        auth_headers, auth_params = self._get_tmdb_auth(key_to_test)
        url = f"{TMDB_BASE_URL}/authentication"
        session = await self._get_session()
        req_headers = {"User-Agent": USER_AGENT}
        if auth_headers:
            req_headers.update(auth_headers)

        try:
            async with session.get(
                url, params=auth_params, headers=req_headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and data.get("success") is True:
                        return True, "Chiave API TMDb valida e funzionante."
                    msg = data.get("status_message") if data else "Risposta non valida da TMDb."
                    return False, f"Errore TMDb: {msg}"
                if resp.status == 401:
                    return False, "Chiave API TMDb non valida o non autorizzata (401 Unauthorized)."
                return False, f"TMDb ha risposto con codice di errore HTTP {resp.status}."
        except Exception as err:
            _LOGGER.warning("TMDb validation request failed: %s", err)
            return False, f"Impossibile contattare i server TMDb: {err}"

    async def create_request_token(self, api_key: str | None = None) -> dict[str, Any]:
        """Create a new TMDb v3 authentication request token."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        if not auth_headers and not auth_params:
            return {"success": False, "error": "Chiave API TMDb non configurata"}
        url = f"{TMDB_BASE_URL}/authentication/token/new"
        data = await self._get_json(url, params=auth_params, headers=auth_headers)
        if data and data.get("success"):
            req_token = data.get("request_token")
            return {
                "success": True,
                "request_token": req_token,
                "expires_at": data.get("expires_at"),
                "auth_url": f"https://www.themoviedb.org/authenticate/{req_token}",
            }
        return {"success": False, "error": "Creazione request token TMDb fallita"}

    async def create_session_id(self, request_token: str, api_key: str | None = None) -> str | None:
        """Exchange an approved request token for a TMDb session ID."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        url = f"{TMDB_BASE_URL}/authentication/session/new"
        data = await self._post_json(
            url, json_data={"request_token": request_token}, params=auth_params, headers=auth_headers
        )
        if data and data.get("success"):
            return str(data.get("session_id"))
        return None

    async def get_account_details(self, session_id: str, api_key: str | None = None) -> dict[str, Any] | None:
        """Fetch TMDb account profile details for an active session ID."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        params = {"session_id": session_id, **auth_params}
        url = f"{TMDB_BASE_URL}/account"
        return await self._get_json(url, params=params, headers=auth_headers)

    async def get_account_favorites(
        self, session_id: str, account_id: int, media_type: str = "movies", api_key: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch user favorite movies or TV shows from TMDb."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        endpoint = "favorite/movies" if media_type == "movies" else "favorite/tv"
        url = f"{TMDB_BASE_URL}/account/{account_id}/{endpoint}"
        params = {"session_id": session_id, "language": "it-IT", "page": 1, **auth_params}
        data = await self._get_json(url, params=params, headers=auth_headers)
        if data and "results" in data:
            return data["results"]
        return []

    async def get_account_watchlist(
        self, session_id: str, account_id: int, media_type: str = "movies", api_key: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch user watchlist movies or TV shows from TMDb."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        endpoint = "watchlist/movies" if media_type == "movies" else "watchlist/tv"
        url = f"{TMDB_BASE_URL}/account/{account_id}/{endpoint}"
        params = {"session_id": session_id, "language": "it-IT", "page": 1, **auth_params}
        data = await self._get_json(url, params=params, headers=auth_headers)
        if data and "results" in data:
            return data["results"]
        return []

    async def post_account_favorite(
        self,
        session_id: str,
        account_id: int,
        media_type: str,
        media_id: int,
        favorite: bool = True,
        api_key: str | None = None,
    ) -> bool:
        """Mark or unmark a title as favorite on TMDb account."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        url = f"{TMDB_BASE_URL}/account/{account_id}/favorite"
        params = {"session_id": session_id, **auth_params}
        payload = {
            "media_type": media_type,
            "media_id": media_id,
            "favorite": favorite,
        }
        res = await self._post_json(url, json_data=payload, params=params, headers=auth_headers)
        return bool(res and res.get("success"))

    async def post_account_watchlist(
        self,
        session_id: str,
        account_id: int,
        media_type: str,
        media_id: int,
        watchlist: bool = True,
        api_key: str | None = None,
    ) -> bool:
        """Add or remove a title from TMDb account watchlist."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        url = f"{TMDB_BASE_URL}/account/{account_id}/watchlist"
        params = {"session_id": session_id, **auth_params}
        payload = {
            "media_type": media_type,
            "media_id": media_id,
            "watchlist": watchlist,
        }
        res = await self._post_json(url, json_data=payload, params=params, headers=auth_headers)
        return bool(res and res.get("success"))

    async def enrich_movie(self, movie: Movie, api_key: str | None = None) -> Movie:
        """Enrich movie details using TMDb or free fallback."""
        cache_key = f"movie:{movie.id}"
        key_to_use = api_key or self.tmdb_api_key
        if cache_key in self._cache:
            cached_meta = self._cache[cache_key]
            has_wp = bool(cached_meta.get("watch/providers") or cached_meta.get("watch_providers"))
            if not key_to_use or has_wp:
                self._apply_movie_metadata(movie, cached_meta)
                return movie

        metadata: dict[str, Any] | None = None
        if key_to_use:
            metadata = await self._fetch_tmdb_movie(movie, key_to_use)

        if not metadata and not movie.imdb_id:
            search_title = movie.title
            if (not search_title or search_title.strip() == "Senza Titolo") and movie.id:
                clean_id = movie.id.replace("sc-", "")
                if "-" in clean_id:
                    search_title = clean_id.split("-", 1)[1].replace("-", " ")
            if search_title and search_title.strip() != "Senza Titolo":
                movie.imdb_id = await self._search_cinemeta_imdb_id("movie", search_title)

        if not metadata and movie.imdb_id:
            metadata = await self._fetch_cinemeta("movie", movie.imdb_id)

        if metadata:
            self._cache[cache_key] = metadata
            self._apply_movie_metadata(movie, metadata)

        return movie

    async def enrich_tv_series(self, series: TvSeries, api_key: str | None = None) -> TvSeries:
        """Enrich TV series details using TMDb or free fallback."""
        cache_key = f"tv:{series.id}"
        key_to_use = api_key or self.tmdb_api_key
        if cache_key in self._cache:
            cached_meta = self._cache[cache_key]
            has_wp = bool(cached_meta.get("watch/providers") or cached_meta.get("watch_providers"))
            if not key_to_use or has_wp:
                self._apply_tv_metadata(series, cached_meta)
                return series

        metadata: dict[str, Any] | None = None
        if key_to_use:
            metadata = await self._fetch_tmdb_tv(series, key_to_use)

        if not metadata and not series.imdb_id:
            search_title = series.title
            if (not search_title or search_title.strip() == "Senza Titolo") and series.id:
                clean_id = series.id.replace("sc-", "")
                if "-" in clean_id:
                    search_title = clean_id.split("-", 1)[1].replace("-", " ")
            if search_title and search_title.strip() != "Senza Titolo":
                series.imdb_id = await self._search_cinemeta_imdb_id("series", search_title)

        if not metadata and series.imdb_id:
            metadata = await self._fetch_cinemeta("series", series.imdb_id)

        if not metadata:
            search_title = series.title
            if (not search_title or search_title.strip() == "Senza Titolo") and series.id:
                clean_id = series.id.replace("sc-", "")
                if "-" in clean_id:
                    search_title = clean_id.split("-", 1)[1].replace("-", " ")
            if search_title and search_title.strip() != "Senza Titolo":
                metadata = await self._fetch_tvmaze(search_title)

        if metadata:
            self._cache[cache_key] = metadata
            self._apply_tv_metadata(series, metadata)

        return series

    async def _fetch_tmdb_movie(self, movie: Movie, api_key: str | None = None) -> dict[str, Any] | None:
        """Fetch movie metadata from TMDb including certification."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        try:
            tmdb_id = movie.tmdb_id
            if not tmdb_id:
                clean_title = self._clean_title(movie.title) if movie.title and movie.title.strip() != "Senza Titolo" else ""
                if not clean_title and movie.id:
                    clean_id = movie.id.replace("sc-", "")
                    if "-" in clean_id:
                        slug_part = clean_id.split("-", 1)[1]
                        clean_title = self._clean_title(slug_part.replace("-", " "))
                if clean_title:
                    search_url = f"{TMDB_BASE_URL}/search/movie"
                    params: dict[str, Any] = {"query": clean_title, "language": "it-IT", **auth_params}
                    if movie.year:
                        params["year"] = str(movie.year)
                    data = await self._get_json(search_url, params=params, headers=auth_headers)
                    if data and data.get("results"):
                        tmdb_id = data["results"][0].get("id")

            if not tmdb_id:
                return None

            detail_url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
            params = {"language": "it-IT", "append_to_response": "credits,release_dates,watch/providers", **auth_params}
            return await self._get_json(detail_url, params=params, headers=auth_headers)
        except Exception as err:
            _LOGGER.debug("TMDb fetch movie failed for %s: %s", movie.title, err)
            return None

    async def _fetch_tmdb_tv(self, series: TvSeries, api_key: str | None = None) -> dict[str, Any] | None:
        """Fetch TV series metadata from TMDb including content ratings and watch providers."""
        auth_headers, auth_params = self._get_tmdb_auth(api_key)
        try:
            tmdb_id = series.tmdb_id
            if not tmdb_id:
                clean_title = self._clean_title(series.title) if series.title and series.title.strip() != "Senza Titolo" else ""
                if not clean_title and series.id:
                    clean_id = series.id.replace("sc-", "")
                    if "-" in clean_id:
                        slug_part = clean_id.split("-", 1)[1]
                        clean_title = self._clean_title(slug_part.replace("-", " "))
                if clean_title:
                    search_url = f"{TMDB_BASE_URL}/search/tv"
                    params: dict[str, Any] = {"query": clean_title, "language": "it-IT", **auth_params}
                    if series.year:
                        params["first_air_date_year"] = str(series.year)
                    data = await self._get_json(search_url, params=params, headers=auth_headers)
                    if data and data.get("results"):
                        tmdb_id = data["results"][0].get("id")

            if not tmdb_id:
                return None

            detail_url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
            params = {
                "language": "it-IT",
                "append_to_response": "credits,content_ratings,watch/providers,external_ids",
                **auth_params,
            }
            return await self._get_json(detail_url, params=params, headers=auth_headers)
        except Exception as err:
            _LOGGER.debug("TMDb fetch TV series failed for %s: %s", series.title, err)
            return None

    async def _fetch_cinemeta(self, media_type: str, imdb_id: str) -> dict[str, Any] | None:
        """Fetch metadata from Cinemeta using IMDb ID."""
        url = f"{CINEMETA_BASE_URL}/{media_type}/{imdb_id}.json"
        data = await self._get_json(url)
        if data and isinstance(data, dict):
            return data.get("meta")
        return None

    async def _fetch_tvmaze(self, title: str) -> dict[str, Any] | None:
        """Fetch TV show metadata from TVmaze API."""
        clean_title = self._clean_title(title)
        url = f"https://api.tvmaze.com/singlesearch/shows?q={quote_plus(clean_title)}"
        data = await self._get_json(url)
        if data and isinstance(data, dict):
            genres = data.get("genres", [])
            rating_obj = data.get("rating", {})
            rating = rating_obj.get("average") if isinstance(rating_obj, dict) else None
            summary = data.get("summary")
            if summary:
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            image = data.get("image", {})
            poster = image.get("original") or image.get("medium") if isinstance(image, dict) else None
            return {
                "name": data.get("name"),
                "overview": summary,
                "poster_url": poster,
                "genres": genres,
                "vote_average": rating,
            }
        return None

    def _apply_movie_metadata(self, movie: Movie, meta: dict[str, Any]) -> None:
        """Apply enriched metadata to Movie object."""
        # Ensure title is populated if missing or placeholder
        if not movie.title or movie.title.strip() in ("", "Senza Titolo"):
            resolved_title = (
                meta.get("title")
                or meta.get("name")
                or meta.get("original_title")
                or meta.get("original_name")
            )
            if resolved_title:
                movie.title = str(resolved_title)

        if meta.get("id"):
            with contextlib.suppress(Exception):
                movie.tmdb_id = int(meta["id"])
        if meta.get("imdb_id"):
            movie.imdb_id = str(meta["imdb_id"])

        if meta.get("overview"):
            movie.description = meta["overview"]

        if meta.get("poster_path"):
            movie.poster_url = f"{TMDB_IMAGE_BASE}{meta['poster_path']}"
        elif meta.get("poster") and not movie.poster_url:
            movie.poster_url = meta["poster"]
        elif meta.get("poster_url") and not movie.poster_url:
            movie.poster_url = meta["poster_url"]

        if meta.get("backdrop_path"):
            movie.backdrop_url = f"{TMDB_BACKDROP_BASE}{meta['backdrop_path']}"
        elif meta.get("background") and not movie.backdrop_url:
            movie.backdrop_url = meta["background"]

        if meta.get("vote_average"):
            with contextlib.suppress(Exception):
                movie.rating = round(float(meta["vote_average"]), 1)
        elif meta.get("imdbRating") and not movie.rating:
            with contextlib.suppress(Exception):
                movie.rating = round(float(meta["imdbRating"]), 1)

        if meta.get("runtime") and not movie.duration:
            movie.duration = int(meta["runtime"])

        # Extract certification (Italian priority, then US, then any)
        release_dates = meta.get("release_dates", {})
        if isinstance(release_dates, dict) and "results" in release_dates:
            results = release_dates.get("results", [])
            it_entry = next((r for r in results if r.get("iso_3166_1") == "IT"), None)
            us_entry = next((r for r in results if r.get("iso_3166_1") == "US"), None)
            target_entry = it_entry or us_entry or (results[0] if results else None)
            if target_entry:
                for rd in target_entry.get("release_dates", []):
                    cert = rd.get("certification")
                    if cert:
                        movie.certification = str(cert)
                        break

        if not movie.certification and meta.get("certification"):
            movie.certification = str(meta["certification"])

        # Check adult flag and certification
        if (
            meta.get("adult")
            or meta.get("is_adult")
            or (
                movie.certification
                and movie.certification.upper().strip() in ("VM18", "VM 18", "18+", "+18", "NC-17", "PEGI 18", "XXX")
            )
        ):
            movie.is_adult = True

        if meta.get("genres"):
            genres = []
            for g in meta["genres"]:
                if isinstance(g, dict) and "name" in g:
                    genres.append(g["name"])
                elif isinstance(g, str):
                    genres.append(g)
            if genres:
                movie.genres = genres
                if any(
                    ag in [x.lower() for x in genres]
                    for ag in (
                        "erotico",
                        "erotica",
                        "erotismo",
                        "pornografico",
                        "porno",
                        "softcore",
                        "hardcore",
                        "hentai",
                        "xxx",
                        "adulti",
                        "adult",
                    )
                ):
                    movie.is_adult = True

        if meta.get("credits"):
            credits = meta["credits"]
            cast = [c["name"] for c in credits.get("cast", [])[:5] if "name" in c]
            if cast:
                movie.cast = cast
            crew = credits.get("crew", [])
            for cr in crew:
                if cr.get("job") == "Director":
                    movie.director = cr.get("name")
                    break

        # Extract watch providers if returned by TMDb
        wp_data = meta.get("watch/providers") or meta.get("watch_providers")
        if isinstance(wp_data, dict) and "results" in wp_data:
            movie.watch_providers = wp_data.get("results", {})

    def _apply_tv_metadata(self, series: TvSeries, meta: dict[str, Any]) -> None:
        """Apply enriched metadata to TvSeries object."""
        # Ensure title is populated if missing or placeholder
        if not series.title or series.title.strip() in ("", "Senza Titolo"):
            resolved_title = (
                meta.get("name")
                or meta.get("title")
                or meta.get("original_name")
                or meta.get("original_title")
            )
            if resolved_title:
                series.title = str(resolved_title)

        if meta.get("id"):
            with contextlib.suppress(Exception):
                series.tmdb_id = int(meta["id"])
        if meta.get("imdb_id"):
            series.imdb_id = str(meta["imdb_id"])
        elif (
            meta.get("external_ids") and isinstance(meta["external_ids"], dict) and meta["external_ids"].get("imdb_id")
        ):
            series.imdb_id = str(meta["external_ids"]["imdb_id"])

        if meta.get("overview"):
            series.description = meta["overview"]

        if meta.get("poster_path"):
            series.poster_url = f"{TMDB_IMAGE_BASE}{meta['poster_path']}"
        elif meta.get("poster") and not series.poster_url:
            series.poster_url = meta["poster"]
        elif meta.get("poster_url") and not series.poster_url:
            series.poster_url = meta["poster_url"]

        if meta.get("backdrop_path"):
            series.backdrop_url = f"{TMDB_BACKDROP_BASE}{meta['backdrop_path']}"
        elif meta.get("background") and not series.backdrop_url:
            series.backdrop_url = meta["background"]

        if meta.get("vote_average"):
            with contextlib.suppress(Exception):
                series.rating = round(float(meta["vote_average"]), 1)
        elif meta.get("imdbRating") and not series.rating:
            with contextlib.suppress(Exception):
                series.rating = round(float(meta["imdbRating"]), 1)

        # Extract TV content ratings (Italian priority, then US, then any)
        content_ratings = meta.get("content_ratings", {})
        if isinstance(content_ratings, dict) and "results" in content_ratings:
            results = content_ratings.get("results", [])
            it_entry = next((r for r in results if r.get("iso_3166_1") == "IT"), None)
            us_entry = next((r for r in results if r.get("iso_3166_1") == "US"), None)
            target = it_entry or us_entry or (results[0] if results else None)
            if target and target.get("rating"):
                series.certification = str(target.get("rating"))

        if not series.certification and meta.get("certification"):
            series.certification = str(meta["certification"])

        if (
            meta.get("adult")
            or meta.get("is_adult")
            or (
                series.certification
                and series.certification.upper().strip()
                in ("VM18", "VM 18", "18+", "+18", "TV-MA", "NC-17", "PEGI 18", "XXX")
            )
        ):
            series.is_adult = True

        # Extract watch providers if returned by TMDb
        wp_data = meta.get("watch/providers") or meta.get("watch_providers")
        if isinstance(wp_data, dict) and "results" in wp_data:
            series.watch_providers = wp_data.get("results", {})

        if meta.get("genres"):
            genres = []
            for g in meta["genres"]:
                if isinstance(g, dict) and "name" in g:
                    genres.append(g["name"])
                elif isinstance(g, str):
                    genres.append(g)
            if genres:
                series.genres = genres
                if any(
                    ag in [x.lower() for x in genres]
                    for ag in (
                        "erotico",
                        "erotica",
                        "erotismo",
                        "pornografico",
                        "porno",
                        "softcore",
                        "hardcore",
                        "hentai",
                        "xxx",
                        "adulti",
                        "adult",
                    )
                ):
                    series.is_adult = True

    async def enrich_tv_season(self, series_tmdb_id: int | None, season: Any) -> Any:
        """Enrich TV season episodes with TMDb episode titles, overviews, and screenshots."""
        if not self.tmdb_api_key or not series_tmdb_id:
            return season

        auth_headers, auth_params = self._get_tmdb_auth()
        season_url = f"{TMDB_BASE_URL}/tv/{series_tmdb_id}/season/{season.number}"
        params = {"language": "it-IT", **auth_params}
        try:
            data = await self._get_json(season_url, params=params, headers=auth_headers)
            if not data or "episodes" not in data:
                return season

            tmdb_eps = {e["episode_number"]: e for e in data["episodes"] if "episode_number" in e}
            for ep in season.episodes:
                t_ep = tmdb_eps.get(ep.episode_number)
                if not t_ep:
                    continue
                ep_name = (t_ep.get("name") or "").strip()
                if ep_name:
                    if not ep.title or ep.title.lower().startswith("episodio"):
                        ep.title = f"Episodio {ep.episode_number}: {ep_name}"
                    else:
                        ep.title = f"{ep.title} - {ep_name}"
                if t_ep.get("overview") and not ep.description:
                    ep.description = t_ep["overview"]
                if t_ep.get("still_path") and not ep.poster_url:
                    ep.poster_url = f"{TMDB_IMAGE_BASE}{t_ep['still_path']}"
        except Exception as err:
            _LOGGER.debug("TMDb enrich season %s failed: %s", season.number, err)

        return season
