"""Internal data models for Streaming Hub."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProviderSource:
    """A streaming or media source available for a movie or episode."""

    id: str
    media_id: str

    provider_id: str
    provider_name: str

    page_url: str

    language: str | None = "ita"
    quality: str | None = None  # e.g., "HD", "SD", "FHD", "4K"

    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "media_id": self.media_id,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "page_url": self.page_url,
            "language": self.language,
            "quality": self.quality,
            "available": self.available,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderSource:
        """Reconstruct from dictionary."""
        return cls(
            id=data["id"],
            media_id=data["media_id"],
            provider_id=data["provider_id"],
            provider_name=data["provider_name"],
            page_url=data["page_url"],
            language=data.get("language"),
            quality=data.get("quality"),
            available=data.get("available", True),
        )


@dataclass
class Movie:
    """A movie entry in the catalog."""

    id: str
    title: str
    original_title: str | None = None
    year: int | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    description: str | None = None
    genres: list[str] = field(default_factory=list)
    duration: int | None = None  # in minutes
    rating: float | None = None

    cast: list[str] = field(default_factory=list)
    director: str | None = None

    source_a_url: str = ""
    source_b_url: str = ""
    tmdb_id: int | None = None
    imdb_id: str | None = None
    trakt_id: int | None = None
    certification: str | None = None
    is_adult: bool = False
    is_anime: bool = False
    dub_type: str | None = None  # "sub" or "dub"
    catalogs: list[str] = field(default_factory=list)
    watch_providers: dict[str, Any] = field(default_factory=dict)

    sources: list[ProviderSource] = field(default_factory=list)

    added_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def streamingcommunity_url(self) -> str:
        return self.source_a_url

    @streamingcommunity_url.setter
    def streamingcommunity_url(self, val: str) -> None:
        self.source_a_url = val

    @property
    def cb01_url(self) -> str:
        return self.source_b_url

    @cb01_url.setter
    def cb01_url(self, val: str) -> None:
        self.source_b_url = val

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": "movie",
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "poster_url": self.poster_url,
            "backdrop_url": self.backdrop_url,
            "description": self.description,
            "genres": self.genres,
            "duration": self.duration,
            "rating": self.rating,
            "certification": self.certification,
            "is_adult": self.is_adult,
            "is_anime": self.is_anime,
            "dub_type": self.dub_type,
            "cast": self.cast,
            "director": self.director,
            "source_a_url": self.source_a_url,
            "source_b_url": self.source_b_url,
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "trakt_id": self.trakt_id,
            "catalogs": self.catalogs,
            "watch_providers": self.watch_providers,
            "sources": [s.to_dict() for s in self.sources],
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Movie:
        """Reconstruct from dictionary."""
        sources = [ProviderSource.from_dict(s) for s in data.get("sources", [])]
        added_at = datetime.fromisoformat(data["added_at"]) if data.get("added_at") else None
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        return cls(
            id=data["id"],
            title=data["title"],
            original_title=data.get("original_title"),
            year=data.get("year"),
            poster_url=data.get("poster_url"),
            backdrop_url=data.get("backdrop_url"),
            description=data.get("description"),
            genres=data.get("genres", []),
            duration=data.get("duration"),
            rating=data.get("rating"),
            certification=data.get("certification"),
            is_adult=bool(data.get("is_adult", False)),
            is_anime=bool(data.get("is_anime", False)),
            dub_type=data.get("dub_type"),
            cast=data.get("cast", []),
            director=data.get("director"),
            source_a_url=data.get("source_a_url") or data.get("streamingcommunity_url", ""),
            source_b_url=data.get("source_b_url") or data.get("cb01_url", ""),
            tmdb_id=data.get("tmdb_id"),
            imdb_id=data.get("imdb_id"),
            trakt_id=data.get("trakt_id"),
            catalogs=data.get("catalogs", []),
            watch_providers=data.get("watch_providers", {}),
            sources=sources,
            added_at=added_at,
            updated_at=updated_at,
        )


@dataclass
class TvEpisode:
    """An episode in a TV Series."""

    id: str
    media_id: str
    season_number: int
    episode_number: int

    title: str = ""
    description: str | None = None
    poster_url: str | None = None

    sources: list[ProviderSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "media_id": self.media_id,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "title": self.title,
            "description": self.description,
            "poster_url": self.poster_url,
            "sources": [s.to_dict() for s in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TvEpisode:
        """Reconstruct from dictionary."""
        return cls(
            id=data["id"],
            media_id=data["media_id"],
            season_number=data["season_number"],
            episode_number=data["episode_number"],
            title=data.get("title", ""),
            description=data.get("description"),
            poster_url=data.get("poster_url"),
            sources=[ProviderSource.from_dict(s) for s in data.get("sources", [])],
        )


@dataclass
class TvSeason:
    """A season in a TV Series."""

    number: int
    episodes: list[TvEpisode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {"number": self.number, "episodes": [e.to_dict() for e in self.episodes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TvSeason:
        """Reconstruct from dictionary."""
        return cls(number=data["number"], episodes=[TvEpisode.from_dict(e) for e in data.get("episodes", [])])


@dataclass
class TvSeries:
    """A TV series entry in the catalog."""

    id: str
    title: str
    original_title: str | None = None
    year: int | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    description: str | None = None
    genres: list[str] = field(default_factory=list)
    rating: float | None = None
    cast: list[str] = field(default_factory=list)
    director: str | None = None

    source_a_url: str = ""
    source_b_url: str = ""
    tmdb_id: int | None = None
    imdb_id: str | None = None
    trakt_id: int | None = None
    certification: str | None = None
    is_adult: bool = False
    is_anime: bool = False
    dub_type: str | None = None  # "sub" or "dub"
    catalogs: list[str] = field(default_factory=list)
    watch_providers: dict[str, Any] = field(default_factory=dict)

    seasons: list[TvSeason] = field(default_factory=list)

    added_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def streamingcommunity_url(self) -> str:
        return self.source_a_url

    @streamingcommunity_url.setter
    def streamingcommunity_url(self, val: str) -> None:
        self.source_a_url = val

    @property
    def cb01_url(self) -> str:
        return self.source_b_url

    @cb01_url.setter
    def cb01_url(self, val: str) -> None:
        self.source_b_url = val

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": "tv",
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "poster_url": self.poster_url,
            "backdrop_url": self.backdrop_url,
            "description": self.description,
            "genres": self.genres,
            "rating": self.rating,
            "certification": self.certification,
            "is_adult": self.is_adult,
            "is_anime": self.is_anime,
            "dub_type": self.dub_type,
            "cast": self.cast,
            "director": self.director,
            "source_a_url": self.source_a_url,
            "source_b_url": self.source_b_url,
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "trakt_id": self.trakt_id,
            "catalogs": self.catalogs,
            "watch_providers": self.watch_providers,
            "seasons": [s.to_dict() for s in self.seasons],
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TvSeries:
        """Reconstruct from dictionary."""
        added_at = datetime.fromisoformat(data["added_at"]) if data.get("added_at") else None
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        return cls(
            id=data["id"],
            title=data["title"],
            original_title=data.get("original_title"),
            year=data.get("year"),
            poster_url=data.get("poster_url"),
            backdrop_url=data.get("backdrop_url"),
            description=data.get("description"),
            genres=data.get("genres", []),
            rating=data.get("rating"),
            certification=data.get("certification"),
            is_adult=bool(data.get("is_adult", False)),
            is_anime=bool(data.get("is_anime", False)),
            dub_type=data.get("dub_type"),
            cast=data.get("cast", []),
            director=data.get("director"),
            source_a_url=data.get("source_a_url") or data.get("streamingcommunity_url", ""),
            source_b_url=data.get("source_b_url") or data.get("cb01_url", ""),
            tmdb_id=data.get("tmdb_id"),
            imdb_id=data.get("imdb_id"),
            trakt_id=data.get("trakt_id"),
            catalogs=data.get("catalogs", []),
            watch_providers=data.get("watch_providers", {}),
            seasons=[TvSeason.from_dict(s) for s in data.get("seasons", [])],
            added_at=added_at,
            updated_at=updated_at,
        )


@dataclass
class Profile:
    """A user profile within the Family Account."""

    id: str
    name: str
    avatar: str = "avatar_1"
    rating_filter: str = "ALL"  # ALL, 18+, 14+, 6+, T
    country: str = ""
    tmdb_api_key: str = ""
    trakt_client_id: str = ""
    trakt_access_token: str = ""
    pin: str | None = None

    def to_dict(self, include_secrets: bool = False) -> dict[str, Any]:
        """Convert profile to dict, omitting sensitive keys unless requested."""
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "rating_filter": self.rating_filter,
            "country": self.country,
            "has_pin": bool(self.pin),
            "tmdb_configured": bool(self.tmdb_api_key),
            "trakt_configured": bool(self.trakt_client_id),
            "trakt_authenticated": bool(self.trakt_access_token),
        }
        if include_secrets:
            data["tmdb_api_key"] = self.tmdb_api_key
            data["trakt_client_id"] = self.trakt_client_id
            data["trakt_access_token"] = self.trakt_access_token
            data["pin"] = self.pin
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        """Create Profile from dictionary."""
        return cls(
            id=str(data.get("id", "default")),
            name=str(data.get("name", "Principale")),
            avatar=str(data.get("avatar", "avatar_1")),
            rating_filter=str(data.get("rating_filter", "ALL")),
            country=str(data.get("country", "")).strip().upper(),
            tmdb_api_key=str(data.get("tmdb_api_key", "")).strip(),
            trakt_client_id=str(data.get("trakt_client_id", "")).strip(),
            trakt_access_token=str(data.get("trakt_access_token", "")).strip(),
            pin=str(data["pin"]).strip() if data.get("pin") else None,
        )


@dataclass
class SubtitleTrack:
    """A subtitle track representation for web player and Cast."""

    id: str
    language: str  # e.g. "it", "en"
    label: str  # e.g. "Italiano", "English"
    url: str  # Proxied VTT or SRT URL
    format: str = "vtt"
    is_default: bool = False
    is_forced: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "language": self.language,
            "label": self.label,
            "url": self.url,
            "format": self.format,
            "is_default": self.is_default,
            "is_forced": self.is_forced,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubtitleTrack:
        """Construct from dictionary."""
        return cls(
            id=str(data.get("id", "")),
            language=str(data.get("language", "it")),
            label=str(data.get("label", "Sottotitoli")),
            url=str(data.get("url", "")),
            format=str(data.get("format", "vtt")),
            is_default=bool(data.get("is_default", False)),
            is_forced=bool(data.get("is_forced", False)),
        )


@dataclass
class ResolvedMedia:
    """A playable media stream resolved from a provider source."""

    url: str

    mime_type: str | None = "application/vnd.apple.mpegurl"
    stream_format: str | None = "hls"

    title: str = ""
    poster_url: str | None = None
    duration: int | None = None
    provider_id: str = ""
    expires_at: datetime | None = None
    headers: dict[str, str] = field(default_factory=dict)
    subtitles: list[SubtitleTrack] = field(default_factory=list)


@dataclass(frozen=True)
class CastDeviceInfo:
    """Information about a discovered media player or Cast device."""

    entity_id: str
    name: str
    is_cast: bool
    state: str
    device_class: str | None = None
