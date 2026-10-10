"""SQLite Persistence Database for Streaming Hub.

Stores titles, posters, descriptions, TV seasons/episodes,
watch history, and user favorites persistently in /data/streaming_hub.db.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
import re
import sqlite3
from typing import Any

from .models import Movie, ProviderSource, TvEpisode, TvSeason, TvSeries

_LOGGER = logging.getLogger(__name__)

# Determine database path: /data for Home Assistant Add-on persistence, ./data for local dev
HA_DATA_DIR = Path("/data")
LOCAL_DATA_DIR = Path("./data")


def slug_to_title(media_id: str) -> str:
    """Derive human-readable title from a media ID slug if possible."""
    clean = media_id.replace("sc-", "")
    if "-" in clean:
        parts = clean.split("-", 1)
        slug_part = parts[1]
        slug_part = re.sub(r"_s\d+e\d+$", "", slug_part)
        words = re.sub(r"[_\-]+", " ", slug_part).strip().title()
        if words:
            return words
    return ""


def get_db_path() -> Path:
    """Return the SQLite database path depending on environment."""
    if HA_DATA_DIR.exists() and HA_DATA_DIR.is_dir():
        return HA_DATA_DIR / "streaming_hub.db"
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_DATA_DIR / "streaming_hub.db"


class MediaDatabase:
    """Persistent SQLite database manager."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize database manager."""
        self._db_path = db_path or get_db_path()
        self._lock = asyncio.Lock()

    @contextlib.contextmanager
    def _get_connection(self) -> Any:
        """Get a configured SQLite connection and ensure clean close."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    async def init(self) -> None:
        """Initialize tables and indexes."""
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        """Synchronously create tables and perform migrations."""
        _LOGGER.info("Initializing persistent SQLite database at %s", self._db_path)
        with self._get_connection() as conn:
            # 1. Base Tables Creation (if not exists)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS titles (
                    id TEXT PRIMARY KEY,
                    media_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    original_title TEXT,
                    year INTEGER,
                    poster_url TEXT,
                    backdrop_url TEXT,
                    description TEXT,
                    genres TEXT,
                    duration INTEGER,
                    rating REAL,
                    certification TEXT,
                    cast_list TEXT,
                    director TEXT,
                    source_a_url TEXT,
                    source_b_url TEXT,
                    tmdb_id INTEGER,
                    imdb_id TEXT,
                    trakt_id INTEGER,
                    catalogs TEXT,
                    sources TEXT,
                    raw_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS seasons (
                    id TEXT PRIMARY KEY,
                    series_id TEXT NOT NULL,
                    season_number INTEGER NOT NULL,
                    episodes_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS watch_history (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL DEFAULT 'default',
                    media_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    poster_url TEXT,
                    media_type TEXT NOT NULL,
                    season_number INTEGER,
                    episode_number INTEGER,
                    progress_seconds REAL DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL DEFAULT 'default',
                    title_id TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    poster_url TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tmdb_sessions (
                    profile_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    account_id INTEGER,
                    username TEXT,
                    avatar_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Safe SQLite Schema Migrations for existing user databases
            try:
                conn.execute("ALTER TABLE titles ADD COLUMN source_a_url TEXT;")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE titles ADD COLUMN source_b_url TEXT;")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE titles ADD COLUMN certification TEXT;")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE titles ADD COLUMN watch_providers TEXT;")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE titles ADD COLUMN is_adult INTEGER DEFAULT 0;")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE titles ADD COLUMN trakt_id INTEGER;")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE watch_history ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default';")
            except Exception:
                pass

            try:
                conn.execute("ALTER TABLE favorites ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default';")
            except Exception:
                pass

            # 3. Create Indexes (guaranteed that all columns exist)
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_titles_type ON titles(media_type);
                CREATE INDEX IF NOT EXISTS idx_titles_title ON titles(title);
                CREATE INDEX IF NOT EXISTS idx_titles_updated ON titles(updated_at);

                CREATE INDEX IF NOT EXISTS idx_seasons_series ON seasons(series_id, season_number);
                CREATE INDEX IF NOT EXISTS idx_seasons_updated ON seasons(updated_at);

                CREATE INDEX IF NOT EXISTS idx_history_updated ON watch_history(profile_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_history_profile_media ON watch_history(profile_id, media_id);

                CREATE INDEX IF NOT EXISTS idx_favorites_profile ON favorites(profile_id, added_at DESC);
                CREATE INDEX IF NOT EXISTS idx_favorites_profile_title ON favorites(profile_id, title_id);
            """)

            # 4. Auto-heal any corrupted / empty titles in existing user databases
            self._migrate_and_heal_sync(conn)

    def _migrate_and_heal_sync(self, conn: sqlite3.Connection) -> None:
        """Heal corrupted or empty titles in titles, favorites, and watch_history."""
        try:
            # 1. Heal empty titles in titles table
            cursor = conn.execute(
                "SELECT id, title, original_title, raw_json FROM titles WHERE title IS NULL OR title = '' OR title = 'Senza Titolo'"
            )
            rows = cursor.fetchall()
            for row in rows:
                media_id = str(row["id"])
                healed_title = ""
                if row["raw_json"]:
                    with contextlib.suppress(Exception):
                        data = json.loads(row["raw_json"])
                        healed_title = (
                            data.get("name")
                            or data.get("title")
                            or data.get("original_name")
                            or data.get("original_title")
                            or ""
                        )
                if not healed_title and row["original_title"]:
                    healed_title = str(row["original_title"])
                if not healed_title:
                    healed_title = slug_to_title(media_id)
                if healed_title:
                    conn.execute("UPDATE titles SET title = ? WHERE id = ?", (healed_title, media_id))

            # 2. Heal favorites
            cursor = conn.execute(
                """
                SELECT f.id, f.title_id, f.title, f.poster_url, t.title as canonical_title, t.poster_url as canonical_poster, t.raw_json
                FROM favorites f
                LEFT JOIN titles t ON f.title_id = t.id
                WHERE f.title IS NULL OR f.title = '' OR f.title = 'Senza Titolo' OR f.poster_url IS NULL OR f.poster_url = ''
                """
            )
            fav_rows = cursor.fetchall()
            for row in fav_rows:
                fav_id = row["id"]
                title_id = str(row["title_id"])
                cur_title = str(row["title"] or "")
                cur_poster = str(row["poster_url"] or "")
                new_title = cur_title
                new_poster = cur_poster

                if not cur_title or cur_title == "Senza Titolo":
                    if row["canonical_title"] and row["canonical_title"] != "Senza Titolo":
                        new_title = str(row["canonical_title"])
                    elif row["raw_json"]:
                        with contextlib.suppress(Exception):
                            data = json.loads(row["raw_json"])
                            new_title = str(data.get("name") or data.get("title") or "")
                    if not new_title or new_title == "Senza Titolo":
                        new_title = slug_to_title(title_id) or "Senza Titolo"

                if not new_poster and row["canonical_poster"]:
                    new_poster = str(row["canonical_poster"])

                conn.execute(
                    "UPDATE favorites SET title = ?, poster_url = ? WHERE id = ?",
                    (new_title, new_poster, fav_id),
                )

            # 3. Heal watch_history
            cursor = conn.execute(
                """
                SELECT h.id, h.media_id, h.title, h.poster_url, t.title as canonical_title, t.poster_url as canonical_poster, t.raw_json
                FROM watch_history h
                LEFT JOIN titles t ON h.media_id = t.id
                WHERE h.title IS NULL OR h.title = '' OR h.title = 'Senza Titolo' OR h.poster_url IS NULL OR h.poster_url = ''
                """
            )
            hist_rows = cursor.fetchall()
            for row in hist_rows:
                hist_id = row["id"]
                media_id = str(row["media_id"])
                cur_title = str(row["title"] or "")
                cur_poster = str(row["poster_url"] or "")
                new_title = cur_title
                new_poster = cur_poster

                if not cur_title or cur_title == "Senza Titolo":
                    if row["canonical_title"] and row["canonical_title"] != "Senza Titolo":
                        new_title = str(row["canonical_title"])
                    elif row["raw_json"]:
                        with contextlib.suppress(Exception):
                            data = json.loads(row["raw_json"])
                            new_title = str(data.get("name") or data.get("title") or "")
                    if not new_title or new_title == "Senza Titolo":
                        new_title = slug_to_title(media_id) or "Senza Titolo"

                if not new_poster and row["canonical_poster"]:
                    new_poster = str(row["canonical_poster"])

                conn.execute(
                    "UPDATE watch_history SET title = ?, poster_url = ? WHERE id = ?",
                    (new_title, new_poster, hist_id),
                )

            # 4. Clean up corrupted / spurious episode records erroneously stored as movies
            conn.execute("DELETE FROM watch_history WHERE media_type = 'movie' AND media_id GLOB '*_s[0-9]*e[0-9]*';")
            _LOGGER.debug("Database migration and auto-healing completed successfully")
        except Exception as err:
            _LOGGER.warning("Database auto-healing error (non-fatal): %s", err)

    async def save_title(self, item: Movie | TvSeries) -> None:
        """Persist a movie or TV series title with metadata to SQLite."""
        async with self._lock:
            await asyncio.to_thread(self._save_title_sync, item)

    def _save_title_sync(self, item: Movie | TvSeries) -> None:
        """Synchronously upsert a title."""
        media_type = "tv" if isinstance(item, TvSeries) else "movie"
        cast_json = json.dumps(item.cast or [])
        genres_json = json.dumps(item.genres or [])
        catalogs_json = json.dumps(item.catalogs or [])
        sources_json = json.dumps([s.to_dict() for s in getattr(item, "sources", [])])
        watch_providers_json = json.dumps(getattr(item, "watch_providers", {}) or {})
        raw_json = json.dumps(item.to_dict())
        is_adult_val = 1 if getattr(item, "is_adult", False) else 0

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO titles (
                    id, media_type, title, original_title, year,
                    poster_url, backdrop_url, description, genres,
                    duration, rating, certification, is_adult, cast_list, director,
                    source_a_url, source_b_url,
                    tmdb_id, imdb_id, trakt_id, catalogs, sources, watch_providers, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title=CASE
                        WHEN excluded.title IS NOT NULL AND excluded.title != '' AND excluded.title != 'Senza Titolo'
                        THEN excluded.title
                        ELSE titles.title
                    END,
                    original_title=excluded.original_title,
                    year=excluded.year,
                    poster_url=COALESCE(excluded.poster_url, titles.poster_url),
                    backdrop_url=COALESCE(excluded.backdrop_url, titles.backdrop_url),
                    description=COALESCE(excluded.description, titles.description),
                    genres=excluded.genres,
                    duration=COALESCE(excluded.duration, titles.duration),
                    rating=COALESCE(excluded.rating, titles.rating),
                    certification=COALESCE(excluded.certification, titles.certification),
                    is_adult=excluded.is_adult,
                    cast_list=excluded.cast_list,
                    director=COALESCE(excluded.director, titles.director),
                    source_a_url=COALESCE(excluded.source_a_url, titles.source_a_url),
                    source_b_url=COALESCE(excluded.source_b_url, titles.source_b_url),
                    tmdb_id=COALESCE(excluded.tmdb_id, titles.tmdb_id),
                    imdb_id=COALESCE(excluded.imdb_id, titles.imdb_id),
                    trakt_id=COALESCE(excluded.trakt_id, titles.trakt_id),
                    catalogs=excluded.catalogs,
                    sources=excluded.sources,
                    watch_providers=excluded.watch_providers,
                    raw_json=excluded.raw_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    item.id,
                    media_type,
                    item.title,
                    getattr(item, "original_title", None),
                    item.year,
                    item.poster_url,
                    item.backdrop_url,
                    item.description,
                    genres_json,
                    getattr(item, "duration", None),
                    item.rating,
                    getattr(item, "certification", None),
                    is_adult_val,
                    cast_json,
                    item.director,
                    getattr(item, "source_a_url", None) or "",
                    getattr(item, "source_b_url", None) or "",
                    item.tmdb_id,
                    item.imdb_id,
                    getattr(item, "trakt_id", None),
                    catalogs_json,
                    sources_json,
                    watch_providers_json,
                    raw_json,
                ),
            )

    async def get_title_record(self, title_id: str) -> dict[str, Any] | None:
        """Retrieve cached title record with cache age metadata from SQLite."""
        async with self._lock:
            return await asyncio.to_thread(self._get_title_record_sync, title_id)

    def _get_title_record_sync(self, title_id: str) -> dict[str, Any] | None:
        """Synchronously get title record with age by id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT raw_json, updated_at,
                       (strftime('%s', 'now') - strftime('%s', updated_at)) AS age_seconds
                FROM titles WHERE id = ?
                """,
                (title_id,),
            )
            row = cursor.fetchone()
            if row and row["raw_json"]:
                try:
                    data = json.loads(row["raw_json"])
                    age = int(row["age_seconds"]) if row["age_seconds"] is not None else 0
                    return {
                        "data": data,
                        "age_seconds": max(0, age),
                        "updated_at": str(row["updated_at"] or ""),
                    }
                except Exception as err:
                    _LOGGER.warning("Corrupted raw_json for title %s: %s", title_id, err)
        return None

    async def get_title(self, title_id: str) -> dict[str, Any] | None:
        """Retrieve cached title dictionary from SQLite."""
        rec = await self.get_title_record(title_id)
        return rec["data"] if rec else None

    def _get_title_sync(self, title_id: str) -> dict[str, Any] | None:
        """Synchronously get title by id."""
        rec = self._get_title_record_sync(title_id)
        return rec["data"] if rec else None

    async def get_titles_watch_providers(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """Retrieve cached watch_providers dict for given title IDs."""
        async with self._lock:
            return await asyncio.to_thread(self._get_titles_watch_providers_sync, ids)

    def _get_titles_watch_providers_sync(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        res = {}
        with self._get_connection() as conn:
            chunk_size = 100
            for i in range(0, len(ids), chunk_size):
                chunk = ids[i : i + chunk_size]
                placeholders = ",".join("?" * len(chunk))
                cursor = conn.execute(
                    f"SELECT id, watch_providers FROM titles WHERE id IN ({placeholders})",
                    chunk,
                )
                for row in cursor.fetchall():
                    raw_wp = row["watch_providers"]
                    if raw_wp:
                        try:
                            wp = json.loads(raw_wp)
                            if wp and isinstance(wp, dict):
                                res[str(row["id"])] = wp
                        except Exception:
                            pass
        return res

    async def update_title_watch_providers(
        self,
        title_id: str,
        watch_providers: dict[str, Any],
        media_type: str = "movie",
        title: str = "",
        year: int | None = None,
        tmdb_id: int | None = None,
        rating: float | None = None,
        certification: str | None = None,
    ) -> None:
        """Upsert title watch_providers and basic enriched metadata in SQLite."""
        async with self._lock:
            await asyncio.to_thread(
                self._update_title_watch_providers_sync,
                title_id,
                watch_providers,
                media_type,
                title,
                year,
                tmdb_id,
                rating,
                certification,
            )

    def _update_title_watch_providers_sync(
        self,
        title_id: str,
        watch_providers: dict[str, Any],
        media_type: str = "movie",
        title: str = "",
        year: int | None = None,
        tmdb_id: int | None = None,
        rating: float | None = None,
        certification: str | None = None,
    ) -> None:
        wp_json = json.dumps(watch_providers or {})
        effective_title = title
        if not effective_title or effective_title.strip() in ("", "Senza Titolo"):
            effective_title = slug_to_title(title_id) or "Senza Titolo"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO titles (id, media_type, title, year, tmdb_id, rating, certification, watch_providers, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title = CASE
                        WHEN excluded.title IS NOT NULL AND excluded.title != '' AND excluded.title != 'Senza Titolo'
                        THEN excluded.title
                        ELSE titles.title
                    END,
                    watch_providers = excluded.watch_providers,
                    tmdb_id = COALESCE(excluded.tmdb_id, titles.tmdb_id),
                    rating = COALESCE(excluded.rating, titles.rating),
                    certification = COALESCE(excluded.certification, titles.certification),
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (title_id, media_type, effective_title, year, tmdb_id, rating, certification, wp_json),
            )

    async def enrich_items_with_cached_metadata(self, items: list[Any]) -> None:
        """Enrich a batch of items in-place with SQLite-cached metadata."""
        if not items:
            return
        async with self._lock:
            await asyncio.to_thread(self._enrich_items_sync, items)

    def _enrich_items_sync(self, items: list[Any]) -> None:
        """Synchronously match and enrich items with cached certification, duration, rating, watch_providers and genres."""
        id_map: dict[str, Any] = {}
        for it in items:
            mid = it.get("id") if isinstance(it, dict) else getattr(it, "id", None)
            if mid:
                id_map[str(mid)] = it

        if not id_map:
            return

        with self._get_connection() as conn:
            keys = list(id_map.keys())
            chunk_size = 100
            for i in range(0, len(keys), chunk_size):
                chunk = keys[i : i + chunk_size]
                placeholders = ",".join("?" * len(chunk))
                cursor = conn.execute(
                    f"SELECT id, certification, is_adult, duration, rating, watch_providers, genres, tmdb_id, source_a_url, source_b_url, poster_url, backdrop_url FROM titles WHERE id IN ({placeholders})",
                    chunk,
                )
                for row in cursor.fetchall():
                    tid = str(row["id"])
                    target = id_map.get(tid)
                    if not target:
                        continue
                    cert = row["certification"]
                    is_adult_db = bool(row["is_adult"])
                    dur = row["duration"]
                    rat = row["rating"]
                    raw_wp = row["watch_providers"]
                    raw_g = row["genres"]
                    src_a = row["source_a_url"]
                    src_b = row["source_b_url"]

                    if cert:
                        if isinstance(target, dict):
                            target["certification"] = cert
                        else:
                            target.certification = cert
                    if is_adult_db:
                        if isinstance(target, dict):
                            target["is_adult"] = True
                        else:
                            target.is_adult = True
                    if dur is not None:
                        if isinstance(target, dict):
                            if not target.get("duration"):
                                target["duration"] = dur
                        elif not getattr(target, "duration", None):
                            target.duration = dur
                    if rat is not None:
                        if isinstance(target, dict):
                            if not target.get("rating"):
                                target["rating"] = rat
                        elif not getattr(target, "rating", None):
                            target.rating = rat
                    if raw_wp:
                        try:
                            wp_dict = json.loads(raw_wp)
                            if wp_dict:
                                if isinstance(target, dict):
                                    target["watch_providers"] = wp_dict
                                else:
                                    target.watch_providers = wp_dict
                        except Exception:
                            pass
                    if raw_g:
                        try:
                            g_list = (
                                json.loads(raw_g)
                                if raw_g.startswith("[")
                                else [x.strip() for x in raw_g.split(",") if x.strip()]
                            )
                            if g_list:
                                if isinstance(target, dict):
                                    if not target.get("genres"):
                                        target["genres"] = g_list
                                elif not getattr(target, "genres", None):
                                    target.genres = g_list
                        except Exception:
                            pass
                    db_poster = row["poster_url"]
                    db_backdrop = row["backdrop_url"]

                    if db_poster:
                        if isinstance(target, dict):
                            if not target.get("poster_url"):
                                target["poster_url"] = db_poster
                        elif not getattr(target, "poster_url", None):
                            target.poster_url = db_poster

                    if db_backdrop:
                        if isinstance(target, dict):
                            if not target.get("backdrop_url"):
                                target["backdrop_url"] = db_backdrop
                        elif not getattr(target, "backdrop_url", None):
                            target.backdrop_url = db_backdrop

                    if src_a:
                        if isinstance(target, dict) and not target.get("source_a_url"):
                            target["source_a_url"] = src_a
                        elif not getattr(target, "source_a_url", None):
                            target.source_a_url = src_a
                    if src_b:
                        if isinstance(target, dict) and not target.get("source_b_url"):
                            target["source_b_url"] = src_b
                        elif not getattr(target, "source_b_url", None):
                            target.source_b_url = src_b

    async def get_titles_by_genre(
        self,
        genre: str,
        media_type: str = "movie",
        limit: int = 40,
    ) -> list[Movie | TvSeries]:
        """Retrieve cached titles matching a genre."""
        async with self._lock:
            return await asyncio.to_thread(self._get_titles_by_genre_sync, genre, media_type, limit)

    def _get_titles_by_genre_sync(
        self,
        genre: str,
        media_type: str = "movie",
        limit: int = 40,
    ) -> list[Movie | TvSeries]:
        """Synchronously query titles matching a genre."""
        pattern = f"%{genre.lower()}%"
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT raw_json, media_type FROM titles
                WHERE (media_type = ? OR ? = 'all')
                  AND LOWER(genres) LIKE ?
                ORDER BY year DESC, rating DESC
                LIMIT ?
                """,
                (media_type, media_type, pattern, limit),
            )
            rows = cursor.fetchall()
            items: list[Movie | TvSeries] = []
            for row in rows:
                if row["raw_json"]:
                    try:
                        data = json.loads(row["raw_json"])
                        if row["media_type"] == "tv":
                            items.append(TvSeries.from_dict(data))
                        else:
                            items.append(Movie.from_dict(data))
                    except Exception:
                        continue
            return items

    async def save_season(self, series_id: str, season: TvSeason) -> None:
        """Persist a season with all its episodes to SQLite."""
        async with self._lock:
            await asyncio.to_thread(self._save_season_sync, series_id, season)

    def _save_season_sync(self, series_id: str, season: TvSeason) -> None:
        """Synchronously upsert a season and episodes."""
        season_id = f"{series_id}_s{season.number}"
        episodes_json = json.dumps([ep.to_dict() for ep in season.episodes])

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO seasons (id, series_id, season_number, episodes_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    episodes_json=excluded.episodes_json,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (season_id, series_id, season.number, episodes_json),
            )

    async def get_season_record(self, series_id: str, season_number: int) -> dict[str, Any] | None:
        """Retrieve a cached season with age metadata from SQLite."""
        async with self._lock:
            return await asyncio.to_thread(self._get_season_record_sync, series_id, season_number)

    def _get_season_record_sync(self, series_id: str, season_number: int) -> dict[str, Any] | None:
        """Synchronously get season record with age by series_id and season_number."""
        season_id = f"{series_id}_s{season_number}"
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT episodes_json, updated_at,
                       (strftime('%s', 'now') - strftime('%s', updated_at)) AS age_seconds
                FROM seasons WHERE id = ?
                """,
                (season_id,),
            )
            row = cursor.fetchone()
            if not row or not row["episodes_json"]:
                return None

            try:
                raw_episodes = json.loads(row["episodes_json"])
                episodes: list[TvEpisode] = []
                for ep in raw_episodes:
                    sources = [
                        ProviderSource(
                            id=s.get("id", ""),
                            media_id=s.get("media_id", ""),
                            provider_id=s.get("provider_id", ""),
                            provider_name=s.get("provider_name", ""),
                            page_url=s.get("page_url", ""),
                            language=s.get("language", "ita"),
                            quality=s.get("quality", "1080p FHD"),
                            available=s.get("available", True),
                        )
                        for s in ep.get("sources", [])
                    ]
                    episodes.append(
                        TvEpisode(
                            id=ep.get("id", ""),
                            media_id=ep.get("media_id", series_id),
                            season_number=season_number,
                            episode_number=int(ep.get("episode_number", 1)),
                            title=ep.get("title", ""),
                            description=ep.get("description"),
                            poster_url=ep.get("poster_url"),
                            sources=sources,
                        )
                    )
                season = TvSeason(number=season_number, episodes=episodes)
                age = int(row["age_seconds"]) if row["age_seconds"] is not None else 0
                return {
                    "season": season,
                    "age_seconds": max(0, age),
                    "updated_at": str(row["updated_at"] or ""),
                }
            except Exception as err:
                _LOGGER.warning("Error parsing cached season %s: %s", season_id, err)
                return None

    async def get_season(self, series_id: str, season_number: int) -> TvSeason | None:
        """Retrieve a cached season with its episodes from SQLite."""
        rec = await self.get_season_record(series_id, season_number)
        return rec["season"] if rec else None

    def _get_season_sync(self, series_id: str, season_number: int) -> TvSeason | None:
        """Synchronously get season by series_id and season_number."""
        rec = self._get_season_record_sync(series_id, season_number)
        return rec["season"] if rec else None

    async def get_next_episode(
        self,
        series_id: str,
        season_number: int,
        episode_number: int,
    ) -> dict[str, Any] | None:
        """Find the next episode in the same season or first episode of the subsequent season."""
        async with self._lock:
            return await asyncio.to_thread(
                self._get_next_episode_sync,
                series_id,
                season_number,
                episode_number,
            )

    def _get_next_episode_sync(
        self,
        series_id: str,
        season_number: int,
        episode_number: int,
    ) -> dict[str, Any] | None:
        """Synchronously determine the subsequent episode from cached seasons."""
        # 1. Look in the current season for episode_number + 1
        current_season = self._get_season_sync(series_id, season_number)
        if current_season and current_season.episodes:
            for ep in current_season.episodes:
                if ep.episode_number == episode_number + 1:
                    return {
                        "series_id": series_id,
                        "season_number": season_number,
                        "episode_number": ep.episode_number,
                        "episode": ep.to_dict(),
                    }

        # 2. Check title's known seasons if title record exists to avoid false season jumps
        title_data = self._get_title_sync(series_id)
        if title_data and title_data.get("seasons"):
            known_season_nums = {
                int(s.get("number", s.get("season_number", 0)))
                for s in title_data["seasons"]
                if isinstance(s, dict) and (s.get("number") is not None or s.get("season_number") is not None)
            }
            if known_season_nums and (season_number + 1) not in known_season_nums:
                return None

        # 3. Look in the next season for episode 1 (or lowest episode number)
        next_season = self._get_season_sync(series_id, season_number + 1)
        if next_season and next_season.episodes and next_season.number == season_number + 1:
            valid_eps = [
                ep
                for ep in next_season.episodes
                if getattr(ep, "season_number", season_number + 1) == season_number + 1
            ]
            if valid_eps:
                sorted_eps = sorted(valid_eps, key=lambda e: e.episode_number)
                target_ep = sorted_eps[0]
                return {
                    "series_id": series_id,
                    "season_number": season_number + 1,
                    "episode_number": target_ep.episode_number,
                    "episode": target_ep.to_dict(),
                }

        return None

    async def save_watch_progress(
        self,
        media_id: str,
        title: str,
        media_type: str,
        poster_url: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
        progress_seconds: float = 0,
        duration_seconds: float = 0,
        profile_id: str = "default",
    ) -> None:
        """Save playback progress into watch_history table scoped by profile_id."""
        async with self._lock:
            await asyncio.to_thread(
                self._save_watch_progress_sync,
                media_id,
                title,
                media_type,
                poster_url,
                season_number,
                episode_number,
                progress_seconds,
                duration_seconds,
                profile_id,
            )

    def _save_watch_progress_sync(
        self,
        media_id: str,
        title: str,
        media_type: str,
        poster_url: str | None,
        season_number: int | None,
        episode_number: int | None,
        progress_seconds: float,
        duration_seconds: float,
        profile_id: str,
    ) -> None:
        """Synchronously upsert watch history."""
        # Defensive normalization: if media_id is an episode-specific identifier (e.g., sc-13083_s1e9)
        if media_id and "_s" in media_id:
            ep_match = re.search(r"^(.*)_s(\d+)e(\d+)$", media_id, re.IGNORECASE)
            if ep_match:
                media_id = ep_match.group(1)
                media_type = "tv"
                if season_number is None:
                    season_number = int(ep_match.group(2))
                if episode_number is None:
                    episode_number = int(ep_match.group(3))

        base_id = f"{media_id}_s{season_number}e{episode_number}" if season_number and episode_number else media_id
        hist_id = f"{profile_id}:{base_id}"
        effective_title = title
        effective_poster = poster_url
        with self._get_connection() as conn:
            if not effective_title or effective_title.strip() in ("", "Senza Titolo") or not effective_poster:
                # 1. Check existing watch_history record for this item
                h_row = conn.execute("SELECT title, poster_url FROM watch_history WHERE id = ?", (hist_id,)).fetchone()
                if h_row:
                    if (not effective_title or effective_title.strip() in ("", "Senza Titolo")) and h_row["title"] and h_row["title"] != "Senza Titolo":
                        effective_title = h_row["title"]
                    if not effective_poster and h_row["poster_url"]:
                        effective_poster = h_row["poster_url"]

                # 2. Check titles table
                if not effective_title or effective_title.strip() in ("", "Senza Titolo") or not effective_poster:
                    t_row = conn.execute("SELECT title, poster_url, raw_json FROM titles WHERE id = ?", (media_id,)).fetchone()
                    if t_row:
                        if (not effective_title or effective_title.strip() in ("", "Senza Titolo")) and t_row["title"] and t_row["title"] != "Senza Titolo":
                            effective_title = t_row["title"]
                        elif (not effective_title or effective_title.strip() in ("", "Senza Titolo")) and t_row["raw_json"]:
                            with contextlib.suppress(Exception):
                                raw_data = json.loads(t_row["raw_json"])
                                effective_title = raw_data.get("name") or raw_data.get("title")
                        if not effective_poster and t_row["poster_url"]:
                            effective_poster = t_row["poster_url"]

            if not effective_title or effective_title.strip() in ("", "Senza Titolo"):
                effective_title = slug_to_title(media_id) or "Senza Titolo"

            conn.execute(
                """
                INSERT INTO watch_history (
                    id, profile_id, media_id, title, poster_url, media_type,
                    season_number, episode_number, progress_seconds, duration_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    progress_seconds=excluded.progress_seconds,
                    duration_seconds=excluded.duration_seconds,
                    title=CASE
                        WHEN excluded.title IS NOT NULL AND excluded.title != '' AND excluded.title != 'Senza Titolo'
                        THEN excluded.title
                        ELSE watch_history.title
                    END,
                    poster_url=CASE
                        WHEN excluded.poster_url IS NOT NULL AND excluded.poster_url != ''
                        THEN excluded.poster_url
                        ELSE watch_history.poster_url
                    END,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (
                    hist_id,
                    profile_id,
                    media_id,
                    effective_title,
                    effective_poster,
                    media_type,
                    season_number,
                    episode_number,
                    progress_seconds,
                    duration_seconds,
                ),
            )

    async def get_watch_history(self, profile_id: str = "default", limit: int = 30) -> list[dict[str, Any]]:
        """Retrieve recent watch history for a profile."""
        async with self._lock:
            return await asyncio.to_thread(self._get_watch_history_sync, profile_id, limit)

    def _get_watch_history_sync(self, profile_id: str, limit: int) -> list[dict[str, Any]]:
        """Synchronously get watch history."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, media_id, title, poster_url, media_type,
                       season_number, episode_number, progress_seconds, duration_seconds, updated_at
                FROM watch_history
                WHERE profile_id = ?
                ORDER BY updated_at DESC
                LIMIT ?;
                """,
                (profile_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    async def get_continue_watching(self, profile_id: str = "default", limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve deduplicated in-progress movies and TV series for 'Continua a guardare'."""
        async with self._lock:
            return await asyncio.to_thread(self._get_continue_watching_sync, profile_id, limit)

    def _get_continue_watching_sync(self, profile_id: str, limit: int) -> list[dict[str, Any]]:
        """Synchronously get continue watching list for a profile."""
        with self._get_connection() as conn:
            query = """
                SELECT h.id, h.media_id, h.title, h.poster_url, h.media_type,
                       h.season_number, h.episode_number, h.progress_seconds,
                       h.duration_seconds, h.updated_at,
                       t.backdrop_url, t.poster_url as title_poster, t.title as title_canonical
                FROM watch_history h
                INNER JOIN (
                    SELECT media_id, MAX(rowid) as max_rowid
                    FROM watch_history
                    WHERE profile_id = ?
                    GROUP BY media_id
                ) latest ON h.rowid = latest.max_rowid
                LEFT JOIN titles t ON h.media_id = t.id
                WHERE h.profile_id = ?
                ORDER BY h.updated_at DESC, h.rowid DESC
                LIMIT ?;
            """
            cursor = conn.execute(query, (profile_id, profile_id, limit * 2))
            rows = [dict(r) for r in cursor.fetchall()]

            results: list[dict[str, Any]] = []
            for r in rows:
                media_type = r.get("media_type", "movie")
                duration = float(r.get("duration_seconds") or 0)
                progress = float(r.get("progress_seconds") or 0)
                percent = round((progress / duration * 100), 1) if duration > 0 else 0
                title_name = r.get("title_canonical")
                if not title_name or str(title_name).strip() in ("", "Senza Titolo"):
                    title_name = r.get("title")
                if not title_name or str(title_name).strip() in ("", "Senza Titolo"):
                    title_name = slug_to_title(r["media_id"]) or "Senza Titolo"
                poster = r.get("title_poster") or r.get("poster_url")
                backdrop = r.get("backdrop_url")

                if media_type == "movie":
                    if "_s" in r["media_id"] and any(c.isdigit() for c in r["media_id"]):
                        continue
                    if progress < 15:
                        continue
                    if percent >= 90 or (duration > 300 and (duration - progress) < 180):
                        continue

                    remaining = max(0, int(duration - progress)) if duration > 0 else 0
                    results.append(
                        {
                            "media_id": r["media_id"],
                            "title": title_name,
                            "media_type": "movie",
                            "poster_url": poster,
                            "backdrop_url": backdrop,
                            "progress_seconds": progress,
                            "duration_seconds": duration,
                            "progress_percent": percent,
                            "remaining_seconds": remaining,
                            "is_next_episode": False,
                            "updated_at": r["updated_at"],
                        }
                    )
                elif media_type == "tv":
                    curr_season = r.get("season_number") or 1
                    curr_ep = r.get("episode_number") or 1

                    is_completed = (
                        percent >= 90
                        or (duration > 120 and (duration - progress) < 90)
                        or (duration == 0 and progress > 1200)
                    )
                    if is_completed:
                        next_ep = self._find_next_episode_sync(conn, r["media_id"], curr_season, curr_ep)
                        if next_ep:
                            results.append(
                                {
                                    "media_id": r["media_id"],
                                    "title": title_name,
                                    "media_type": "tv",
                                    "poster_url": next_ep.get("poster_url") or poster,
                                    "backdrop_url": backdrop,
                                    "season_number": next_ep["season_number"],
                                    "episode_number": next_ep["episode_number"],
                                    "episode_title": next_ep.get("title") or f"Episodio {next_ep['episode_number']}",
                                    "progress_seconds": 0,
                                    "duration_seconds": 0,
                                    "progress_percent": 0,
                                    "remaining_seconds": 0,
                                    "is_next_episode": True,
                                    "updated_at": r["updated_at"],
                                }
                            )
                    else:
                        if progress < 15:
                            continue
                        remaining = max(0, int(duration - progress)) if duration > 0 else 0
                        ep_title = self._get_episode_title_sync(conn, r["media_id"], curr_season, curr_ep)
                        results.append(
                            {
                                "media_id": r["media_id"],
                                "title": title_name,
                                "media_type": "tv",
                                "poster_url": poster,
                                "backdrop_url": backdrop,
                                "season_number": curr_season,
                                "episode_number": curr_ep,
                                "episode_title": ep_title or f"Episodio {curr_ep}",
                                "progress_seconds": progress,
                                "duration_seconds": duration,
                                "progress_percent": percent,
                                "remaining_seconds": remaining,
                                "is_next_episode": False,
                                "updated_at": r["updated_at"],
                            }
                        )

                if len(results) >= limit:
                    break

            return results

    async def get_watched_history(self, profile_id: str = "default", limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve completed / watched titles (progress >= 90%) for 'Visti di Recente'."""
        async with self._lock:
            return await asyncio.to_thread(self._get_watched_history_sync, profile_id, limit)

    def _get_watched_history_sync(self, profile_id: str, limit: int) -> list[dict[str, Any]]:
        """Synchronously get watched list for a profile."""
        with self._get_connection() as conn:
            query = """
                SELECT h.id, h.media_id, h.title, h.poster_url, h.media_type,
                       h.season_number, h.episode_number, h.progress_seconds,
                       h.duration_seconds, h.updated_at,
                       t.backdrop_url, t.poster_url as title_poster, t.title as title_canonical
                FROM watch_history h
                INNER JOIN (
                    SELECT media_id, MAX(updated_at) as max_updated
                    FROM watch_history
                    WHERE profile_id = ?
                    GROUP BY media_id
                ) latest ON h.media_id = latest.media_id AND h.updated_at = latest.max_updated
                LEFT JOIN titles t ON h.media_id = t.id
                WHERE h.profile_id = ?
                ORDER BY h.updated_at DESC
                LIMIT ?;
            """
            cursor = conn.execute(query, (profile_id, profile_id, limit * 2))
            rows = [dict(r) for r in cursor.fetchall()]

            results: list[dict[str, Any]] = []
            for r in rows:
                duration = float(r.get("duration_seconds") or 0)
                progress = float(r.get("progress_seconds") or 0)
                percent = round((progress / duration * 100), 1) if duration > 0 else 0
                title_name = r.get("title_canonical")
                if not title_name or str(title_name).strip() in ("", "Senza Titolo"):
                    title_name = r.get("title")
                if not title_name or str(title_name).strip() in ("", "Senza Titolo"):
                    title_name = slug_to_title(r["media_id"]) or "Senza Titolo"
                poster = r.get("title_poster") or r.get("poster_url")
                backdrop = r.get("backdrop_url")

                # Count as watched if percent >= 85% or duration > 300 and less than 3 min remaining
                is_watched = percent >= 85 or (duration > 300 and (duration - progress) < 180)
                if not is_watched:
                    continue

                results.append(
                    {
                        "media_id": r["media_id"],
                        "title": title_name,
                        "media_type": r.get("media_type", "movie"),
                        "poster_url": poster,
                        "backdrop_url": backdrop,
                        "season_number": r.get("season_number"),
                        "episode_number": r.get("episode_number"),
                        "progress_percent": 100.0,
                        "updated_at": r["updated_at"],
                    }
                )
                if len(results) >= limit:
                    break
            return results

    def _find_next_episode_sync(
        self, conn: sqlite3.Connection, series_id: str, season_num: int, ep_num: int
    ) -> dict[str, Any] | None:
        """Find the next episode in the current season or the first episode of the next season."""
        s_cursor = conn.execute(
            "SELECT episodes_json FROM seasons WHERE series_id = ? AND season_number = ?", (series_id, season_num)
        )
        row = s_cursor.fetchone()
        if row and row["episodes_json"]:
            with contextlib.suppress(Exception):
                episodes = json.loads(row["episodes_json"])
                for ep in episodes:
                    if int(ep.get("episode_number", 0)) == ep_num + 1:
                        return {
                            "season_number": season_num,
                            "episode_number": ep_num + 1,
                            "title": ep.get("title"),
                            "poster_url": ep.get("poster_url"),
                        }

        next_s_cursor = conn.execute(
            "SELECT episodes_json, season_number FROM seasons WHERE series_id = ? AND season_number = ?",
            (series_id, season_num + 1),
        )
        next_row = next_s_cursor.fetchone()
        if next_row and next_row["episodes_json"]:
            with contextlib.suppress(Exception):
                episodes = json.loads(next_row["episodes_json"])
                if episodes:
                    first_ep = episodes[0]
                    return {
                        "season_number": season_num + 1,
                        "episode_number": int(first_ep.get("episode_number", 1)),
                        "title": first_ep.get("title"),
                        "poster_url": first_ep.get("poster_url"),
                    }
        return None

    def _get_episode_title_sync(
        self, conn: sqlite3.Connection, series_id: str, season_num: int, ep_num: int
    ) -> str | None:
        """Get cached episode title."""
        cursor = conn.execute(
            "SELECT episodes_json FROM seasons WHERE series_id = ? AND season_number = ?", (series_id, season_num)
        )
        row = cursor.fetchone()
        if row and row["episodes_json"]:
            with contextlib.suppress(Exception):
                episodes = json.loads(row["episodes_json"])
                for ep in episodes:
                    if int(ep.get("episode_number", 0)) == ep_num:
                        return ep.get("title")
        return None

    async def delete_watch_history(self, media_id: str, profile_id: str = "default") -> None:
        """Remove a title and all its episodes from watch history for a profile."""
        async with self._lock:
            await asyncio.to_thread(self._delete_watch_history_sync, media_id, profile_id)

    def _delete_watch_history_sync(self, media_id: str, profile_id: str) -> None:
        """Synchronously delete history by media_id and profile_id."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM watch_history WHERE media_id = ? AND profile_id = ?", (media_id, profile_id))

    async def get_media_progress(
        self,
        media_id: str,
        profile_id: str = "default",
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> dict[str, Any] | None:
        """Get latest watch progress for a media_id and profile, optionally filtered by season and episode."""
        async with self._lock:
            return await asyncio.to_thread(
                self._get_media_progress_sync, media_id, profile_id, season_number, episode_number
            )

    def _get_media_progress_sync(
        self,
        media_id: str,
        profile_id: str,
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> dict[str, Any] | None:
        """Synchronously get latest progress."""
        with self._get_connection() as conn:
            if season_number is not None and episode_number is not None:
                query = """
                    SELECT id, media_id, title, poster_url, media_type,
                           season_number, episode_number, progress_seconds, duration_seconds, updated_at
                    FROM watch_history
                    WHERE media_id = ? AND profile_id = ? AND season_number = ? AND episode_number = ?
                    ORDER BY updated_at DESC
                    LIMIT 1;
                """
                params = (media_id, profile_id, season_number, episode_number)
            else:
                query = """
                    SELECT id, media_id, title, poster_url, media_type,
                           season_number, episode_number, progress_seconds, duration_seconds, updated_at
                    FROM watch_history
                    WHERE media_id = ? AND profile_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1;
                """
                params = (media_id, profile_id)

            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            if season_number is None and episode_number is None and res.get("media_type") == "tv":
                curr_s = int(res.get("season_number") or 1)
                curr_e = int(res.get("episode_number") or 1)
                dur = float(res.get("duration_seconds") or 0)
                prog = float(res.get("progress_seconds") or 0)
                pct = (prog / dur * 100) if dur > 0 else 0
                is_done = pct >= 85 or (dur > 120 and (dur - prog) < 90) or (dur == 0 and prog > 1200)
                if is_done:
                    next_ep = self._find_next_episode_sync(conn, media_id, curr_s, curr_e)
                    if next_ep:
                        res["season_number"] = next_ep["season_number"]
                        res["episode_number"] = next_ep["episode_number"]
                        res["progress_seconds"] = 0
                        res["is_next_episode"] = True
                    else:
                        res["is_completed"] = True
            return res

    async def toggle_favorite(
        self,
        title_id: str,
        media_type: str,
        title: str,
        poster_url: str | None,
        profile_id: str = "default",
    ) -> bool:
        """Toggle favorite status for a profile. Returns True if now favorite, False if removed."""
        async with self._lock:
            return await asyncio.to_thread(
                self._toggle_favorite_sync, title_id, media_type, title, poster_url, profile_id
            )

    def _toggle_favorite_sync(
        self,
        title_id: str,
        media_type: str,
        title: str,
        poster_url: str | None,
        profile_id: str,
    ) -> bool:
        """Synchronously toggle favorite."""
        fav_id = f"{profile_id}:{title_id}"
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM favorites WHERE profile_id = ? AND title_id = ?", (profile_id, title_id)
            )
            if cursor.fetchone():
                conn.execute("DELETE FROM favorites WHERE profile_id = ? AND title_id = ?", (profile_id, title_id))
                return False

            effective_title = title
            effective_poster = poster_url
            if not effective_title or effective_title.strip() in ("", "Senza Titolo") or not effective_poster:
                t_row = conn.execute("SELECT title, poster_url, raw_json FROM titles WHERE id = ?", (title_id,)).fetchone()
                if t_row:
                    if (not effective_title or effective_title.strip() in ("", "Senza Titolo")) and t_row["title"] and t_row["title"] != "Senza Titolo":
                        effective_title = t_row["title"]
                    elif (not effective_title or effective_title.strip() in ("", "Senza Titolo")) and t_row["raw_json"]:
                        with contextlib.suppress(Exception):
                            raw_data = json.loads(t_row["raw_json"])
                            effective_title = raw_data.get("name") or raw_data.get("title")
                    if not effective_poster and t_row["poster_url"]:
                        effective_poster = t_row["poster_url"]
            if not effective_title or effective_title.strip() in ("", "Senza Titolo"):
                effective_title = slug_to_title(title_id) or "Senza Titolo"

            conn.execute(
                """
                INSERT INTO favorites (id, profile_id, title_id, media_type, title, poster_url, added_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING;
                """,
                (fav_id, profile_id, title_id, media_type, effective_title, effective_poster),
            )
            return True

    async def get_favorites(self, profile_id: str = "default") -> list[dict[str, Any]]:
        """Retrieve all user favorites for a profile."""
        async with self._lock:
            return await asyncio.to_thread(self._get_favorites_sync, profile_id)

    def _get_favorites_sync(self, profile_id: str) -> list[dict[str, Any]]:
        """Synchronously get all favorites for a profile."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT f.title_id, f.media_type, f.title, f.poster_url, f.added_at,
                       t.title as canonical_title, t.poster_url as canonical_poster,
                       t.backdrop_url, t.description, t.year, t.rating, t.duration, t.raw_json
                FROM favorites f
                LEFT JOIN titles t ON f.title_id = t.id
                WHERE f.profile_id = ?
                ORDER BY f.added_at DESC
                """,
                (profile_id,),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                r = dict(row)
                r["id"] = r["title_id"]
                r["type"] = r["media_type"]
                resolved_title = r.get("title")
                if not resolved_title or str(resolved_title).strip() in ("", "Senza Titolo"):
                    resolved_title = r.get("canonical_title")
                if (not resolved_title or str(resolved_title).strip() in ("", "Senza Titolo")) and r.get("raw_json"):
                    with contextlib.suppress(Exception):
                        raw_data = json.loads(r["raw_json"])
                        resolved_title = raw_data.get("name") or raw_data.get("title")
                if not resolved_title or str(resolved_title).strip() in ("", "Senza Titolo"):
                    resolved_title = slug_to_title(r["title_id"]) or "Senza Titolo"
                r["title"] = resolved_title

                if not r.get("poster_url") and r.get("canonical_poster"):
                    r["poster_url"] = r.get("canonical_poster")

                results.append(r)
            return results

    async def is_favorite(self, title_id: str, profile_id: str = "default") -> bool:
        """Check if a title is favorited by profile."""
        async with self._lock:
            return await asyncio.to_thread(self._is_favorite_sync, title_id, profile_id)

    def _is_favorite_sync(self, title_id: str, profile_id: str) -> bool:
        """Synchronously check favorite status."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM favorites WHERE profile_id = ? AND title_id = ? LIMIT 1", (profile_id, title_id)
            )
            return cursor.fetchone() is not None

    async def get_candidates_for_background_sync(self, limit: int = 15) -> list[dict[str, Any]]:
        """Retrieve active series and movies eligible for periodic background revalidation."""
        async with self._lock:
            return await asyncio.to_thread(self._get_candidates_for_background_sync_sync, limit)

    def _get_candidates_for_background_sync_sync(self, limit: int = 15) -> list[dict[str, Any]]:
        """Synchronously retrieve active series and movies eligible for background refresh."""
        with self._get_connection() as conn:
            # 1. TV Series candidates from watch history (last 14 days) and favorites:
            query_tv = """
                WITH active_series AS (
                    SELECT media_id, MAX(season_number) as max_s, MAX(updated_at) as last_act
                    FROM watch_history
                    WHERE media_type = 'tv' AND updated_at >= datetime('now', '-14 days')
                    GROUP BY media_id
                    UNION
                    SELECT title_id as media_id, 1 as max_s, added_at as last_act
                    FROM favorites
                    WHERE media_type = 'tv'
                ),
                consolidated_series AS (
                    SELECT media_id, MAX(COALESCE(max_s, 1)) as target_season, MAX(last_act) as latest_activity
                    FROM active_series
                    GROUP BY media_id
                )
                SELECT c.media_id, 'tv' as media_type, c.target_season,
                       (strftime('%s', 'now') - strftime('%s', s.updated_at)) as age_seconds
                FROM consolidated_series c
                LEFT JOIN seasons s ON s.series_id = c.media_id AND s.season_number = c.target_season
                WHERE s.updated_at IS NULL OR (strftime('%s', 'now') - strftime('%s', s.updated_at)) > 43200
                ORDER BY c.latest_activity DESC
                LIMIT ?;
            """
            cursor_tv = conn.execute(query_tv, (limit,))
            tv_candidates = [
                {
                    "media_id": row["media_id"],
                    "media_type": "tv",
                    "season_number": int(row["target_season"] or 1),
                    "age_seconds": int(row["age_seconds"]) if row["age_seconds"] is not None else None,
                }
                for row in cursor_tv.fetchall()
            ]

            # 2. Movie candidates from active watch history (last 14 days) and favorites:
            remaining_limit = max(0, limit - len(tv_candidates))
            movie_candidates: list[dict[str, Any]] = []
            if remaining_limit > 0:
                query_movie = """
                    WITH active_movies AS (
                        SELECT media_id, MAX(updated_at) as last_act
                        FROM watch_history
                        WHERE media_type = 'movie' AND updated_at >= datetime('now', '-14 days')
                        GROUP BY media_id
                        UNION
                        SELECT title_id as media_id, added_at as last_act
                        FROM favorites
                        WHERE media_type = 'movie'
                    ),
                    consolidated_movies AS (
                        SELECT media_id, MAX(last_act) as latest_activity
                        FROM active_movies
                        GROUP BY media_id
                    )
                    SELECT m.media_id, 'movie' as media_type,
                           (strftime('%s', 'now') - strftime('%s', t.updated_at)) as age_seconds
                    FROM consolidated_movies m
                    LEFT JOIN titles t ON t.id = m.media_id
                    WHERE t.updated_at IS NULL OR (strftime('%s', 'now') - strftime('%s', t.updated_at)) > 43200
                    ORDER BY m.latest_activity DESC
                    LIMIT ?;
                """
                cursor_movie = conn.execute(query_movie, (remaining_limit,))
                movie_candidates = [
                    {
                        "media_id": row["media_id"],
                        "media_type": "movie",
                        "season_number": None,
                        "age_seconds": int(row["age_seconds"]) if row["age_seconds"] is not None else None,
                    }
                    for row in cursor_movie.fetchall()
                ]

            return tv_candidates + movie_candidates

    async def save_tmdb_session(
        self,
        profile_id: str,
        session_id: str,
        account_id: int | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        """Persist TMDb session for a user profile."""
        async with self._lock:
            await asyncio.to_thread(
                self._save_tmdb_session_sync,
                profile_id,
                session_id,
                account_id,
                username,
                avatar_url,
            )

    def _save_tmdb_session_sync(
        self,
        profile_id: str,
        session_id: str,
        account_id: int | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tmdb_sessions (profile_id, session_id, account_id, username, avatar_url, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(profile_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    account_id=excluded.account_id,
                    username=excluded.username,
                    avatar_url=excluded.avatar_url,
                    updated_at=CURRENT_TIMESTAMP;
                """,
                (profile_id, session_id, account_id, username, avatar_url),
            )

    async def get_tmdb_session(self, profile_id: str = "default") -> dict[str, Any] | None:
        """Get TMDb session record for a user profile."""
        async with self._lock:
            return await asyncio.to_thread(self._get_tmdb_session_sync, profile_id)

    def _get_tmdb_session_sync(self, profile_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT profile_id, session_id, account_id, username, avatar_url, updated_at FROM tmdb_sessions WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            if row:
                return dict(row)
            return None

    async def delete_tmdb_session(self, profile_id: str = "default") -> bool:
        """Delete TMDb session for a user profile."""
        async with self._lock:
            return await asyncio.to_thread(self._delete_tmdb_session_sync, profile_id)

    def _delete_tmdb_session_sync(self, profile_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM tmdb_sessions WHERE profile_id = ?", (profile_id,))
            return cursor.rowcount > 0

    async def add_favorite(
        self,
        title_id: str,
        media_type: str,
        title: str,
        poster_url: str | None = None,
        profile_id: str = "default",
    ) -> bool:
        """Add a title to favorites if not already present."""
        async with self._lock:
            return await asyncio.to_thread(
                self._add_favorite_sync,
                title_id,
                media_type,
                title,
                poster_url,
                profile_id,
            )

    def _add_favorite_sync(
        self,
        title_id: str,
        media_type: str,
        title: str,
        poster_url: str | None = None,
        profile_id: str = "default",
    ) -> bool:
        fav_id = f"fav_{profile_id}_{title_id}"
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM favorites WHERE profile_id = ? AND title_id = ? LIMIT 1",
                (profile_id, title_id),
            )
            if cursor.fetchone():
                return False
            conn.execute(
                """
                INSERT INTO favorites (id, profile_id, title_id, media_type, title, poster_url, added_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING;
                """,
                (fav_id, profile_id, title_id, media_type, title, poster_url),
            )
            return True

    async def get_titles_for_enrichment(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve titles that need metadata enrichment or have stale metadata."""
        async with self._lock:
            return await asyncio.to_thread(self._get_titles_for_enrichment_sync, limit)

    def _get_titles_for_enrichment_sync(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, media_type, title, year, poster_url, backdrop_url, tmdb_id, imdb_id, updated_at
                FROM titles
                WHERE tmdb_id IS NULL
                   OR backdrop_url IS NULL
                   OR certification IS NULL
                   OR updated_at <= datetime('now', '-14 days')
                ORDER BY
                    CASE WHEN tmdb_id IS NULL THEN 0 ELSE 1 END,
                    updated_at ASC
                LIMIT ?;
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]

    async def find_title_by_tmdb_or_query(
        self,
        title: str,
        media_type: str | None = None,
        tmdb_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Find an existing title in the database matching a tmdb_id or title query."""
        async with self._lock:
            return await asyncio.to_thread(self._find_title_by_tmdb_or_query_sync, title, media_type, tmdb_id)

    def _find_title_by_tmdb_or_query_sync(
        self,
        title: str,
        media_type: str | None = None,
        tmdb_id: int | None = None,
    ) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            if tmdb_id:
                row = conn.execute("SELECT * FROM titles WHERE tmdb_id = ? LIMIT 1", (tmdb_id,)).fetchone()
                if row:
                    return dict(row)
            if title:
                q = "SELECT * FROM titles WHERE LOWER(title) = LOWER(?)"
                params: list[Any] = [title.strip()]
                if media_type:
                    q += " AND media_type = ?"
                    params.append(media_type)
                q += " LIMIT 1"
                row = conn.execute(q, params).fetchone()
                if row:
                    return dict(row)
            return None
