"""Tests for sync service functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
import httpx

from radarr_manager.services.sync import SyncService
from radarr_manager.models import MovieSuggestion, SyncSummary
from radarr_manager.clients.radarr import RadarrClient
from tests.fixtures.radarr_responses import (
    MOVIE_LOOKUP_RESPONSE,
    EMPTY_MOVIE_LOOKUP_RESPONSE,
    MOVIE_LIST_RESPONSE,
    ADD_MOVIE_SUCCESS_RESPONSE,
)


@pytest.fixture
def mock_radarr_client():
    """Create a mock RadarrClient for testing."""
    client = AsyncMock(spec=RadarrClient)
    # Pre-configure methods that are expected by tests
    client.list_movies = AsyncMock()
    client.lookup_movie = AsyncMock()
    client.ensure_movie = AsyncMock()
    return client


@pytest.fixture
def sync_service(mock_radarr_client):
    """Create a SyncService instance with mocked client."""
    return SyncService(
        mock_radarr_client,
        quality_profile_id=1,
        root_folder_path="/data/movies",
        monitor=True,
        minimum_availability="announced",
        tags=["radarr-manager"],
    )


@pytest.fixture
def sync_service_no_config(mock_radarr_client):
    """Create a SyncService instance without required configuration."""
    return SyncService(
        mock_radarr_client,
        quality_profile_id=None,
        root_folder_path=None,
        monitor=True,
        minimum_availability=None,
        tags=None,
    )


@pytest.fixture
def sample_suggestions():
    """Create sample movie suggestions for testing."""
    return [
        MovieSuggestion(
            title="Dune: Part Two",
            release_date=date(2024, 2, 29),
            overview="Epic sci-fi sequel",
            confidence=0.9,
            sources=["tmdb"],
        ),
        MovieSuggestion(
            title="Unknown Movie",
            release_date=date(2024, 5, 15),
            overview="Mystery film",
            confidence=0.7,
            sources=["imdb"],
        ),
        MovieSuggestion(
            title="Future Release",
            release_date=None,  # No release date
            overview="TBD movie",
            confidence=0.5,
            sources=["variety"],
        ),
    ]


class TestSyncService:
    """Test cases for SyncService."""

    def test_sync_service_initialization(self, mock_radarr_client):
        """Test SyncService initialization with all parameters."""
        service = SyncService(
            mock_radarr_client,
            quality_profile_id=5,
            root_folder_path="/custom/path",
            monitor=False,
            minimum_availability="released",
            tags=["tag1", "tag2"],
        )

        assert service._client == mock_radarr_client
        assert service._quality_profile_id == 5
        assert service._root_folder_path == "/custom/path"
        assert service._monitor is False
        assert service._minimum_availability == "released"
        assert service._tags == ["tag1", "tag2"]

    def test_sync_service_initialization_with_none_tags(self, mock_radarr_client):
        """Test SyncService initialization with None tags."""
        service = SyncService(
            mock_radarr_client,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
            minimum_availability=None,
            tags=None,
        )

        assert service._tags == []

    @pytest.mark.asyncio
    async def test_sync_dry_run_mode(self, sync_service, sample_suggestions):
        """Test sync in dry-run mode."""
        result = await sync_service.sync(sample_suggestions, dry_run=True, force=False)

        assert isinstance(result, SyncSummary)
        assert result.dry_run is True
        assert len(result.queued) == 3
        assert result.queued == ["Dune: Part Two", "Unknown Movie", "Future Release"]
        assert len(result.skipped) == 0
        assert len(result.errors) == 0

        # Verify no actual API calls were made
        sync_service._client.list_movies.assert_not_called()
        sync_service._client.lookup_movie.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_missing_configuration_error(
        self, sync_service_no_config, sample_suggestions
    ):
        """Test sync fails when required configuration is missing."""
        with pytest.raises(
            RuntimeError, match="quality_profile_id and root_folder_path must be configured"
        ):
            await sync_service_no_config.sync(sample_suggestions, dry_run=False, force=False)

    @pytest.mark.asyncio
    async def test_sync_empty_suggestions(self, sync_service):
        """Test sync with empty suggestions list."""
        result = await sync_service.sync([], dry_run=False, force=False)

        assert result.dry_run is False
        assert len(result.queued) == 0
        assert len(result.skipped) == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_sync_successful_addition(self, sync_service, mock_radarr_client):
        """Test successful movie addition during sync."""
        suggestion = MovieSuggestion(
            title="Dune: Part Two",
            release_date=date(2024, 2, 29),
            confidence=0.9,
        )

        # Mock existing movies (empty list)
        mock_radarr_client.list_movies.return_value = []

        # Mock successful lookup
        mock_radarr_client.lookup_movie.return_value = MOVIE_LOOKUP_RESPONSE

        # Mock successful addition
        mock_radarr_client.ensure_movie.return_value = ADD_MOVIE_SUCCESS_RESPONSE

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 1
        assert result.queued[0] == "Dune: Part Two"
        assert len(result.skipped) == 0
        assert len(result.errors) == 0

        # Verify API calls
        mock_radarr_client.list_movies.assert_called_once()
        mock_radarr_client.lookup_movie.assert_called_once_with("Dune: Part Two")
        mock_radarr_client.ensure_movie.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_skips_movies_without_release_date(self, sync_service, mock_radarr_client):
        """Test sync skips movies without release date."""
        suggestion = MovieSuggestion(
            title="TBD Movie",
            release_date=None,  # No release date
            confidence=0.5,
        )

        mock_radarr_client.list_movies.return_value = []

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0] == "TBD Movie"
        assert len(result.errors) == 0

        # Should not attempt lookup for movies without release date
        mock_radarr_client.lookup_movie.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skips_movies_with_no_lookup_results(self, sync_service, mock_radarr_client):
        """Test sync skips movies that cannot be found in Radarr lookup."""
        suggestion = MovieSuggestion(
            title="Unknown Movie",
            release_date=date(2024, 5, 15),
            confidence=0.7,
        )

        mock_radarr_client.list_movies.return_value = []
        mock_radarr_client.lookup_movie.return_value = EMPTY_MOVIE_LOOKUP_RESPONSE

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0] == "Unknown Movie"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_sync_skips_movies_with_invalid_year(self, sync_service, mock_radarr_client):
        """Test sync skips movies with invalid year in lookup response."""
        suggestion = MovieSuggestion(
            title="Bad Year Movie",
            release_date=date(2024, 5, 15),
            confidence=0.7,
        )

        # Mock lookup response with invalid year
        invalid_lookup = MOVIE_LOOKUP_RESPONSE.copy()
        invalid_lookup[0]["year"] = None

        mock_radarr_client.list_movies.return_value = []
        mock_radarr_client.lookup_movie.return_value = invalid_lookup

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0] == "Bad Year Movie"

    @pytest.mark.asyncio
    async def test_sync_skips_duplicate_movies(self, sync_service, mock_radarr_client):
        """Test sync skips movies that already exist in Radarr."""
        suggestion = MovieSuggestion(
            title="The Matrix",
            release_date=date(1999, 3, 31),
            confidence=0.9,
        )

        # Mock existing movies list with The Matrix
        mock_radarr_client.list_movies.return_value = MOVIE_LIST_RESPONSE

        # Mock lookup that would match existing movie
        matrix_lookup = [{"tmdbId": 603, "title": "The Matrix", "year": 1999}]
        mock_radarr_client.lookup_movie.return_value = matrix_lookup

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0] == "The Matrix"
        assert len(result.errors) == 0

        # Should not attempt to add duplicate movie
        mock_radarr_client.ensure_movie.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_force_adds_duplicate_movies(self, sync_service, mock_radarr_client):
        """Test sync adds duplicate movies when force=True."""
        suggestion = MovieSuggestion(
            title="The Matrix",
            release_date=date(1999, 3, 31),
            confidence=0.9,
        )

        # Mock existing movies list with The Matrix
        mock_radarr_client.list_movies.return_value = MOVIE_LIST_RESPONSE

        # Mock lookup that would match existing movie
        matrix_lookup = [{"tmdbId": 603, "title": "The Matrix", "year": 1999}]
        mock_radarr_client.lookup_movie.return_value = matrix_lookup

        # Mock successful addition despite duplicate
        mock_radarr_client.ensure_movie.return_value = {"title": "The Matrix", "id": 999}

        result = await sync_service.sync([suggestion], dry_run=False, force=True)

        assert len(result.queued) == 1
        assert result.queued[0] == "The Matrix"
        assert len(result.skipped) == 0
        assert len(result.errors) == 0

        # Should attempt to add even though it's a duplicate
        mock_radarr_client.ensure_movie.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_handles_http_errors(self, sync_service, mock_radarr_client):
        """Test sync handles HTTP errors during movie addition."""
        suggestion = MovieSuggestion(
            title="Error Movie",
            release_date=date(2024, 5, 15),
            confidence=0.7,
        )

        mock_radarr_client.list_movies.return_value = []
        mock_radarr_client.lookup_movie.return_value = MOVIE_LOOKUP_RESPONSE

        # Mock HTTP error during addition
        error_response = MagicMock()
        error_response.json.return_value = {"error": "Movie already exists"}
        error_response.text = "Bad Request"

        http_error = httpx.HTTPStatusError(
            "400 Bad Request", request=MagicMock(), response=error_response
        )
        mock_radarr_client.ensure_movie.side_effect = http_error

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 0
        assert len(result.skipped) == 0
        assert len(result.errors) == 1
        assert "Error Movie:" in result.errors[0]
        assert "400 Bad Request" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_handles_non_json_http_errors(self, sync_service, mock_radarr_client):
        """Test sync handles HTTP errors with non-JSON responses."""
        suggestion = MovieSuggestion(
            title="Error Movie",
            release_date=date(2024, 5, 15),
            confidence=0.7,
        )

        mock_radarr_client.list_movies.return_value = []
        mock_radarr_client.lookup_movie.return_value = MOVIE_LOOKUP_RESPONSE

        # Mock HTTP error with non-JSON response
        error_response = MagicMock()
        error_response.json.side_effect = ValueError("Not JSON")
        error_response.text = "Internal Server Error"

        http_error = httpx.HTTPStatusError(
            "500 Internal Server Error", request=MagicMock(), response=error_response
        )
        mock_radarr_client.ensure_movie.side_effect = http_error

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.errors) == 1
        assert "Error Movie:" in result.errors[0]
        assert "Internal Server Error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_handles_general_exceptions(self, sync_service, mock_radarr_client):
        """Test sync handles general exceptions during movie addition."""
        suggestion = MovieSuggestion(
            title="Exception Movie",
            release_date=date(2024, 5, 15),
            confidence=0.7,
        )

        mock_radarr_client.list_movies.return_value = []
        mock_radarr_client.lookup_movie.return_value = MOVIE_LOOKUP_RESPONSE

        # Mock general exception
        mock_radarr_client.ensure_movie.side_effect = Exception("Unexpected error")

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        assert len(result.queued) == 0
        assert len(result.skipped) == 0
        assert len(result.errors) == 1
        assert "Exception Movie: Unexpected error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_handles_malformed_tmdb_ids(self, sync_service, mock_radarr_client):
        """Test sync handles malformed TMDB IDs in existing movies."""
        suggestion = MovieSuggestion(
            title="Test Movie",
            release_date=date(2024, 5, 15),
            confidence=0.7,
        )

        # Mock existing movies with malformed TMDB IDs
        malformed_movies = [
            {"tmdbId": "not-a-number", "title": "Bad Movie 1"},
            {"tmdbId": None, "title": "Bad Movie 2"},
            {"tmdbId": 123, "title": "Good Movie"},
        ]
        mock_radarr_client.list_movies.return_value = malformed_movies

        # Mock lookup with different TMDB ID
        test_lookup = [{"tmdbId": 456, "title": "Test Movie", "year": 2024}]
        mock_radarr_client.lookup_movie.return_value = test_lookup

        mock_radarr_client.ensure_movie.return_value = {"title": "Test Movie", "id": 789}

        result = await sync_service.sync([suggestion], dry_run=False, force=False)

        # Should successfully add since TMDB ID 456 is not in existing (valid) IDs
        assert len(result.queued) == 1
        assert result.queued[0] == "Test Movie"

    @pytest.mark.asyncio
    async def test_sync_multiple_suggestions_mixed_results(
        self, sync_service, mock_radarr_client, sample_suggestions
    ):
        """Test sync with multiple suggestions having mixed outcomes."""
        # Mock existing movies (empty)
        mock_radarr_client.list_movies.return_value = []

        # Mock different lookup results for each suggestion
        def mock_lookup_side_effect(title):
            if title == "Dune: Part Two":
                return MOVIE_LOOKUP_RESPONSE
            elif title == "Unknown Movie":
                return EMPTY_MOVIE_LOOKUP_RESPONSE  # Not found
            else:  # "Future Release"
                return [{"tmdbId": 999, "title": "Future Release", "year": 0}]  # Invalid year

        mock_radarr_client.lookup_movie.side_effect = mock_lookup_side_effect

        # Mock successful addition for the one that gets through
        mock_radarr_client.ensure_movie.return_value = ADD_MOVIE_SUCCESS_RESPONSE

        result = await sync_service.sync(sample_suggestions, dry_run=False, force=False)

        # One queued (Dune), two skipped (Unknown Movie - no results, Future Release - no date + invalid year)
        assert len(result.queued) == 1
        assert result.queued[0] == "Dune: Part Two"
        assert len(result.skipped) == 2
        assert "Unknown Movie" in result.skipped
        assert "Future Release" in result.skipped
        assert len(result.errors) == 0

    def test_sync_summary_total_candidates_property(self):
        """Test SyncSummary total_candidates property."""
        summary = SyncSummary(
            dry_run=False,
            queued=["Movie 1", "Movie 2"],
            skipped=["Movie 3"],
            errors=["Movie 4: Error"],
        )

        assert summary.total_candidates == 3  # queued + skipped (errors don't count as candidates)
