"""Utility functions for genres and catalog deduplication."""

from __future__ import annotations

from datetime import UTC, datetime
import html
import logging
import re
import unicodedata

from .models import Movie, ProviderSource, TvSeries

_LOGGER = logging.getLogger(__name__)

GENRE_SYNONYMS: dict[str, set[str]] = {
    "azione": {"azione", "action"},
    "action": {"azione", "action"},
    "avventura": {"avventura", "adventure"},
    "adventure": {"avventura", "adventure"},
    "animazione": {"animazione", "animation"},
    "animation": {"animazione", "animation"},
    "biografico": {"biografico", "biografia", "biography"},
    "biografia": {"biografico", "biografia", "biography"},
    "comico": {"comico", "commedia", "comedy"},
    "commedia": {"commedia", "comico", "comedy"},
    "comedy": {"commedia", "comico", "comedy"},
    "crime": {"crime", "poliziesco"},
    "poliziesco": {"poliziesco", "crime"},
    "documentario": {"documentario", "documentary"},
    "documentary": {"documentario", "documentary"},
    "dramma": {"dramma", "drammatico", "drama"},
    "drammatico": {"drammatico", "dramma", "drama"},
    "drama": {"drammatico", "dramma", "drama"},
    "famiglia": {"famiglia", "family"},
    "family": {"famiglia", "family"},
    "fantasy": {"fantasy", "fantastico"},
    "fantastico": {"fantastico", "fantasy"},
    "fantascienza": {"fantascienza", "sci-fi", "science fiction"},
    "sci-fi": {"fantascienza", "sci-fi", "science fiction"},
    "giallo": {"giallo", "mystery", "mistero"},
    "mistero": {"mistero", "mystery", "giallo"},
    "mystery": {"mistero", "mystery", "giallo"},
    "guerra": {"guerra", "war", "bellico"},
    "war": {"guerra", "war", "bellico"},
    "horror": {"horror"},
    "musica": {"musicale", "musical", "musica", "music"},
    "musicale": {"musicale", "musical", "musica", "music"},
    "musical": {"musicale", "musical", "musica", "music"},
    "music": {"musicale", "musical", "musica", "music"},
    "romance": {"sentimentale", "romance", "romantico"},
    "sentimentale": {"sentimentale", "romance", "romantico"},
    "romantico": {"sentimentale", "romance", "romantico"},
    "storia": {"storico", "storia", "history"},
    "storico": {"storico", "storia", "history"},
    "history": {"storico", "storia", "history"},
    "thriller": {"thriller"},
    "western": {"western"},
}


def genre_matches(target_genre: str, item_genres: list[str]) -> bool:
    """Return True if any element in item_genres matches target_genre or its known synonyms."""
    target = target_genre.strip().lower()
    allowed = GENRE_SYNONYMS.get(target, {target})
    for g in item_genres:
        g_clean = g.strip().lower()
        if g_clean in allowed:
            return True
        for syn in allowed:
            if re.search(rf"\b{re.escape(syn)}\b", g_clean):
                return True
    return False


class CatalogMerger:
    """Handles cross-catalog matching, metadata enrichment, and source unification."""

    @staticmethod
    def normalize_title(title: str | None) -> str:
        """Normalize movie or series title for comparison."""
        if not title:
            return ""

        text = html.unescape(title)
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.lower()

        text = re.sub(r"\[.*?\]", " ", text)
        text = re.sub(r"\(.*?\)", " ", text)
        text = re.sub(
            r"\b(streaming|film\s+gratis|serie\s+tv|hd|sd|4k|fhd|ita|subita|sub-ita|completa)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"[^\w\s]", " ", text)

        num_map = {
            "uno": "1",
            "due": "2",
            "tre": "3",
            "quattro": "4",
            "cinque": "5",
            "sei": "6",
            "sette": "7",
            "otto": "8",
            "nove": "9",
            "dieci": "10",
            "i": "1",
            "ii": "2",
            "iii": "3",
            "iv": "4",
            "v": "5",
            "vi": "6",
        }
        words = [num_map.get(w, w) for w in text.split()]
        return " ".join(words)

    @classmethod
    def titles_match(cls, title1: str, year1: int | None, title2: str, year2: int | None) -> bool:
        """Check if two titles and their release years match."""
        n1 = cls.normalize_title(title1)
        n2 = cls.normalize_title(title2)

        if not n1 or not n2:
            return False

        if n1 == n2:
            if year1 and year2:
                return abs(year1 - year2) <= 1
            return True

        words1 = set(n1.split())
        words2 = set(n2.split())
        if len(words1) >= 2 and len(words2) >= 2:
            if words1.issubset(words2) or words2.issubset(words1):
                if year1 and year2:
                    return abs(year1 - year2) <= 1

        return False

    @classmethod
    def is_same_media(cls, m1: Movie | TvSeries, m2: Movie | TvSeries) -> bool:
        """Determine if two Movie or TvSeries objects represent the same piece of media."""
        if m1.tmdb_id and m2.tmdb_id:
            return str(m1.tmdb_id) == str(m2.tmdb_id)

        if m1.imdb_id and m2.imdb_id:
            return m1.imdb_id.strip().lower() == m2.imdb_id.strip().lower()

        if cls.titles_match(m1.title, m1.year, m2.title, m2.year):
            return True

        if getattr(m1, "original_title", None) and getattr(m2, "original_title", None):
            if cls.titles_match(m1.original_title or "", m1.year, m2.original_title or "", m2.year):
                return True

        return False

    @classmethod
    def merge_sources(
        cls,
        existing_sources: list[ProviderSource],
        new_sources: list[ProviderSource],
        media_id: str,
    ) -> list[ProviderSource]:
        """Combine sources avoiding duplicate page URLs or provider collisions."""
        seen_urls = {s.page_url for s in existing_sources if s.page_url}
        result = list(existing_sources)

        for src in new_sources:
            if src.page_url not in seen_urls:
                seen_urls.add(src.page_url)
                cloned = ProviderSource(
                    id=src.id,
                    media_id=media_id,
                    provider_id=src.provider_id,
                    provider_name=src.provider_name,
                    page_url=src.page_url,
                    language=src.language,
                    quality=src.quality,
                    available=src.available,
                )
                result.append(cloned)

        return result

    @classmethod
    def merge_movie(cls, existing: Movie, incoming: Movie) -> Movie:
        """Merge an incoming Movie record into an existing Movie record."""
        if (not existing.title or existing.title.strip() in ("", "Senza Titolo")) and incoming.title and incoming.title.strip() not in ("", "Senza Titolo"):
            existing.title = incoming.title

        all_catalogs = list(dict.fromkeys(existing.catalogs + incoming.catalogs))
        existing.catalogs = all_catalogs

        if not existing.source_a_url and incoming.source_a_url:
            existing.source_a_url = incoming.source_a_url
        if not existing.source_b_url and incoming.source_b_url:
            existing.source_b_url = incoming.source_b_url

        if not existing.tmdb_id and incoming.tmdb_id:
            existing.tmdb_id = incoming.tmdb_id
        if not existing.imdb_id and incoming.imdb_id:
            existing.imdb_id = incoming.imdb_id

        if not existing.poster_url and incoming.poster_url:
            existing.poster_url = incoming.poster_url
        if not existing.backdrop_url and incoming.backdrop_url:
            existing.backdrop_url = incoming.backdrop_url
        if not existing.description and incoming.description:
            existing.description = incoming.description

        if not existing.year and incoming.year:
            existing.year = incoming.year
        if not existing.duration and incoming.duration:
            existing.duration = incoming.duration
        if not existing.rating and incoming.rating:
            existing.rating = incoming.rating

        if incoming.genres:
            existing.genres = list(dict.fromkeys(existing.genres + incoming.genres))

        existing.sources = cls.merge_sources(existing.sources, incoming.sources, existing.id)
        existing.updated_at = datetime.now(UTC)
        return existing

    @classmethod
    def merge_tv_series(cls, existing: TvSeries, incoming: TvSeries) -> TvSeries:
        """Merge an incoming TvSeries record into an existing TvSeries record."""
        if (not existing.title or existing.title.strip() in ("", "Senza Titolo")) and incoming.title and incoming.title.strip() not in ("", "Senza Titolo"):
            existing.title = incoming.title

        all_catalogs = list(dict.fromkeys(existing.catalogs + incoming.catalogs))
        existing.catalogs = all_catalogs

        if not existing.source_a_url and incoming.source_a_url:
            existing.source_a_url = incoming.source_a_url
        if not existing.source_b_url and incoming.source_b_url:
            existing.source_b_url = incoming.source_b_url

        if not existing.tmdb_id and incoming.tmdb_id:
            existing.tmdb_id = incoming.tmdb_id
        if not existing.imdb_id and incoming.imdb_id:
            existing.imdb_id = incoming.imdb_id

        if not existing.poster_url and incoming.poster_url:
            existing.poster_url = incoming.poster_url
        if not existing.backdrop_url and incoming.backdrop_url:
            existing.backdrop_url = incoming.backdrop_url
        if not existing.description and incoming.description:
            existing.description = incoming.description

        if not existing.year and incoming.year:
            existing.year = incoming.year
        if not existing.rating and incoming.rating:
            existing.rating = incoming.rating

        if incoming.genres:
            existing.genres = list(dict.fromkeys(existing.genres + incoming.genres))

        existing_seasons_map = {s.number: s for s in existing.seasons}
        for in_season in incoming.seasons:
            if in_season.number in existing_seasons_map:
                ex_season = existing_seasons_map[in_season.number]
                ex_episodes_map = {e.episode_number: e for e in ex_season.episodes}
                for in_ep in in_season.episodes:
                    if in_ep.episode_number in ex_episodes_map:
                        ex_ep = ex_episodes_map[in_ep.episode_number]
                        ex_ep.sources = cls.merge_sources(ex_ep.sources, in_ep.sources, existing.id)
                        if not ex_ep.title and in_ep.title:
                            ex_ep.title = in_ep.title
                    else:
                        in_ep.media_id = existing.id
                        ex_season.episodes.append(in_ep)
                ex_season.episodes.sort(key=lambda e: e.episode_number)
            else:
                for ep in in_season.episodes:
                    ep.media_id = existing.id
                existing.seasons.append(in_season)

        existing.seasons.sort(key=lambda s: s.number)
        existing.updated_at = datetime.now(UTC)
        return existing

    @classmethod
    def merge_movie_lists(cls, list_a: list[Movie], list_b: list[Movie]) -> list[Movie]:
        """Deduplicate and merge two lists of movies."""
        merged: list[Movie] = list(list_a)
        for incoming in list_b:
            match = next((m for m in merged if cls.is_same_media(m, incoming)), None)
            if match:
                cls.merge_movie(match, incoming)
            else:
                merged.append(incoming)
        return merged

    @classmethod
    def merge_tv_lists(cls, list_a: list[TvSeries], list_b: list[TvSeries]) -> list[TvSeries]:
        """Deduplicate and merge two lists of TV series."""
        merged: list[TvSeries] = list(list_a)
        for incoming in list_b:
            match = next((s for s in merged if cls.is_same_media(s, incoming)), None)
            if match:
                cls.merge_tv_series(match, incoming)
            else:
                merged.append(incoming)
        return merged
