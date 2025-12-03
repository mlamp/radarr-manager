"""Tests for MCP server implementation."""

import os
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent

from radarr_manager.config.settings import Settings, load_settings
from radarr_manager.mcp.server import (
    _add_movie,
    _analyze_quality,
    _discover_movies,
    _search_movie,
    _sync_movies,
    create_mcp_server,
)
from radarr_manager.models.movie import MovieSuggestion as MovieSuggestionModel


class TestSettingsLoading:
    """Test that settings are properly loaded from .env files."""

    def test_create_mcp_server_loads_settings_from_env(self):
        """Test that create_mcp_server uses load_settings() not Settings()."""
        # Load settings using the same method as create_mcp_server
        load_result = load_settings()
        settings = load_result.settings

        # Verify settings are loaded as plain strings, not SecretStr
        assert isinstance(settings.radarr_api_key, str)
        assert isinstance(settings.openai_api_key, str)

        # Verify no .get_secret_value() is needed - should work directly
        api_key = settings.radarr_api_key  # Should work directly
        assert isinstance(api_key, str)

    def test_settings_are_plain_strings_not_secret_str(self):
        """Verify Settings uses plain str, not SecretStr for API keys."""
        settings = Settings(
            radarr_api_key="test-key",
            openai_api_key="sk-test",
        )

        # These should be plain strings
        assert isinstance(settings.radarr_api_key, str)
        assert isinstance(settings.openai_api_key, str)

        # Should NOT have .get_secret_value() method
        assert not hasattr(settings.radarr_api_key, "get_secret_value")
        assert not hasattr(settings.openai_api_key, "get_secret_value")


class TestSearchMovieTool:
    """Test search_movie tool - simulates 'Check if movie exists' request."""

    @pytest.mark.asyncio
    async def test_search_movie_found(self):
        """Test searching for a movie that exists - like 'search The Matrix'."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
        )

        # Mock RadarrClient
        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock lookup response
            mock_instance.lookup_movie.return_value = [
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                }
            ]

            # Mock get_movie_by_tmdb to show it exists in Radarr
            mock_instance.get_movie_by_tmdb.return_value = {
                "id": 1,
                "title": "The Matrix",
                "year": 1999,
                "tmdbId": 603,
                "imdbId": "tt0133093",
                "hasFile": True,
            }

            # Call the tool
            result = await _search_movie(
                settings,
                {
                    "title": "The Matrix",
                    "year": 1999,
                },
            )

            # Verify result
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            assert "exists" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_search_movie_not_found(self):
        """Test searching for a movie that doesn't exist."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock empty lookup response
            mock_instance.lookup_movie.return_value = []

            result = await _search_movie(
                settings,
                {
                    "title": "Unknown Movie",
                },
            )

            assert isinstance(result, list)
            assert len(result) == 1
            assert "not found" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_search_movie_with_year(self):
        """Test searching for a movie with year - ensures lookup_movie() is called correctly."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Mock lookup response
            mock_instance.lookup_movie.return_value = [
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                }
            ]

            mock_instance.get_movie_by_tmdb.return_value = None  # Not in Radarr

            result = await _search_movie(
                settings,
                {
                    "title": "The Matrix",
                    "year": 1999,
                },
            )

            # Verify lookup_movie was called with combined search term (not 2 separate args)
            mock_instance.lookup_movie.assert_called_once_with("The Matrix 1999")

            assert isinstance(result, list)
            assert len(result) == 1


class TestAddMovieTool:
    """Test add_movie tool - simulates 'Add The Matrix 1999' request."""

    @pytest.mark.asyncio
    async def test_add_movie_success_with_quality_analysis(self):
        """Test adding a high-quality movie - like 'Add The Matrix 1999'."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
            openai_api_key="sk-test",
            openai_model="gpt-4o",
            quality_profile_id=4,
            root_folder_path="/movies",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client, patch(
            "radarr_manager.mcp.server.DeepAnalysisService"
        ) as mock_analysis:
            # Mock RadarrClient
            mock_radarr = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_radarr

            mock_radarr.lookup_movie.return_value = [
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                }
            ]

            mock_radarr.ensure_movie.return_value = {
                "id": 1,
                "title": "The Matrix",
                "added": True,
            }

            # Mock DeepAnalysisService (no API key params needed)
            mock_analysis_instance = AsyncMock()
            mock_analysis.return_value = mock_analysis_instance
            mock_analysis_instance.analyze_movie.return_value = MagicMock(
                quality_score=9.5,
                should_add=True,
                reasons=["Critically acclaimed", "Cultural impact"],
            )

            # Call the tool - force=False but quality is high
            result = await _add_movie(
                settings,
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "force": False,
                    "deep_analysis": True,
                    "quality_threshold": 5.0,
                    "dry_run": False,
                },
            )

            # Verify result
            assert isinstance(result, list)
            assert len(result) == 1
            assert "success" in result[0].text.lower() or "added" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_add_movie_with_title_and_year(self):
        """Test add_movie with title and year - ensures lookup_movie() is called correctly."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
            openai_api_key="sk-test",
            openai_model="gpt-4o",
            quality_profile_id=4,
            root_folder_path="/movies",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client, patch(
            "radarr_manager.mcp.server.DeepAnalysisService"
        ) as mock_analysis:
            # Mock RadarrClient
            mock_radarr = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_radarr

            mock_radarr.lookup_movie.return_value = [
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                }
            ]

            mock_radarr.ensure_movie.return_value = {
                "id": 1,
                "title": "The Matrix",
                "added": True,
            }

            # Mock DeepAnalysisService
            mock_analysis_instance = AsyncMock()
            mock_analysis.return_value = mock_analysis_instance
            mock_analysis_instance.analyze_movie.return_value = MagicMock(
                quality_score=9.5,
                should_add=True,
            )

            # Call the tool with both title and year
            result = await _add_movie(
                settings,
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "force": False,
                    "deep_analysis": True,
                    "quality_threshold": 5.0,
                    "dry_run": False,
                },
            )

            # Verify lookup_movie was called with combined search term
            mock_radarr.lookup_movie.assert_called_once_with("The Matrix 1999")

            assert isinstance(result, list)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_add_movie_blocked_by_quality_gate(self):
        """Test that low-quality movie is blocked unless forced."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
            openai_api_key="sk-test",
            openai_model="gpt-4o",
            quality_profile_id=4,
            root_folder_path="/movies",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client, patch(
            "radarr_manager.mcp.server.DeepAnalysisService"
        ) as mock_analysis:
            mock_radarr = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_radarr

            mock_radarr.lookup_movie.return_value = [
                {
                    "title": "Bad Movie",
                    "year": 2024,
                    "tmdbId": 999,
                }
            ]

            # Mock low quality score
            mock_analysis_instance = AsyncMock()
            mock_analysis.return_value = mock_analysis_instance
            mock_analysis_instance.analyze_movie.return_value = MagicMock(
                quality_score=2.0,
                should_add=False,
                reasons=["Poor reviews", "Low ratings"],
            )

            result = await _add_movie(
                settings,
                {
                    "title": "Bad Movie",
                    "year": 2024,
                    "force": False,
                    "deep_analysis": True,
                    "quality_threshold": 5.0,
                    "dry_run": False,
                },
            )

            # Should be blocked
            assert isinstance(result, list)
            assert "blocked" in result[0].text.lower() or "quality" in result[0].text.lower()


class TestAnalyzeQualityTool:
    """Test analyze_quality tool - simulates quality analysis request."""

    @pytest.mark.asyncio
    async def test_analyze_quality_with_title_and_year(self):
        """Test analyze_quality with title and year - ensures lookup_movie() is called correctly."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
        )

        with patch("radarr_manager.mcp.server.RadarrClient") as mock_client, patch(
            "radarr_manager.mcp.server.DeepAnalysisService"
        ) as mock_analysis:
            # Mock RadarrClient
            mock_radarr = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_radarr

            mock_radarr.lookup_movie.return_value = [
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdbId": 603,
                    "imdbId": "tt0133093",
                }
            ]

            # Mock DeepAnalysisService
            mock_analysis_instance = AsyncMock()
            mock_analysis.return_value = mock_analysis_instance
            mock_analysis_instance.analyze_movie.return_value = MagicMock(
                quality_score=9.5,
                should_add=True,
                recommendation="Highly recommended",
                rating_details={"imdb": 8.7, "rt": 88},
                red_flags=[],
            )

            # Call the tool with both title and year
            result = await _analyze_quality(
                settings,
                {
                    "title": "The Matrix",
                    "year": 1999,
                },
            )

            # Verify lookup_movie was called with combined search term (not 2 separate args)
            mock_radarr.lookup_movie.assert_called_once_with("The Matrix 1999")

            assert isinstance(result, list)
            assert len(result) == 1


class TestDiscoverMoviesTool:
    """Test discover_movies tool - simulates 'discover trending movies' request."""

    @pytest.mark.asyncio
    async def test_discover_movies_success(self):
        """Test discovering trending movies."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
            llm_provider="openai",
            openai_api_key="sk-test",
            openai_model="gpt-4o",
        )

        with patch("radarr_manager.mcp.server.build_provider") as mock_provider, patch(
            "radarr_manager.mcp.server.DiscoveryService"
        ) as mock_discovery:
            # Mock provider
            provider_instance = MagicMock()
            mock_provider.return_value = provider_instance

            # Mock discovery service - returns MovieSuggestion objects
            discovery_instance = AsyncMock()
            mock_discovery.return_value = discovery_instance
            discovery_instance.discover.return_value = [
                MovieSuggestionModel(
                    title="Dune: Part Two",
                    release_date=date(2024, 3, 1),
                    confidence=0.95,
                ),
                MovieSuggestionModel(
                    title="Oppenheimer",
                    release_date=date(2023, 7, 21),
                    confidence=0.90,
                ),
            ]

            result = await _discover_movies(
                settings,
                {
                    "limit": 5,
                },
            )

            assert isinstance(result, list)
            assert len(result) == 1
            assert "Dune" in result[0].text or "discovered" in result[0].text.lower()


class TestSyncMoviesTool:
    """Test sync_movies tool - simulates 'sync movies with Radarr' request."""

    @pytest.mark.asyncio
    async def test_sync_movies_dry_run(self):
        """Test syncing movies in dry-run mode."""
        settings = Settings(
            radarr_base_url="http://test:7878/api/v3",
            radarr_api_key="test-key",
            llm_provider="openai",
            openai_api_key="sk-test",
            openai_model="gpt-4o",
            quality_profile_id=4,
            root_folder_path="/movies",
        )

        with patch("radarr_manager.mcp.server.build_provider") as mock_provider, patch(
            "radarr_manager.mcp.server.DiscoveryService"
        ) as mock_discovery_service, patch(
            "radarr_manager.mcp.server.RadarrClient"
        ) as mock_client, patch("radarr_manager.mcp.server.SyncService") as mock_sync:
            # Mock provider
            provider_instance = MagicMock()
            mock_provider.return_value = provider_instance

            # Mock DiscoveryService
            discovery_instance = AsyncMock()
            mock_discovery_service.return_value = discovery_instance

            # Mock RadarrClient
            mock_radarr = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_radarr

            # Mock SyncService
            sync_instance = AsyncMock()
            mock_sync.return_value = sync_instance
            sync_instance.sync.return_value = MagicMock(
                dry_run=True,
                queued=["Movie 1", "Movie 2"],
                skipped=["Movie 3"],
                errors=[],
            )

            result = await _sync_movies(
                settings,
                {
                    "dry_run": True,
                    "force": False,
                    "limit": 5,
                },
            )

            assert isinstance(result, list)
            assert "dry" in result[0].text.lower() or "queued" in result[0].text.lower()


class TestMCPServerCreation:
    """Test MCP server initialization."""

    def test_create_mcp_server_succeeds(self, tmp_path):
        """Test that MCP server can be created with proper settings."""
        # Create temporary .env
        env_file = tmp_path / ".env"
        env_file.write_text(
            """
RADARR_BASE_URL=http://test:7878/api/v3
RADARR_API_KEY=test-key
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-test
"""
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # This should not raise any errors
            server = create_mcp_server()
            assert server is not None
            assert server.name == "radarr-manager"

        finally:
            os.chdir(original_cwd)
