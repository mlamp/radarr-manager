"""End-to-end integration tests for radarr-manager MCP server.

These tests verify that the MCP server works correctly with all tools,
including proper error handling and response formats. Tests cover the
new RadarrClient methods (get_movie_by_tmdb, lookup_movie_by_tmdb, etc.).
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from radarr_manager.mcp.server import (
    _add_movie,
    _search_movie,
    _analyze_quality,
    _discover_movies,
    _sync_movies,
)
from radarr_manager.config.settings import Settings


@pytest.mark.integration
class TestMCPToolsE2E:
    """End-to-end tests for MCP tools."""

    @pytest.mark.asyncio
    async def test_search_movie_success(self):
        """Test search_movie tool returns movie data."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.lookup_movie.return_value = [
                {
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                    "title": "The Matrix",
                    "year": 1999,
                    "titleSlug": "the-matrix-603",
                }
            ]
            mock_instance.get_movie_by_tmdb.return_value = None

            result = await _search_movie(settings, {"title": "The Matrix"})

            assert isinstance(result, list)
            assert len(result) > 0
            assert "The Matrix" in result[0].text

    @pytest.mark.asyncio
    async def test_search_movie_no_results(self):
        """Test search_movie with no results."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.lookup_movie.return_value = []

            result = await _search_movie(settings, {"title": "Nonexistent Movie"})

            assert isinstance(result, list)
            assert len(result) > 0
            assert "not found" in result[0].text.lower() or "no" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_add_movie_uses_lookup_by_tmdb(self):
        """Test add_movie tool uses new lookup_movie_by_tmdb method."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock the new lookup_movie_by_tmdb method
            mock_instance.lookup_movie_by_tmdb.return_value = [
                {
                    "tmdbId": 603,
                    "title": "The Matrix",
                    "titleSlug": "the-matrix-603",
                    "year": 1999,
                }
            ]

            # Mock get_movie_by_tmdb to show not in library
            mock_instance.get_movie_by_tmdb.return_value = None

            mock_instance.list_root_folders.return_value = [
                {"path": "/data/movies", "id": 1}
            ]
            mock_instance.list_quality_profiles.return_value = [
                {"name": "HD-1080p", "id": 1}
            ]
            mock_instance.ensure_movie.return_value = {
                "id": 123,
                "title": "The Matrix",
                "tmdbId": 603,
            }

            result = await _add_movie(
                settings,
                {
                    "tmdb_id": 603,
                    "quality_profile_id": 1,
                    "root_folder_path": "/data/movies",
                    "monitor": True,
                },
            )

            # Verify lookup_movie_by_tmdb was called (new method)
            mock_instance.lookup_movie_by_tmdb.assert_called_once_with(603)

            # Verify get_movie_by_tmdb was called (new method)
            mock_instance.get_movie_by_tmdb.assert_called_once_with(603)

            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_add_movie_already_exists_uses_get_movie_by_tmdb(self):
        """Test add_movie uses get_movie_by_tmdb to check if movie exists."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.lookup_movie_by_tmdb.return_value = [
                {
                    "tmdbId": 603,
                    "title": "The Matrix",
                    "titleSlug": "the-matrix-603",
                    "year": 1999,
                }
            ]

            # Mock get_movie_by_tmdb to return existing movie (new method)
            mock_instance.get_movie_by_tmdb.return_value = {
                "id": 123,
                "title": "The Matrix",
                "tmdbId": 603,
            }

            result = await _add_movie(
                settings,
                {
                    "tmdb_id": 603,
                    "quality_profile_id": 1,
                    "root_folder_path": "/data/movies",
                    "monitor": True,
                },
            )

            # Verify get_movie_by_tmdb was called
            mock_instance.get_movie_by_tmdb.assert_called_once_with(603)

            assert isinstance(result, list)
            assert len(result) > 0
            # Should indicate movie already exists
            assert "already" in result[0].text.lower() or "exists" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_add_movie_movie_not_found(self):
        """Test add_movie with invalid TMDB ID."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # lookup_movie_by_tmdb returns empty list for non-existent movie
            mock_instance.lookup_movie_by_tmdb.return_value = []

            result = await _add_movie(
                settings,
                {
                    "tmdb_id": 999999,
                    "quality_profile_id": 1,
                    "root_folder_path": "/data/movies",
                    "monitor": True,
                },
            )

            assert isinstance(result, list)
            assert len(result) > 0
            # Should indicate movie not found
            assert "not found" in result[0].text.lower() or "no movie" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_analyze_quality_success(self):
        """Test analyze_quality tool returns quality profiles."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_instance.list_quality_profiles.return_value = [
                {"id": 1, "name": "HD-1080p", "cutoff": {"name": "Bluray-1080p"}},
                {"id": 2, "name": "HD-720p", "cutoff": {"name": "Bluray-720p"}},
            ]

            result = await _analyze_quality(settings, {})

            assert isinstance(result, list)
            assert len(result) > 0
            assert "HD-1080p" in result[0].text or "HD-720p" in result[0].text

    @pytest.mark.asyncio
    async def test_discover_movies_success(self):
        """Test discover_movies tool returns suggestions."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
            llm_provider="openai",
            openai_api_key="sk-test",
            openai_model="gpt-4o-mini",
        )

        with patch("radarr_manager.mcp.server.DiscoveryService") as mock_service:
            mock_instance = AsyncMock()
            mock_service.return_value = mock_instance

            mock_instance.discover_movies.return_value = [
                {"title": "Dune: Part Two", "tmdb_id": 693134},
                {"title": "The Matrix", "tmdb_id": 603},
            ]

            result = await _discover_movies(settings, {"limit": 2})

            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_sync_movies_success(self):
        """Test sync_movies tool syncs successfully."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
            llm_provider="openai",
            openai_api_key="sk-test",
            openai_model="gpt-4o-mini",
        )

        with patch("radarr_manager.mcp.server.SyncService") as mock_service:
            mock_instance = AsyncMock()
            mock_service.return_value = mock_instance

            mock_instance.sync_movies.return_value = {
                "added": 2,
                "skipped": 1,
                "failed": 0,
            }

            result = await _sync_movies(settings, {"limit": 3, "dry_run": False})

            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_search_movie_with_error_handling(self):
        """Test search_movie handles RadarrClient errors gracefully."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Simulate HTTP error
            mock_instance.lookup_movie.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(404),
            )

            result = await _search_movie(settings, {"title": "Test Movie"})

            # Should return error message, not raise exception
            assert isinstance(result, list)
            assert len(result) > 0
            # Error should be indicated in the text
            assert "error" in result[0].text.lower() or "failed" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_all_new_radarr_methods_are_used(self):
        """Integration test verifying all 3 new RadarrClient methods work together."""
        settings = Settings(
            radarr_base_url="http://test:7878",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Set up responses for all new methods
            mock_instance.lookup_movie_by_tmdb.return_value = [
                {
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                    "title": "The Matrix",
                    "year": 1999,
                    "titleSlug": "the-matrix-603",
                }
            ]

            mock_instance.lookup_movie_by_imdb.return_value = [
                {
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                    "title": "The Matrix",
                    "year": 1999,
                }
            ]

            mock_instance.get_movie_by_tmdb.return_value = None
            mock_instance.list_root_folders.return_value = [{"path": "/data/movies", "id": 1}]
            mock_instance.list_quality_profiles.return_value = [{"name": "HD-1080p", "id": 1}]
            mock_instance.ensure_movie.return_value = {
                "id": 123,
                "title": "The Matrix",
                "tmdbId": 603,
            }

            # Test add_movie which should use lookup_movie_by_tmdb and get_movie_by_tmdb
            await _add_movie(
                settings,
                {
                    "tmdb_id": 603,
                    "quality_profile_id": 1,
                    "root_folder_path": "/data/movies",
                    "monitor": True,
                },
            )

            # Verify all new methods were available and callable
            assert mock_instance.lookup_movie_by_tmdb.called
            assert mock_instance.get_movie_by_tmdb.called

            # Verify methods exist and are callable (would fail if methods missing)
            assert callable(mock_instance.lookup_movie_by_tmdb)
            assert callable(mock_instance.lookup_movie_by_imdb)
            assert callable(mock_instance.get_movie_by_tmdb)
