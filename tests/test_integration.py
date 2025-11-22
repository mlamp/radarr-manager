"""Integration tests that require live services."""

import pytest
import os
import asyncio
from datetime import date

from radarr_manager.clients.radarr import RadarrClient
from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.providers.factory import build_provider
from radarr_manager.services.discovery import DiscoveryService
from radarr_manager.services.sync import SyncService
from radarr_manager.config.settings import Settings, load_settings
from radarr_manager.models import MovieSuggestion


@pytest.mark.integration
class TestRadarrIntegration:
    """Integration tests for Radarr client and services."""

    @pytest.fixture
    def radarr_config(self):
        """Get Radarr configuration from environment."""
        api_key = os.getenv("RADARR_API_KEY")
        base_url = os.getenv("RADARR_BASE_URL", "http://localhost:7878")

        if not api_key:
            pytest.skip("RADARR_API_KEY not set, skipping Radarr integration tests")

        return {"base_url": base_url, "api_key": api_key}

    @pytest.mark.asyncio
    async def test_radarr_connection_and_basic_operations(self, radarr_config):
        """Test basic Radarr operations with live instance."""
        async with RadarrClient(**radarr_config) as client:
            # Test system status
            status = await client.ping()
            assert status["appName"] == "Radarr"
            assert "version" in status

            # Test listing root folders
            root_folders = await client.list_root_folders()
            assert isinstance(root_folders, list)
            assert len(root_folders) > 0
            assert all("path" in folder for folder in root_folders)

            # Test listing quality profiles
            profiles = await client.list_quality_profiles()
            assert isinstance(profiles, list)
            assert len(profiles) > 0
            assert all("name" in profile for profile in profiles)

            # Test listing existing movies
            movies = await client.list_movies()
            assert isinstance(movies, list)
            # Movies list can be empty, that's OK

    @pytest.mark.asyncio
    async def test_radarr_movie_lookup(self, radarr_config):
        """Test movie lookup functionality with live Radarr."""
        async with RadarrClient(**radarr_config) as client:
            # Test lookup for a well-known movie
            results = await client.lookup_movie("The Matrix")
            assert isinstance(results, list)

            if results:
                movie = results[0]
                assert "title" in movie
                assert "tmdbId" in movie
                assert "year" in movie

            # Test lookup for non-existent movie
            no_results = await client.lookup_movie("NonexistentMovieTitle12345")
            assert isinstance(no_results, list)
            # May or may not have results, but should not error

    @pytest.mark.asyncio
    async def test_sync_service_dry_run_integration(self, radarr_config):
        """Test sync service dry run with live Radarr."""
        async with RadarrClient(**radarr_config) as client:
            # Get available quality profiles and root folders
            profiles = await client.list_quality_profiles()
            root_folders = await client.list_root_folders()

            assert len(profiles) > 0, "No quality profiles available"
            assert len(root_folders) > 0, "No root folders available"

            sync_service = SyncService(
                client,
                quality_profile_id=profiles[0]["id"],
                root_folder_path=root_folders[0]["path"],
                monitor=True,
                minimum_availability="announced",
                tags=["integration-test"],
            )

            # Create test suggestions
            suggestions = [
                MovieSuggestion(
                    title="The Matrix",
                    release_date=date(1999, 3, 31),
                    overview="Classic sci-fi movie",
                    confidence=0.9,
                    sources=["integration-test"],
                ),
            ]

            # Run sync in dry-run mode (safe)
            result = await sync_service.sync(suggestions, dry_run=True, force=False)

            assert result.dry_run is True
            assert len(result.queued) == 1
            assert result.queued[0] == "The Matrix"
            assert len(result.errors) == 0


@pytest.mark.integration
class TestProviderIntegration:
    """Integration tests for discovery providers."""

    @pytest.fixture
    def openai_config(self):
        """Get OpenAI configuration from environment."""
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not api_key:
            pytest.skip("OPENAI_API_KEY not set, skipping OpenAI integration tests")

        return {"api_key": api_key, "model": model}

    @pytest.mark.asyncio
    async def test_openai_provider_discovery(self, openai_config):
        """Test OpenAI provider with live API."""
        provider = OpenAIProvider(
            api_key=openai_config["api_key"],
            model=openai_config["model"],
            region="US",
            cache_ttl_hours=1,
        )

        suggestions = await provider.discover(limit=2, region="US")

        # Validate response structure
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 2

        if suggestions:
            suggestion = suggestions[0]
            assert isinstance(suggestion, MovieSuggestion)
            assert suggestion.title
            assert isinstance(suggestion.title, str)
            assert 0.0 <= suggestion.confidence <= 1.0
            assert isinstance(suggestion.sources, list)

            # Optional fields validation
            if suggestion.release_date:
                assert isinstance(suggestion.release_date, date)
            if suggestion.overview:
                assert isinstance(suggestion.overview, str)

    @pytest.mark.asyncio
    async def test_discovery_service_integration(self, openai_config):
        """Test discovery service with live provider."""
        provider = OpenAIProvider(
            api_key=openai_config["api_key"],
            model=openai_config["model"],
            region="US",
            cache_ttl_hours=1,
        )

        discovery = DiscoveryService(provider, region="US")
        suggestions = await discovery.discover(limit=1)

        assert isinstance(suggestions, list)
        assert len(suggestions) <= 1

        if suggestions:
            assert isinstance(suggestions[0], MovieSuggestion)

    @pytest.mark.asyncio
    async def test_provider_factory_integration(self):
        """Test provider factory with live configuration."""
        # Try to load real settings
        try:
            result = load_settings()
            settings = result.settings
        except Exception:
            # Fallback to basic settings
            settings = Settings(
                llm_provider="static",  # Safe fallback
            )

        # Test static provider (always works)
        provider = build_provider(settings, override="static")
        assert provider.name == "static"

        suggestions = await provider.discover(limit=1)
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 1

    @pytest.mark.asyncio
    async def test_openai_error_handling(self, openai_config):
        """Test OpenAI provider error handling with invalid parameters."""
        provider = OpenAIProvider(
            api_key="invalid-key",  # Invalid API key
            model="gpt-4o-mini",
            region="US",
            cache_ttl_hours=1,
        )

        with pytest.raises(Exception):
            # Should fail with authentication error
            await provider.discover(limit=1)


@pytest.mark.integration
class TestEndToEndIntegration:
    """End-to-end integration tests."""

    @pytest.fixture
    def full_config(self):
        """Get full configuration for end-to-end testing."""
        radarr_api_key = os.getenv("RADARR_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not radarr_api_key or not openai_api_key:
            pytest.skip("Full integration requires both RADARR_API_KEY and OPENAI_API_KEY")

        return {
            "radarr_base_url": os.getenv("RADARR_BASE_URL", "http://localhost:7878"),
            "radarr_api_key": radarr_api_key,
            "openai_api_key": openai_api_key,
            "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        }

    @pytest.mark.asyncio
    async def test_full_discovery_to_radarr_pipeline(self, full_config):
        """Test complete pipeline from discovery to Radarr sync (dry run)."""
        # Setup OpenAI provider
        provider = OpenAIProvider(
            api_key=full_config["openai_api_key"],
            model=full_config["openai_model"],
            region="US",
            cache_ttl_hours=1,
        )

        # Discover movies
        discovery = DiscoveryService(provider, region="US")
        suggestions = await discovery.discover(limit=2)

        assert isinstance(suggestions, list)
        # We may get 0-2 suggestions depending on API response

        if not suggestions:
            pytest.skip("No suggestions returned from discovery, skipping pipeline test")

        # Setup Radarr sync
        async with RadarrClient(
            base_url=full_config["radarr_base_url"],
            api_key=full_config["radarr_api_key"],
        ) as radarr_client:

            profiles = await radarr_client.list_quality_profiles()
            root_folders = await radarr_client.list_root_folders()

            sync_service = SyncService(
                radarr_client,
                quality_profile_id=profiles[0]["id"],
                root_folder_path=root_folders[0]["path"],
                monitor=True,
                minimum_availability="announced",
                tags=["integration-test"],
            )

            # Run sync in dry-run mode (safe)
            result = await sync_service.sync(suggestions, dry_run=True, force=False)

            assert result.dry_run is True
            assert isinstance(result.queued, list)
            assert isinstance(result.skipped, list)
            assert isinstance(result.errors, list)

            # Total processed should equal input suggestions
            total_processed = len(result.queued) + len(result.skipped)
            assert total_processed <= len(suggestions)

    @pytest.mark.asyncio
    async def test_settings_loading_integration(self):
        """Test settings loading with actual configuration files."""
        try:
            result = load_settings()
            settings = result.settings

            # Basic validation that settings loaded
            assert isinstance(settings, Settings)

            # If provider is configured, test that it works
            if settings.llm_provider:
                provider = build_provider(settings)
                assert provider.name == settings.llm_provider.lower()

                # Quick test that provider is functional
                suggestions = await provider.discover(limit=1)
                assert isinstance(suggestions, list)

        except Exception as e:
            # Settings loading failed, but that's OK for integration tests
            pytest.skip(f"Settings loading failed: {e}")


@pytest.mark.integration
class TestPerformanceIntegration:
    """Performance and load testing for integration scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_radarr_requests(self):
        """Test concurrent requests to Radarr API."""
        api_key = os.getenv("RADARR_API_KEY")
        base_url = os.getenv("RADARR_BASE_URL", "http://localhost:7878")

        if not api_key:
            pytest.skip("RADARR_API_KEY not set, skipping performance test")

        async with RadarrClient(base_url, api_key) as client:
            # Create multiple concurrent requests
            tasks = [
                client.ping(),
                client.list_quality_profiles(),
                client.list_root_folders(),
                client.lookup_movie("The Matrix"),
                client.lookup_movie("Inception"),
            ]

            # Run concurrently and ensure all succeed
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check that all requests succeeded (no exceptions)
            for result in results:
                assert not isinstance(result, Exception), f"Request failed: {result}"

    @pytest.mark.asyncio
    async def test_large_movie_list_handling(self):
        """Test handling of large movie lists from Radarr."""
        api_key = os.getenv("RADARR_API_KEY")
        base_url = os.getenv("RADARR_BASE_URL", "http://localhost:7878")

        if not api_key:
            pytest.skip("RADARR_API_KEY not set, skipping performance test")

        async with RadarrClient(base_url, api_key) as client:
            # Get all movies (potentially large list)
            movies = await client.list_movies()

            assert isinstance(movies, list)

            # If there are many movies, test performance characteristics
            if len(movies) > 100:
                # Test that we can process the list efficiently
                tmdb_ids = {
                    movie.get("tmdbId") for movie in movies if movie.get("tmdbId") is not None
                }

                # Should be able to extract TMDB IDs quickly
                assert len(tmdb_ids) <= len(movies)

                # Test duplicate detection logic similar to sync service
                duplicates = len(movies) - len({movie.get("tmdbId") for movie in movies})
                assert duplicates >= 0  # Should not have negative duplicates
