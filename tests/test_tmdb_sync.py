"""Tests for TMDb catalog enrichment and personal account synchronization."""

from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from streaming_hub.backend.database import MediaDatabase
from streaming_hub.backend.metadata import MetadataEnricher
from streaming_hub.backend.models import Movie


class TestTmdbSync:
    """Test suite for TMDb sync features."""

    @pytest.fixture(autouse=True)
    def setup_db(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tmdb.db"
        self.db = MediaDatabase(self.db_path)
        self.db._init_sync()
        yield
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_tmdb_session_lifecycle(self) -> None:
        """Verify saving, retrieving, and deleting a TMDb user session in database."""
        # Initial state: no session
        session = await self.db.get_tmdb_session("user1")
        assert session is None

        # Save session
        await self.db.save_tmdb_session(
            profile_id="user1",
            session_id="tmdb_sess_xyz123",
            account_id=98765,
            username="andrea_user",
            avatar_url="https://image.tmdb.org/t/p/w200/avatar.jpg",
        )

        session = await self.db.get_tmdb_session("user1")
        assert session is not None
        assert session["session_id"] == "tmdb_sess_xyz123"
        assert session["account_id"] == 98765
        assert session["username"] == "andrea_user"

        # Delete session
        deleted = await self.db.delete_tmdb_session("user1")
        assert deleted is True

        session = await self.db.get_tmdb_session("user1")
        assert session is None

    @pytest.mark.asyncio
    async def test_get_titles_for_enrichment(self) -> None:
        """Verify titles needing TMDb metadata are queried correctly."""
        # Title missing tmdb_id
        m1 = Movie(id="movie-1", title="Title One", year=2024)
        await self.db.save_title(m1)

        # Title with tmdb_id and backdrop
        m2 = Movie(id="movie-2", title="Title Two", year=2024, tmdb_id=123, backdrop_url="http://backdrop.jpg")
        m2.certification = "T"
        await self.db.save_title(m2)

        candidates = await self.db.get_titles_for_enrichment(limit=10)
        candidate_ids = [c["id"] for c in candidates]
        assert "movie-1" in candidate_ids

    @pytest.mark.asyncio
    async def test_add_favorite_idempotent(self) -> None:
        """Verify add_favorite inserts once and does not duplicate."""
        res1 = await self.db.add_favorite(
            title_id="fav-movie-1",
            media_type="movie",
            title="Favorite Movie",
            poster_url="http://poster.jpg",
            profile_id="default",
        )
        assert res1 is True

        res2 = await self.db.add_favorite(
            title_id="fav-movie-1",
            media_type="movie",
            title="Favorite Movie",
            poster_url="http://poster.jpg",
            profile_id="default",
        )
        assert res2 is False

        favs = await self.db.get_favorites("default")
        assert len(favs) == 1
        assert favs[0]["title"] == "Favorite Movie"

    @pytest.mark.asyncio
    async def test_metadata_enricher_create_request_token(self) -> None:
        """Verify request token creation parsing from TMDb API response."""
        enricher = MetadataEnricher(tmdb_api_key="mock_tmdb_key")
        mock_response = {
            "success": True,
            "request_token": "req_token_abc456",
            "expires_at": "2026-10-08 00:00:00 UTC",
        }

        with patch.object(enricher, "_get_json", new=AsyncMock(return_value=mock_response)):
            result = await enricher.create_request_token()
            assert result["success"] is True
            assert result["request_token"] == "req_token_abc456"
            assert "https://www.themoviedb.org/authenticate/req_token_abc456" in result["auth_url"]
