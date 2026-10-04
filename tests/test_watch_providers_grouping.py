"""Unit tests for watch providers canonical grouping, pay-per-view exclusion, and batch pre-loading endpoint."""

from __future__ import annotations

import pytest

from streaming_hub.backend.main import (
    BatchAvailabilityItem,
    BatchAvailabilityRequest,
    db,
    extract_streaming_availability,
    get_batch_streaming_availability,
    get_canonical_provider_group,
)


class TestWatchProvidersGrouping:
    """Test suite for streaming providers canonical grouping and exclusion rules."""

    def test_canonical_provider_group_resolution(self) -> None:
        """Test canonical mapping for various service name variants."""
        assert get_canonical_provider_group("Amazon Prime Video") == ("amazon", "Amazon Prime Video")
        assert get_canonical_provider_group("Amazon Prime Video with Ads") == ("amazon", "Amazon Prime Video")
        assert get_canonical_provider_group("Prime Video") == ("amazon", "Amazon Prime Video")
        assert get_canonical_provider_group("Netflix basic with Ads") == ("netflix", "Netflix")
        assert get_canonical_provider_group("Disney Plus") == ("disney", "Disney+")
        assert get_canonical_provider_group("Apple TV+") == ("apple", "Apple TV+")
        assert get_canonical_provider_group("Paramount Plus") == ("paramount", "Paramount+")
        assert get_canonical_provider_group("Mediaset Infinity") == ("mediaset", "Mediaset Infinity")
        assert get_canonical_provider_group("RaiPlay") == ("raiplay", "RaiPlay")

    def test_amazon_grouping_and_deduplication(self) -> None:
        """Test that multiple Amazon variants (flatrate + ads) collapse to exactly ONE Amazon logo."""
        raw_wp = {
            "IT": {
                "flatrate": [
                    {
                        "provider_id": 119,
                        "provider_name": "Amazon Prime Video",
                        "logo_path": "/amazon_prime.jpg",
                        "display_priority": 1,
                    }
                ],
                "ads": [
                    {
                        "provider_id": 619,
                        "provider_name": "Amazon Prime Video with Ads",
                        "logo_path": "/amazon_ads.jpg",
                        "display_priority": 2,
                    }
                ],
                "rent": [
                    {
                        "provider_id": 10,
                        "provider_name": "Amazon Video",
                        "logo_path": "/amazon_video.jpg",
                        "display_priority": 5,
                    }
                ],
            }
        }
        item = {"watch_providers": raw_wp}
        avail = extract_streaming_availability(item, "IT")

        # 1. grouped_logos for the card MUST have exactly 1 Amazon logo
        assert len(avail["grouped_logos"]) == 1
        assert avail["grouped_logos"][0]["group_id"] == "amazon"
        assert avail["grouped_logos"][0]["provider_name"] == "Amazon Prime Video"
        assert avail["grouped_logos"][0]["logo_path"] == "/amazon_prime.jpg"

        # 2. grouped_providers for the modal MUST consolidate the offers with badges
        assert len(avail["grouped_providers"]) == 1
        assert avail["grouped_providers"][0]["group_id"] == "amazon"
        badge_keys = [b["key"] for b in avail["grouped_providers"][0]["badges"]]
        assert "flatrate" in badge_keys
        assert "ads" in badge_keys
        assert "rent" not in badge_keys

    def test_zero_extra_cost_rule_excludes_rent_and_buy(self) -> None:
        """Zero extra cost rule: Titles available ONLY for rent or buy must NOT show streaming icons on cards."""
        raw_wp = {
            "IT": {
                "rent": [
                    {
                        "provider_id": 10,
                        "provider_name": "Amazon Video",
                        "logo_path": "/amazon.jpg",
                        "display_priority": 1,
                    },
                    {
                        "provider_id": 2,
                        "provider_name": "Apple TV",
                        "logo_path": "/apple.jpg",
                        "display_priority": 2,
                    },
                ],
                "buy": [
                    {
                        "provider_id": 3,
                        "provider_name": "Google Play Movies",
                        "logo_path": "/google.jpg",
                        "display_priority": 3,
                    }
                ],
            }
        }
        item = {"watch_providers": raw_wp}
        avail = extract_streaming_availability(item, "IT")

        # Must not display any icons or grouped providers for pay-per-view titles
        assert avail["grouped_logos"] == []
        assert avail["grouped_providers"] == []
        # Raw rent and buy are still accessible for the details modal rent section
        assert len(avail["rent"]) == 2
        assert len(avail["buy"]) == 1

    def test_multi_service_grouping(self) -> None:
        """Test grouping across multiple platforms up to max 4 logos."""
        raw_wp = {
            "IT": {
                "flatrate": [
                    {"provider_name": "Netflix", "logo_path": "/netflix.jpg", "display_priority": 1},
                    {"provider_name": "Amazon Prime Video", "logo_path": "/amazon.jpg", "display_priority": 2},
                    {"provider_name": "Disney Plus", "logo_path": "/disney.jpg", "display_priority": 3},
                    {"provider_name": "Apple TV+", "logo_path": "/apple.jpg", "display_priority": 4},
                    {"provider_name": "Paramount Plus", "logo_path": "/paramount.jpg", "display_priority": 5},
                ]
            }
        }
        avail = extract_streaming_availability({"watch_providers": raw_wp}, "IT")
        assert len(avail["grouped_logos"]) == 4
        groups = [x["group_id"] for x in avail["grouped_logos"]]
        assert groups == ["netflix", "amazon", "disney", "apple"]

    @pytest.mark.asyncio
    async def test_batch_streaming_availability_endpoint(self) -> None:
        """Test batch streaming availability endpoint with cached and uncached items."""
        test_id_cached = "test-wp-cached-1"
        test_id_missing = "test-wp-missing-2"

        # Pre-seed cached item in SQLite
        cached_wp = {
            "IT": {"flatrate": [{"provider_name": "Netflix", "logo_path": "/netflix.jpg", "display_priority": 1}]}
        }
        await db.update_title_watch_providers(
            test_id_cached,
            cached_wp,
            media_type="movie",
            title="Cached Movie",
            year=2024,
        )

        req = BatchAvailabilityRequest(
            profile_id="default",
            items=[
                BatchAvailabilityItem(id=test_id_cached, media_type="movie", title="Cached Movie", year=2024),
                BatchAvailabilityItem(id=test_id_missing, media_type="movie", title="Missing Movie", year=2024),
            ],
        )
        data = await get_batch_streaming_availability(req)
        assert "results" in data
        assert test_id_cached in data["results"]
        cached_result = data["results"][test_id_cached]
        assert len(cached_result["grouped_logos"]) == 1
        assert cached_result["grouped_logos"][0]["group_id"] == "netflix"

        # Missing item without TMDb returns empty availability without error
        assert test_id_missing in data["results"]
        missing_result = data["results"][test_id_missing]
        assert missing_result["grouped_logos"] == []
