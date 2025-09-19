"""Tests for Radarr client functionality."""

import pytest
import httpx
import respx
from unittest.mock import AsyncMock

from radarr_manager.clients.radarr import RadarrClient, build_add_movie_payload, radarr_client
from tests.fixtures.radarr_responses import (
    SYSTEM_STATUS_RESPONSE,
    MOVIE_LOOKUP_RESPONSE,
    EMPTY_MOVIE_LOOKUP_RESPONSE,
    MOVIE_LIST_RESPONSE,
    ROOT_FOLDERS_RESPONSE,
    QUALITY_PROFILES_RESPONSE,
    ADD_MOVIE_SUCCESS_RESPONSE,
    ADD_MOVIE_ERROR_RESPONSE,
)


@pytest.fixture
def client():
    """Create a RadarrClient instance for testing."""
    return RadarrClient(
        base_url="http://localhost:7878",
        api_key="test-api-key",
        timeout=10.0
    )


class TestRadarrClient:
    """Test cases for RadarrClient."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client is properly initialized with headers."""
        client = RadarrClient(
            base_url="http://localhost:7878",
            api_key="test-key",
            timeout=15.0
        )

        assert client._client.base_url == "http://localhost:7878"
        assert client._client.headers["X-Api-Key"] == "test-key"
        assert client._client.headers["User-Agent"] == "radarr-manager/0.1.0"
        assert client._client.headers["Accept"] == "application/json"
        assert client._client.timeout.read == 15.0

        await client.close()

    @pytest.mark.asyncio
    async def test_client_strips_trailing_slash_from_base_url(self):
        """Test that trailing slash is removed from base URL."""
        client = RadarrClient(
            base_url="http://localhost:7878/",
            api_key="test-key"
        )

        assert client._client.base_url == "http://localhost:7878"
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_ping_success(self, client):
        """Test successful ping operation."""
        respx.get("http://localhost:7878/system/status").mock(
            return_value=httpx.Response(200, json=SYSTEM_STATUS_RESPONSE)
        )

        result = await client.ping()
        assert result == SYSTEM_STATUS_RESPONSE
        assert result["appName"] == "Radarr"

    @pytest.mark.asyncio
    @respx.mock
    async def test_ping_http_error(self, client):
        """Test ping with HTTP error response."""
        respx.get("http://localhost:7878/system/status").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.ping()

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_movie_success(self, client):
        """Test successful movie lookup."""
        respx.get("http://localhost:7878/movie/lookup").mock(
            return_value=httpx.Response(200, json=MOVIE_LOOKUP_RESPONSE)
        )

        result = await client.lookup_movie("Dune Part Two")
        assert len(result) == 1
        assert result[0]["title"] == "Dune: Part Two"
        assert result[0]["tmdbId"] == 693134

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_movie_no_results(self, client):
        """Test movie lookup with no results."""
        respx.get("http://localhost:7878/movie/lookup").mock(
            return_value=httpx.Response(200, json=EMPTY_MOVIE_LOOKUP_RESPONSE)
        )

        result = await client.lookup_movie("Nonexistent Movie")
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_lookup_movie_with_query_params(self, client):
        """Test that movie lookup sends correct query parameters."""
        mock_route = respx.get("http://localhost:7878/movie/lookup").mock(
            return_value=httpx.Response(200, json=MOVIE_LOOKUP_RESPONSE)
        )

        await client.lookup_movie("Test Movie")

        assert mock_route.call_count == 1
        request = mock_route.calls[0].request
        assert request.url.params["term"] == "Test Movie"

    @pytest.mark.asyncio
    @respx.mock
    async def test_add_movie_success(self, client):
        """Test successful movie addition."""
        payload = {"tmdbId": 693134, "title": "Dune: Part Two"}

        respx.post("http://localhost:7878/movie").mock(
            return_value=httpx.Response(201, json=ADD_MOVIE_SUCCESS_RESPONSE)
        )

        result = await client.add_movie(payload)
        assert result["title"] == "Dune: Part Two"
        assert result["id"] == 123

    @pytest.mark.asyncio
    @respx.mock
    async def test_add_movie_duplicate_error(self, client):
        """Test movie addition with duplicate error."""
        payload = {"tmdbId": 693134, "title": "Dune: Part Two"}

        respx.post("http://localhost:7878/movie").mock(
            return_value=httpx.Response(400, json=ADD_MOVIE_ERROR_RESPONSE)
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.add_movie(payload)

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_root_folders(self, client):
        """Test listing root folders."""
        respx.get("http://localhost:7878/rootfolder").mock(
            return_value=httpx.Response(200, json=ROOT_FOLDERS_RESPONSE)
        )

        result = await client.list_root_folders()
        assert len(result) == 1
        assert result[0]["path"] == "/data/movies"
        assert result[0]["accessible"] is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_quality_profiles(self, client):
        """Test listing quality profiles."""
        respx.get("http://localhost:7878/qualityprofile").mock(
            return_value=httpx.Response(200, json=QUALITY_PROFILES_RESPONSE)
        )

        result = await client.list_quality_profiles()
        assert len(result) == 1
        assert result[0]["name"] == "HD-1080p"
        assert result[0]["id"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_movies(self, client):
        """Test listing movies."""
        respx.get("http://localhost:7878/movie").mock(
            return_value=httpx.Response(200, json=MOVIE_LIST_RESPONSE)
        )

        result = await client.list_movies()
        assert len(result) == 1
        assert result[0]["title"] == "The Matrix"
        assert result[0]["tmdbId"] == 603

    @pytest.mark.asyncio
    @respx.mock
    async def test_ensure_movie_success_first_try(self, client):
        """Test ensure_movie succeeds on first attempt."""
        payload = {"tmdbId": 693134, "title": "Dune: Part Two"}

        respx.post("http://localhost:7878/movie").mock(
            return_value=httpx.Response(201, json=ADD_MOVIE_SUCCESS_RESPONSE)
        )

        result = await client.ensure_movie(payload)
        assert result["title"] == "Dune: Part Two"

    @pytest.mark.asyncio
    @respx.mock
    async def test_ensure_movie_retry_on_http_error(self, client):
        """Test ensure_movie retries on HTTP errors."""
        payload = {"tmdbId": 693134, "title": "Dune: Part Two"}

        # First two attempts fail, third succeeds
        respx.post("http://localhost:7878/movie").mock(
            side_effect=[
                httpx.Response(500, json={"error": "Internal Server Error"}),
                httpx.Response(502, json={"error": "Bad Gateway"}),
                httpx.Response(201, json=ADD_MOVIE_SUCCESS_RESPONSE),
            ]
        )

        result = await client.ensure_movie(payload)
        assert result["title"] == "Dune: Part Two"

    @pytest.mark.asyncio
    @respx.mock
    async def test_ensure_movie_fails_after_retries(self, client):
        """Test ensure_movie fails after all retries exhausted."""
        payload = {"tmdbId": 693134, "title": "Dune: Part Two"}

        # All attempts fail
        respx.post("http://localhost:7878/movie").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        with pytest.raises(httpx.HTTPStatusError, match="500 Internal Server Error"):
            await client.ensure_movie(payload)

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test RadarrClient as async context manager."""
        async with RadarrClient("http://localhost:7878", "test-key") as client:
            assert isinstance(client, RadarrClient)
            assert client._client is not None

        # Client should be closed after context exit
        assert client._client.is_closed

    @pytest.mark.asyncio
    async def test_radarr_client_context_manager(self):
        """Test radarr_client convenience function."""
        async with radarr_client("http://localhost:7878", "test-key") as client:
            assert isinstance(client, RadarrClient)
            assert client._client is not None


class TestBuildAddMoviePayload:
    """Test cases for build_add_movie_payload function."""

    def test_build_basic_payload(self):
        """Test building basic movie payload."""
        lookup = {
            "tmdbId": 693134,
            "title": "Dune: Part Two",
            "titleSlug": "dune-part-two-693134",
            "year": 2024,
        }

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
        )

        expected = {
            "tmdbId": 693134,
            "title": "Dune: Part Two",
            "qualityProfileId": 1,
            "titleSlug": "dune-part-two-693134",
            "year": 2024,
            "monitored": True,
            "rootFolderPath": "/data/movies",
            "addOptions": {
                "searchForMovie": False,
                "monitor": True,
            },
        }

        assert payload == expected

    def test_build_payload_with_minimum_availability(self):
        """Test building payload with minimum availability."""
        lookup = {"tmdbId": 123, "title": "Test Movie", "titleSlug": "test-movie", "year": 2024}

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=False,
            minimum_availability="announced",
        )

        assert payload["minimumAvailability"] == "announced"
        assert payload["monitored"] is False
        assert payload["addOptions"]["monitor"] == False

    def test_build_payload_with_numeric_tags(self):
        """Test building payload with numeric tags."""
        lookup = {"tmdbId": 123, "title": "Test Movie", "titleSlug": "test-movie", "year": 2024}

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
            tags=["1", "2", "3"],
        )

        assert payload["tags"] == [1, 2, 3]

    def test_build_payload_with_invalid_tags(self):
        """Test building payload with invalid tags (non-numeric)."""
        lookup = {"tmdbId": 123, "title": "Test Movie", "titleSlug": "test-movie", "year": 2024}

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
            tags=["invalid", "not-a-number", "1", "2"],
        )

        # Only numeric tags should be included
        assert payload["tags"] == [1, 2]

    def test_build_payload_with_mixed_valid_invalid_tags(self):
        """Test building payload with mix of valid and invalid tags."""
        lookup = {"tmdbId": 123, "title": "Test Movie", "titleSlug": "test-movie", "year": 2024}

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
            tags=["tag1", "123", "invalid", "456"],
        )

        assert payload["tags"] == [123, 456]

    def test_build_payload_no_tags(self):
        """Test building payload without tags."""
        lookup = {"tmdbId": 123, "title": "Test Movie", "titleSlug": "test-movie", "year": 2024}

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
        )

        assert "tags" not in payload

    def test_build_payload_empty_tags(self):
        """Test building payload with empty tags list."""
        lookup = {"tmdbId": 123, "title": "Test Movie", "titleSlug": "test-movie", "year": 2024}

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
            tags=[],
        )

        assert "tags" not in payload

    def test_build_payload_handles_missing_lookup_fields(self):
        """Test payload building with missing optional lookup fields."""
        lookup = {"tmdbId": 123}  # Minimal lookup data

        payload = build_add_movie_payload(
            lookup=lookup,
            quality_profile_id=1,
            root_folder_path="/data/movies",
            monitor=True,
        )

        assert payload["tmdbId"] == 123
        assert payload["title"] is None
        assert payload["titleSlug"] is None
        assert payload["year"] is None


@pytest.mark.integration
class TestRadarrClientIntegration:
    """Integration tests for RadarrClient that require live Radarr instance."""

    @pytest.mark.asyncio
    async def test_real_radarr_connection(self):
        """Test connection to real Radarr instance if configured."""
        import os

        api_key = os.getenv("RADARR_API_KEY")
        base_url = os.getenv("RADARR_BASE_URL", "http://localhost:7878")

        if not api_key:
            pytest.skip("RADARR_API_KEY not set, skipping integration test")

        async with RadarrClient(base_url, api_key) as client:
            # Test basic connectivity
            status = await client.ping()
            assert "appName" in status
            assert status["appName"] == "Radarr"

            # Test listing endpoints that don't modify data
            root_folders = await client.list_root_folders()
            assert isinstance(root_folders, list)

            profiles = await client.list_quality_profiles()
            assert isinstance(profiles, list)
            assert len(profiles) > 0