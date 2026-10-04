"""Unit tests for home thematic carousels, crawler grid fallback, and parental control pruning."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from streaming_hub.backend.engine_reactive import ReactiveStreamClient
from streaming_hub.backend.models import Movie, Profile, TvSeries
from streaming_hub.backend.rating_filter import is_title_allowed_for_profile
from streaming_hub.backend.sources.crawler_source import CrawlerSource
from streaming_hub.backend.sources.manager import SourceManager
from streaming_hub.backend.sources.reactive_source import ReactiveSource


class TestHomeCarousels:
    """Test suite for home carousels, hero spotlight, and parental control pruning."""

    def setup_method(self, method=None) -> None:
        """Initialize mock profiles."""
        self.profile_all = Profile(id="p_all", name="Principale", rating_filter="ALL")
        self.profile_kids = Profile(id="p_kids", name="Bambini 6+", rating_filter="6+")
        self.profile_teen = Profile(id="p_teen", name="Ragazzi 14+", rating_filter="14+")

    @pytest.mark.asyncio
    async def test_get_homepage_carousels_parsing(self) -> None:
        """Test that ReactiveStreamClient correctly parses Inertia sliders and billboard."""
        client = ReactiveStreamClient(base_url="https://streaming.example.com")

        mock_props = {
            "props": {
                "billboard": {
                    "id": 999,
                    "name": "Featured Spotlight",
                    "slug": "featured-spotlight",
                    "type": "movie",
                    "release_date": "2026-01-01",
                    "score": "8.5",
                },
                "sliders": [
                    {
                        "name": "trending",
                        "titles": [
                            {"id": 101, "name": "Film Uno", "slug": "film-uno", "type": "movie", "score": "7.8"},
                            {"id": 102, "name": "Serie Due", "slug": "serie-due", "type": "tv", "score": "8.2"},
                        ],
                    },
                    {
                        "name": "latest",
                        "label": "Ultime Aggiunte",
                        "titles": [
                            {"id": 201, "name": "Film Tre", "slug": "film-tre", "type": "movie", "score": "6.5"},
                        ],
                    },
                ],
            }
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = json.dumps(mock_props)
            hero, carousels = await client.get_homepage_carousels()

            assert hero is not None
            assert hero.title == "Featured Spotlight"
            assert len(carousels) == 2

            # Check translation of trending and preservation of custom label
            assert carousels[0]["id"] == "trending"
            assert carousels[0]["title"] == "Di Tendenza"
            assert len(carousels[0]["items"]) == 2
            assert isinstance(carousels[0]["items"][0], Movie)
            assert isinstance(carousels[0]["items"][1], TvSeries)

            # Order must be preserved exactly as in upstream JSON
            assert carousels[0]["items"][0].title == "Film Uno"
            assert carousels[0]["items"][1].title == "Serie Due"

            assert carousels[1]["id"] == "latest"
            assert carousels[1]["title"] == "Ultime Aggiunte"
            assert len(carousels[1]["items"]) == 1

    def test_source_capabilities(self) -> None:
        """Test has_carousels capability on ReactiveSource vs CrawlerSource."""
        reactive = ReactiveSource(base_url="https://sc.example.com", enabled=True)
        crawler = CrawlerSource(base_url="https://cb.example.com", enabled=True)

        assert reactive.has_carousels is True
        assert crawler.has_carousels is False

    @pytest.mark.asyncio
    async def test_source_manager_crawler_only_returns_no_carousels(self) -> None:
        """Test that if only crawler source is enabled, manager returns no carousels (grid mode)."""
        manager = SourceManager()
        crawler = CrawlerSource(base_url="https://cb.example.com", enabled=True)
        manager.register_source(crawler)

        hero, carousels = await manager.get_home_carousels()
        assert hero is None
        assert carousels == []

    @pytest.mark.asyncio
    async def test_source_manager_with_reactive_returns_carousels(self) -> None:
        """Test that when ReactiveSource is present, manager fetches and delegates carousels."""
        manager = SourceManager()
        reactive = ReactiveSource(base_url="https://sc.example.com", enabled=True)

        mock_hero = Movie(id="sc-1", title="Hero Movie")
        mock_carousels = [
            {"id": "trending", "title": "Di Tendenza", "items": [mock_hero]},
        ]
        with patch.object(reactive, "get_carousels", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = (mock_hero, mock_carousels)
            manager.register_source(reactive)

            hero, carousels = await manager.get_home_carousels()
            assert hero == mock_hero
            assert len(carousels) == 1
            assert carousels[0]["title"] == "Di Tendenza"

    def test_parental_control_prunes_empty_carousels(self) -> None:
        """Test that carousels empty after parental control filtering are completely pruned."""
        safe_family_movie = Movie(id="s1", title="Il Re Leone", genres=["Animazione", "Famiglia"])
        adult_movie = Movie(id="a1", title="Film Horror VM18", certification="VM18", genres=["Horror"])

        raw_carousels = [
            {
                "id": "family_friendly",
                "title": "Per Tutta la Famiglia",
                "items": [safe_family_movie],
            },
            {
                "id": "adult_shelf",
                "title": "Cinema Per Adulti",
                "items": [adult_movie],
            },
        ]

        # Filter for kids profile (6+)
        filtered_carousels = []
        for c in raw_carousels:
            allowed = [it for it in c["items"] if is_title_allowed_for_profile(it, self.profile_kids)]
            if allowed:
                c_copy = dict(c)
                c_copy["items"] = allowed
                filtered_carousels.append(c_copy)

        # "Cinema Per Adulti" must be completely dropped because all items were blocked
        assert len(filtered_carousels) == 1
        assert filtered_carousels[0]["id"] == "family_friendly"
        assert filtered_carousels[0]["items"][0].title == "Il Re Leone"

    def test_hero_banner_selection_safety(self) -> None:
        """Test that Hero banner does not select an adult title on restricted profiles."""
        adult_hero = Movie(id="a_hero", title="Adult Billboard", is_adult=True)
        safe_candidate = Movie(id="s_cand", title="Safe Family Title", genres=["Animazione", "Famiglia"])

        allowed_pool = [safe_candidate]

        # For adults: adult hero is allowed
        assert is_title_allowed_for_profile(adult_hero, self.profile_all)

        # For kids: adult hero is blocked, fallback must pick safe title
        assert not is_title_allowed_for_profile(adult_hero, self.profile_kids)

        selected_hero = adult_hero if is_title_allowed_for_profile(adult_hero, self.profile_kids) else allowed_pool[0]
        assert selected_hero.title == "Safe Family Title"

    @pytest.mark.asyncio
    async def test_upcoming_and_unreleased_titles_are_excluded(self) -> None:
        """Test that upcoming sliders and unreleased titles are filtered out."""
        client = ReactiveStreamClient(base_url="https://streaming.example.com")

        mock_props = {
            "props": {
                "billboard": {
                    "id": 999,
                    "name": "Unreleased Billboard",
                    "coming_soon": True,
                    "type": "movie",
                },
                "sliders": [
                    {
                        "name": "upcoming",
                        "label": "In Arrivo",
                        "titles": [
                            {"id": 301, "name": "Film Futuro 1", "coming_soon": True},
                            {"id": 302, "name": "Film Futuro 2", "uploaded_at": None},
                        ],
                    },
                    {
                        "name": "trending",
                        "titles": [
                            {
                                "id": 101,
                                "name": "Film Disponibile",
                                "slug": "film-disp",
                                "type": "movie",
                                "coming_soon": False,
                            },
                            {
                                "id": 102,
                                "name": "Film In Arrivo",
                                "slug": "film-arr",
                                "type": "movie",
                                "coming_soon": True,
                            },
                            {
                                "id": 103,
                                "name": "Film Non Caricato",
                                "slug": "film-nc",
                                "type": "movie",
                                "uploaded_at": None,
                            },
                        ],
                    },
                ],
            }
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = json.dumps(mock_props)
            hero, carousels = await client.get_homepage_carousels()

            # The unreleased billboard must be rejected
            # And the first available item in carousels chosen instead
            assert hero is not None
            assert hero.title == "Film Disponibile"

            # The 'upcoming' slider must be completely excluded
            assert len(carousels) == 1
            assert carousels[0]["id"] == "trending"

            # Inside trending, only 'Film Disponibile' must remain
            assert len(carousels[0]["items"]) == 1
            assert carousels[0]["items"][0].title == "Film Disponibile"

    @pytest.mark.asyncio
    async def test_get_homepage_carousels_fallback_to_movies_and_tv(self) -> None:
        """Test fallback to /it/movies and /it/tv-shows when home candidate URLs have no sliders."""
        client = ReactiveStreamClient(base_url="https://streaming.example.com/")

        empty_props = json.dumps({"props": {"sliders": []}})
        movies_props = json.dumps(
            {
                "props": {
                    "sliders": [
                        {
                            "name": "trending",
                            "titles": [{"id": 501, "name": "Film Popolare", "slug": "film-pop", "type": "movie"}],
                        }
                    ]
                }
            }
        )
        tv_props = json.dumps(
            {
                "props": {
                    "sliders": [
                        {
                            "name": "trending",
                            "titles": [{"id": 601, "name": "Serie Popolare", "slug": "serie-pop", "type": "tv"}],
                        }
                    ]
                }
            }
        )

        async def mock_request_side_effect(url: str, headers: dict | None = None) -> str:
            if "movies" in url:
                return movies_props
            if "tv-shows" in url:
                return tv_props
            return empty_props

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = mock_request_side_effect
            hero, carousels = await client.get_homepage_carousels()

            assert hero is not None
            assert hero.title == "Film Popolare"
            assert len(carousels) == 2
            assert carousels[0]["title"] == "Film del Momento"
            assert carousels[1]["title"] == "Serie TV del Momento"
