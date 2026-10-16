"""HTML and metadata parser for semantic web catalog and media pages."""

from __future__ import annotations

import contextlib
from datetime import datetime
import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import urlparse

from .models import Movie, ProviderSource, TvEpisode, TvSeason, TvSeries


class CrawlerCatalogParser:
    """Parser for HTML web catalog documents and embed sources."""

    # Private compiled regex patterns for clean_title
    _CLEAN_FILM_GRATIS = re.compile(r"\s*-\s*FILM GRATIS.*$", re.IGNORECASE)
    _CLEAN_STREAMING = re.compile(r"\s*Streaming.*$", re.IGNORECASE)
    _VM_PATTERN = re.compile(
        r"\[?(VM\s*\d{1,2}|PEGI\s*\d{1,2}|1[0-8]\+|6\+)\]?",
        re.IGNORECASE,
    )
    _VIETATO_PATTERN = re.compile(r"vietato ai minori", re.IGNORECASE)
    _YEAR_PATTERN = re.compile(r"\((\d{4})\)")
    _YEAR_SUB_PATTERN = re.compile(r"\(\d{4}\)")
    _HD_PATTERN = re.compile(r"\[HD\]", re.IGNORECASE)
    _SUB_ITA_PATTERN = re.compile(r"\[Sub-ITA\]", re.IGNORECASE)
    _PUNCTUATION_PATTERN = re.compile(r"[–—−-]\s*$")
    _EXTRA_SPACES_PATTERN = re.compile(r"\s+")

    # Private compiled regex patterns for parse_metadata_line
    _META_SPLIT_PATTERN = re.compile(r"[–—−-]")
    _DURATA_PATTERN = re.compile(r"DURATA\s+(\d+)", re.IGNORECASE)

    # Private compiled regex patterns for is_tv_item
    _TV_URL_PATTERN = re.compile(r"/(?:serie-?tv|serietv)/", re.IGNORECASE)
    _TV_TITLE_PATTERN = re.compile(
        r"\b(?:\d+x\d+|s\d+e\d+|stagion[ei]|episodi[oe]?)\b",
        re.IGNORECASE,
    )

    # Private compiled regex patterns for parse_catalog_page
    _CARD_PATTERN_1 = re.compile(
        r'<div class="card mp-post horizontal">(.*?)</div>\s*</div>\s*</div>',
        re.DOTALL,
    )
    _CARD_PATTERN_2 = re.compile(
        r'<div class="[^"]*mp-post[^"]*">(.*?)</div>\s*</div>',
        re.DOTALL,
    )
    _CARD_TITLE_PATTERN = re.compile(
        r'<h3 class="card-title"><a href="([^"]+)">\s*(.*?)\s*</a></h3>',
        re.DOTALL,
    )
    _CARD_IMG_PATTERN = re.compile(
        r'<div class="card-image">.*?<img [^>]*src="([^"]+)"',
        re.DOTALL,
    )
    _CARD_META_PATTERN = re.compile(r"<strong[^>]*>\s*(.*?)\s*</strong>")
    _CARD_DESC_PATTERN = re.compile(
        r"<strong[^>]*>.*?</strong>(?:</span>)?\s*<br />\s*(.*?)(?:<a |</div>)",
        re.DOTALL,
    )
    _HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

    # Private compiled regex patterns for parse_movie_page and parse_tv_series_page
    _JSON_LD_PATTERN = re.compile(
        r'<script type="application/ld\+json" class="yoast-schema-graph">(.*?)</script>',
        re.DOTALL,
    )
    _YEAR_SEC_PATTERN = re.compile(r"^\(?\d{4}\)?$")
    _PAREN_STRIP_PATTERN = re.compile(r"[\(\)]")
    _PAGE_TITLE_PATTERN = re.compile(r"<title>(.*?)</title>")
    _OG_IMAGE_PATTERN = re.compile(r'<meta property="og:image" content="([^"]+)"')
    _MOVIE_META_PATTERN = re.compile(
        r'<div class="ignore-css">.*?<strong[^>]*>(.*?)</strong>',
        re.DOTALL,
    )
    _MOVIE_DESC_PATTERN = re.compile(
        r'<div class="ignore-css">.*?<p>(?:<strong[^>]*>.*?</strong></p>\s*<p>)?(.*?)(?:<br\s*/?>\s*<a |</p>)',
        re.DOTALL,
    )

    # Private compiled regex patterns for parse_sources
    _TABLE_PATTERN = re.compile(
        r'<table class="cbtable"[^>]*>(.*?)</table>\s*td>',
        re.DOTALL,
    )
    _TABLE_SECTION_SPLIT = re.compile(r"<u><strong>(Streaming.*?|Download.*?):?</strong></u>")
    _A_HREF_PATTERN = re.compile(r'<a href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>')

    # Private compiled regex patterns for parse_tv_series_page episodes
    _TV_TAGS_PATTERN = re.compile(
        r"<p[^>]*>(.*?)</p>|<li[^>]*>(.*?)</li>",
        re.IGNORECASE | re.DOTALL,
    )
    _SEASON_EP_MATCH_PATTERN = re.compile(r"\b(\d{1,2})\s*[xX×]\s*(\d{1,3})\b")
    _EPISODE_LINK_PATTERN = re.compile(
        r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE,
    )
    _HOSTING_URL_PATTERN = re.compile(r"stayonline\.pro|uprot\.net")

    @staticmethod
    def extract_media_id_from_url(url: str) -> str:
        """Extract media slug ID from a catalog URL."""
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        return parts[-1] if parts else hashlib.md5(url.encode()).hexdigest()[:12]

    @classmethod
    def clean_title(cls, raw_title: str) -> tuple[str, int | None, str | None, str | None]:
        """Clean raw title string, extracting clean title, year, quality flag, and age certification."""
        cleaned = html.unescape(raw_title)
        # Remove common marketing suffixes
        cleaned = cls._CLEAN_FILM_GRATIS.sub("", cleaned)
        cleaned = cls._CLEAN_STREAMING.sub("", cleaned)

        # Extract certification / age rating
        certification: str | None = None
        vm_match = cls._VM_PATTERN.search(cleaned)
        if vm_match:
            certification = vm_match.group(1).upper().replace(" ", "")
            cleaned = cls._VM_PATTERN.sub("", cleaned)
        elif cls._VIETATO_PATTERN.search(cleaned):
            certification = "VM18"
            cleaned = cls._VIETATO_PATTERN.sub("", cleaned)

        # Extract year
        year: int | None = None
        year_match = cls._YEAR_PATTERN.search(cleaned)
        if year_match:
            with contextlib.suppress(ValueError):
                year = int(year_match.group(1))
            cleaned = cls._YEAR_SUB_PATTERN.sub("", cleaned)

        # Extract quality
        quality: str | None = None
        if cls._HD_PATTERN.search(cleaned):
            quality = "HD"
            cleaned = cls._HD_PATTERN.sub("", cleaned)
        elif cls._SUB_ITA_PATTERN.search(cleaned):
            quality = "Sub-ITA"
            cleaned = cls._SUB_ITA_PATTERN.sub("", cleaned)

        # Clean punctuation and extra spaces
        cleaned = cls._PUNCTUATION_PATTERN.sub("", cleaned).strip()
        cleaned = cls._EXTRA_SPACES_PATTERN.sub(" ", cleaned).strip()

        return cleaned, year, quality, certification

    @classmethod
    def parse_metadata_line(cls, raw_meta: str) -> tuple[list[str], int | None, str | None, str | None]:
        """Parse genre, duration, country, and certification from metadata header line."""
        unescaped = html.unescape(raw_meta).replace("</span>", "").strip()
        parts = [p.strip() for p in cls._META_SPLIT_PATTERN.split(unescaped) if p.strip()]

        genres: list[str] = []
        duration: int | None = None
        country: str | None = None
        certification: str | None = None

        for part in parts:
            dur_match = cls._DURATA_PATTERN.search(part)
            if dur_match:
                with contextlib.suppress(ValueError):
                    duration = int(dur_match.group(1))
                continue

            vm_match = cls._VM_PATTERN.search(part)
            if vm_match:
                certification = vm_match.group(1).upper().replace(" ", "")
                continue
            if "VIETATO AI MINORI" in part.upper():
                certification = "VM18"
                continue

            if part.upper() in (
                "ITALIA",
                "USA",
                "FRANCIA",
                "REGNO UNITO",
                "SPAGNA",
                "GERMANIA",
                "CANADA",
                "GIAPPONE",
                "CINA",
            ):
                country = part.title()
            else:
                genres.append(part.title())

        return genres, duration, country, certification

    @classmethod
    def is_tv_item(cls, title: str, url: str = "", genres: list[str] | None = None) -> bool:
        """Check if an item is a TV series rather than a movie."""
        if url and cls._TV_URL_PATTERN.search(url):
            return True
        if genres and any(g.lower() in ("serie tv", "serietv") for g in genres):
            return True
        return bool(cls._TV_TITLE_PATTERN.search(title))

    @classmethod
    def parse_catalog_page(cls, html_text: str) -> list[Movie]:
        """Parse movie cards from a catalog, category, or search results page."""
        movies: list[Movie] = []

        card_matches = cls._CARD_PATTERN_1.findall(html_text)

        if not card_matches:
            card_matches = cls._CARD_PATTERN_2.findall(html_text)

        for card_html in card_matches:
            title_match = cls._CARD_TITLE_PATTERN.search(card_html)
            if not title_match:
                continue

            movie_url = title_match.group(1).strip()
            raw_title = title_match.group(2).strip()

            if "cambia-i-dns" in movie_url or "avviso" in movie_url.lower():
                continue

            media_id = cls.extract_media_id_from_url(movie_url)
            clean_title, year, _, title_cert = cls.clean_title(raw_title)

            img_match = cls._CARD_IMG_PATTERN.search(card_html)
            poster_url = img_match.group(1).strip() if img_match else None

            meta_match = cls._CARD_META_PATTERN.search(card_html)
            genres: list[str] = []
            duration: int | None = None
            meta_cert: str | None = None
            if meta_match:
                genres, duration, _, meta_cert = cls.parse_metadata_line(meta_match.group(1))

            cert = title_cert or meta_cert

            desc_match = cls._CARD_DESC_PATTERN.search(card_html)
            description = None
            if desc_match:
                clean_desc = cls._HTML_TAG_PATTERN.sub("", desc_match.group(1)).strip()
                description = html.unescape(clean_desc)

            movies.append(
                Movie(
                    id=media_id,
                    title=clean_title,
                    year=year,
                    poster_url=poster_url,
                    description=description,
                    genres=genres,
                    duration=duration,
                    certification=cert,
                    source_b_url=movie_url,
                    catalogs=["crawler"],
                    sources=[],
                )
            )

        return movies

    @classmethod
    def parse_movie_page(cls, html_text: str, movie_url: str = "") -> Movie:
        """Parse complete details and sources from a movie page."""
        media_id = cls.extract_media_id_from_url(movie_url) if movie_url else ""

        json_ld_data: dict[str, Any] = {}
        json_ld_match = cls._JSON_LD_PATTERN.search(html_text)
        if json_ld_match:
            with contextlib.suppress(Exception):
                json_ld_data = json.loads(json_ld_match.group(1))

        raw_title = ""
        poster_url: str | None = None
        added_at: datetime | None = None
        updated_at: datetime | None = None
        genres: list[str] = []

        if json_ld_data and "@graph" in json_ld_data:
            for item in json_ld_data["@graph"]:
                if item.get("@type") in ("Article", "WebPage"):
                    raw_title = item.get("headline") or item.get("name") or raw_title
                    if item.get("datePublished"):
                        with contextlib.suppress(Exception):
                            added_at = datetime.fromisoformat(item["datePublished"])
                    if item.get("dateModified"):
                        with contextlib.suppress(Exception):
                            updated_at = datetime.fromisoformat(item["dateModified"])
                    if item.get("thumbnailUrl"):
                        poster_url = item["thumbnailUrl"]
                    if item.get("articleSection") and isinstance(item["articleSection"], list):
                        for sec in item["articleSection"]:
                            if not cls._YEAR_SEC_PATTERN.match(sec) and sec not in (
                                "Film",
                                "HD",
                                "Vetrina-news",
                            ):
                                clean_sec = cls._PAREN_STRIP_PATTERN.sub("", sec).strip()
                                if clean_sec and clean_sec not in genres:
                                    genres.append(clean_sec)

        if not raw_title:
            title_tag = cls._PAGE_TITLE_PATTERN.search(html_text)
            if title_tag:
                raw_title = title_tag.group(1)

        clean_title, year, _, title_cert = cls.clean_title(raw_title)

        if not poster_url:
            og_img = cls._OG_IMAGE_PATTERN.search(html_text)
            if og_img:
                poster_url = og_img.group(1)

        duration: int | None = None
        meta_cert: str | None = None
        meta_match = cls._MOVIE_META_PATTERN.search(html_text)
        if meta_match:
            body_genres, parsed_dur, _, meta_cert = cls.parse_metadata_line(meta_match.group(1))
            if parsed_dur:
                duration = parsed_dur
            for g in body_genres:
                if g not in genres:
                    genres.append(g)

        cert = title_cert or meta_cert

        desc_match = cls._MOVIE_DESC_PATTERN.search(html_text)
        description: str | None = None
        if desc_match:
            clean_desc = cls._HTML_TAG_PATTERN.sub("", desc_match.group(1)).strip()
            description = html.unescape(clean_desc)

        sources = cls.parse_sources(html_text, media_id)

        return Movie(
            id=media_id,
            title=clean_title,
            year=year,
            poster_url=poster_url,
            description=description,
            genres=genres,
            duration=duration,
            certification=cert,
            source_b_url=movie_url,
            catalogs=["crawler"],
            sources=sources,
            added_at=added_at,
            updated_at=updated_at,
        )

    @classmethod
    def parse_sources(cls, html_text: str, media_id: str) -> list[ProviderSource]:
        """Extract streaming sources from the catalog table."""
        sources: list[ProviderSource] = []

        table_match = cls._TABLE_PATTERN.search(html_text)
        if not table_match:
            return sources

        table_content = table_match.group(1)
        sections = cls._TABLE_SECTION_SPLIT.split(table_content)

        for i in range(1, len(sections), 2):
            sec_name = sections[i].strip()
            sec_body = sections[i + 1]

            if not sec_name.lower().startswith("streaming"):
                continue

            quality = "HD" if "HD" in sec_name else "SD"

            link_matches = cls._A_HREF_PATTERN.findall(sec_body)
            for page_url, provider_raw in link_matches:
                provider_name = provider_raw.strip()
                provider_id = provider_name.lower().replace(" ", "_")

                url_hash = hashlib.md5(page_url.encode()).hexdigest()[:8]
                source_id = f"{media_id}_{provider_id}_{quality.lower()}_{url_hash}"

                sources.append(
                    ProviderSource(
                        id=source_id,
                        media_id=media_id,
                        provider_id=provider_id,
                        provider_name=provider_name,
                        page_url=page_url.strip(),
                        quality=quality,
                        language="ita",
                        available=True,
                    )
                )

        return sources

    @classmethod
    def parse_tv_series_page(cls, html_text: str, series_url: str = "") -> TvSeries:
        """Parse complete details and episodes from a TV series page."""
        series_id = cls.extract_media_id_from_url(series_url) if series_url else ""

        json_ld_data: dict[str, Any] = {}
        json_ld_match = cls._JSON_LD_PATTERN.search(html_text)
        if json_ld_match:
            with contextlib.suppress(Exception):
                json_ld_data = json.loads(json_ld_match.group(1))

        raw_title = ""
        poster_url: str | None = None
        added_at: datetime | None = None
        updated_at: datetime | None = None
        genres: list[str] = []

        if json_ld_data and "@graph" in json_ld_data:
            for item in json_ld_data["@graph"]:
                if item.get("@type") in ("Article", "WebPage"):
                    raw_title = item.get("headline") or item.get("name") or raw_title
                    if item.get("datePublished"):
                        with contextlib.suppress(Exception):
                            added_at = datetime.fromisoformat(item["datePublished"])
                    if item.get("dateModified"):
                        with contextlib.suppress(Exception):
                            updated_at = datetime.fromisoformat(item["dateModified"])
                    if item.get("thumbnailUrl"):
                        poster_url = item["thumbnailUrl"]
                    if item.get("articleSection") and isinstance(item["articleSection"], list):
                        for sec in item["articleSection"]:
                            if not cls._YEAR_SEC_PATTERN.match(sec) and sec not in (
                                "Film",
                                "HD",
                                "Vetrina-news",
                                "Serie TV",
                            ):
                                clean_sec = cls._PAREN_STRIP_PATTERN.sub("", sec).strip()
                                if clean_sec and clean_sec not in genres:
                                    genres.append(clean_sec)

        if not raw_title:
            title_tag = cls._PAGE_TITLE_PATTERN.search(html_text)
            if title_tag:
                raw_title = title_tag.group(1)

        clean_title, year, _, title_cert = cls.clean_title(raw_title)

        if not poster_url:
            og_img = cls._OG_IMAGE_PATTERN.search(html_text)
            if og_img:
                poster_url = og_img.group(1)

        desc_match = cls._MOVIE_DESC_PATTERN.search(html_text)
        description: str | None = None
        if desc_match:
            clean_desc = cls._HTML_TAG_PATTERN.sub("", desc_match.group(1)).strip()
            description = html.unescape(clean_desc)

        seasons_dict: dict[int, list[TvEpisode]] = {}
        tags = cls._TV_TAGS_PATTERN.findall(html_text)
        for t1, t2 in tags:
            content = t1 or t2
            p_text = html.unescape(cls._HTML_TAG_PATTERN.sub("", content))

            match = cls._SEASON_EP_MATCH_PATTERN.search(p_text)
            if match:
                season_num = int(match.group(1))
                ep_num = int(match.group(2))

                links = cls._EPISODE_LINK_PATTERN.findall(content)
                valid_sources: list[ProviderSource] = []
                for url, name_html in links:
                    name = html.unescape(cls._HTML_TAG_PATTERN.sub("", name_html)).strip()
                    if name.lower() in (
                        "maxstream",
                        "mixdrop",
                        "mixdrop.",
                        "maxstream.",
                        "streamtape",
                        "doodstream",
                        "wstream",
                    ) or cls._HOSTING_URL_PATTERN.search(url):
                        if not name or len(name) > 20:
                            if "mixdrop" in name.lower() or "mixdrop" in url.lower():
                                name = "Mixdrop"
                            elif "maxstream" in name.lower() or "maxstream" in url.lower():
                                name = "Maxstream"
                            else:
                                name = "Unknown"

                        provider_id = name.lower().replace(" ", "_").replace(".", "")
                        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                        source_id = f"{series_id}_s{season_num}e{ep_num}_{provider_id}_hd_{url_hash}"

                        valid_sources.append(
                            ProviderSource(
                                id=source_id,
                                media_id=series_id,
                                provider_id=provider_id,
                                provider_name=name,
                                page_url=url.strip(),
                                quality="HD",
                                language="ita",
                                available=True,
                            )
                        )

                if not valid_sources:
                    continue

                if season_num not in seasons_dict:
                    seasons_dict[season_num] = []

                ep_id = f"{series_id}_s{season_num}e{ep_num}"
                seasons_dict[season_num].append(
                    TvEpisode(
                        id=ep_id,
                        media_id=series_id,
                        season_number=season_num,
                        episode_number=ep_num,
                        title=f"Episodio {ep_num}",
                        sources=valid_sources,
                    )
                )

        seasons_list: list[TvSeason] = []
        for s_num in sorted(seasons_dict.keys()):
            ep_dict = {}
            for ep in seasons_dict[s_num]:
                if ep.episode_number not in ep_dict:
                    ep_dict[ep.episode_number] = ep
                else:
                    ep_dict[ep.episode_number].sources.extend(ep.sources)

            seasons_list.append(
                TvSeason(number=s_num, episodes=sorted(ep_dict.values(), key=lambda e: e.episode_number))
            )

        return TvSeries(
            id=series_id,
            title=clean_title,
            year=year,
            poster_url=poster_url,
            description=description,
            genres=genres,
            certification=title_cert,
            source_b_url=series_url,
            catalogs=["crawler"],
            seasons=seasons_list,
            added_at=added_at,
            updated_at=updated_at,
        )
