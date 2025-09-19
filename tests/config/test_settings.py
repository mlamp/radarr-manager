"""Tests for configuration and settings functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open
import pytest

from radarr_manager.config.settings import (
    Settings,
    SettingsError,
    SettingsLoadResult,
    load_settings,
    _determine_config_path,
    _flatten_toml,
    _collect_env_overrides,
)


class TestSettings:
    """Test Settings model functionality."""

    def test_settings_default_values(self):
        """Test Settings model with default values."""
        settings = Settings()

        assert settings.radarr_base_url is None
        assert settings.radarr_api_key is None
        assert settings.llm_provider is None
        assert settings.openai_api_key is None
        assert settings.openai_model == "gpt-4o-mini"
        assert settings.gemini_api_key is None
        assert settings.grok_api_key is None
        assert settings.quality_profile_id is None
        assert settings.root_folder_path is None
        assert settings.minimum_availability is None
        assert settings.monitor is True
        assert settings.tags == []
        assert settings.cache_ttl_hours == 6
        assert settings.region is None

    def test_settings_with_values(self):
        """Test Settings model with provided values."""
        settings = Settings(
            radarr_base_url="http://localhost:7878",
            radarr_api_key="test-key",
            llm_provider="openai",
            openai_api_key="openai-key",
            openai_model="gpt-4",
            quality_profile_id=1,
            root_folder_path="/data/movies",
            minimum_availability="released",
            monitor=False,
            tags=["tag1", "tag2"],
            cache_ttl_hours=12,
            region="EU",
        )

        assert settings.radarr_base_url == "http://localhost:7878"
        assert settings.radarr_api_key == "test-key"
        assert settings.llm_provider == "openai"
        assert settings.openai_api_key == "openai-key"
        assert settings.openai_model == "gpt-4"
        assert settings.quality_profile_id == 1
        assert settings.root_folder_path == "/data/movies"
        assert settings.minimum_availability == "released"
        assert settings.monitor is False
        assert settings.tags == ["tag1", "tag2"]
        assert settings.cache_ttl_hours == 12
        assert settings.region == "EU"

    def test_settings_with_aliases(self):
        """Test Settings model using environment variable aliases."""
        settings = Settings(
            RADARR_BASE_URL="http://radarr:7878",
            RADARR_API_KEY="radarr-key",
            LLM_PROVIDER="gemini",
            OPENAI_API_KEY="openai-key",
            RADARR_QUALITY_PROFILE_ID=5,
        )

        assert settings.radarr_base_url == "http://radarr:7878"
        assert settings.radarr_api_key == "radarr-key"
        assert settings.llm_provider == "gemini"
        assert settings.openai_api_key == "openai-key"
        assert settings.quality_profile_id == 5

    def test_settings_extra_fields_ignored(self):
        """Test that extra fields are ignored in Settings model."""
        settings = Settings(
            radarr_base_url="http://localhost:7878",
            unknown_field="should-be-ignored",
            another_unknown="also-ignored",
        )

        assert settings.radarr_base_url == "http://localhost:7878"
        assert not hasattr(settings, "unknown_field")
        assert not hasattr(settings, "another_unknown")

    def test_require_radarr_success(self):
        """Test require_radarr method with valid configuration."""
        settings = Settings(
            radarr_base_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        # Should not raise an exception
        settings.require_radarr()

    def test_require_radarr_missing_url(self):
        """Test require_radarr method with missing URL."""
        settings = Settings(radarr_api_key="test-key")

        with pytest.raises(SettingsError, match="Missing RADARR_BASE_URL or RADARR_API_KEY"):
            settings.require_radarr()

    def test_require_radarr_missing_api_key(self):
        """Test require_radarr method with missing API key."""
        settings = Settings(radarr_base_url="http://localhost:7878")

        with pytest.raises(SettingsError, match="Missing RADARR_BASE_URL or RADARR_API_KEY"):
            settings.require_radarr()

    def test_require_radarr_missing_both(self):
        """Test require_radarr method with both missing."""
        settings = Settings()

        with pytest.raises(SettingsError, match="Missing RADARR_BASE_URL or RADARR_API_KEY"):
            settings.require_radarr()


class TestDetermineConfigPath:
    """Test config path determination logic."""

    def test_determine_config_path_explicit(self):
        """Test explicit config path takes precedence."""
        explicit_path = Path("/custom/config.toml")
        result = _determine_config_path(explicit_path)
        assert result == explicit_path

    def test_determine_config_path_from_env(self):
        """Test config path from environment variable."""
        with patch.dict(os.environ, {"RADARR_MANAGER_CONFIG": "/env/config.toml"}):
            result = _determine_config_path(None)
            expected = Path("/env/config.toml").expanduser().resolve()
            assert result == expected

    def test_determine_config_path_default_exists(self):
        """Test default config path when file exists."""
        with patch("pathlib.Path.exists", return_value=True):
            result = _determine_config_path(None)
            expected = Path.home() / ".config" / "radarr-manager" / "config.toml"
            assert result == expected

    def test_determine_config_path_default_not_exists(self):
        """Test default config path when file does not exist."""
        with patch("pathlib.Path.exists", return_value=False):
            result = _determine_config_path(None)
            assert result is None

    def test_determine_config_path_env_with_tilde(self):
        """Test config path from environment with tilde expansion."""
        with patch.dict(os.environ, {"RADARR_MANAGER_CONFIG": "~/custom/config.toml"}):
            result = _determine_config_path(None)
            expected = Path("~/custom/config.toml").expanduser().resolve()
            assert result == expected


class TestFlattenToml:
    """Test TOML configuration flattening."""

    def test_flatten_toml_empty(self):
        """Test flattening empty TOML data."""
        result = _flatten_toml({})
        assert result == {}

    def test_flatten_toml_radarr_section(self):
        """Test flattening TOML with radarr section."""
        toml_data = {
            "radarr": {
                "base_url": "http://localhost:7878",
                "api_key": "test-key",
                "quality_profile_id": 1,
                "root_folder_path": "/data/movies",
                "minimum_availability": "announced",
                "monitor": True,
                "tags": ["tag1", "tag2"],
            }
        }

        result = _flatten_toml(toml_data)

        expected = {
            "radarr_base_url": "http://localhost:7878",
            "radarr_api_key": "test-key",
            "quality_profile_id": 1,
            "root_folder_path": "/data/movies",
            "minimum_availability": "announced",
            "monitor": True,
            "tags": ["tag1", "tag2"],
        }
        assert result == expected

    def test_flatten_toml_provider_section(self):
        """Test flattening TOML with provider section."""
        toml_data = {
            "provider": {
                "name": "openai",
                "cache_ttl_hours": 12,
                "region": "EU",
            }
        }

        result = _flatten_toml(toml_data)

        expected = {
            "llm_provider": "openai",
            "cache_ttl_hours": 12,
            "region": "EU",
        }
        assert result == expected

    def test_flatten_toml_providers_section(self):
        """Test flattening TOML with providers section."""
        toml_data = {
            "providers": {
                "openai": {
                    "api_key": "openai-key",
                    "model": "gpt-4",
                },
                "gemini": {
                    "api_key": "gemini-key",
                },
                "grok": {
                    "api_key": "grok-key",
                },
            }
        }

        result = _flatten_toml(toml_data)

        expected = {
            "openai_api_key": "openai-key",
            "openai_model": "gpt-4",
            "gemini_api_key": "gemini-key",
            "grok_api_key": "grok-key",
        }
        assert result == expected

    def test_flatten_toml_tags_as_string(self):
        """Test flattening TOML with tags as comma-separated string."""
        toml_data = {
            "radarr": {
                "tags": "tag1, tag2, tag3",
            }
        }

        result = _flatten_toml(toml_data)

        assert result["tags"] == ["tag1", "tag2", "tag3"]

    def test_flatten_toml_tags_with_empty_values(self):
        """Test flattening TOML with tags containing empty values."""
        toml_data = {
            "radarr": {
                "tags": "tag1, , tag2, ,tag3",
            }
        }

        result = _flatten_toml(toml_data)

        assert result["tags"] == ["tag1", "tag2", "tag3"]

    def test_flatten_toml_complex_structure(self):
        """Test flattening complex TOML structure."""
        toml_data = {
            "radarr": {
                "base_url": "http://radarr:7878",
                "quality_profile_id": 2,
            },
            "provider": {
                "name": "openai",
                "region": "US",
            },
            "providers": {
                "openai": {
                    "api_key": "openai-key",
                    "model": "gpt-4o",
                },
                "gemini": {
                    "api_key": "gemini-key",
                },
            },
            "ignored_section": {
                "some_field": "ignored",
            },
        }

        result = _flatten_toml(toml_data)

        expected = {
            "radarr_base_url": "http://radarr:7878",
            "quality_profile_id": 2,
            "llm_provider": "openai",
            "region": "US",
            "openai_api_key": "openai-key",
            "openai_model": "gpt-4o",
            "gemini_api_key": "gemini-key",
        }
        assert result == expected


class TestCollectEnvOverrides:
    """Test environment variable collection."""

    def test_collect_env_overrides_empty(self):
        """Test collecting env overrides with no relevant env vars."""
        with patch.dict(os.environ, {}, clear=True):
            result = _collect_env_overrides()
            assert result == {}

    def test_collect_env_overrides_string_values(self):
        """Test collecting string environment variables."""
        env_vars = {
            "RADARR_BASE_URL": "http://localhost:7878",
            "RADARR_API_KEY": "test-key",
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_MODEL": "gpt-4",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = _collect_env_overrides()

            expected = {
                "radarr_base_url": "http://localhost:7878",
                "radarr_api_key": "test-key",
                "llm_provider": "openai",
                "openai_api_key": "openai-key",
                "openai_model": "gpt-4",
            }
            assert result == expected

    def test_collect_env_overrides_integer_values(self):
        """Test collecting integer environment variables."""
        env_vars = {
            "RADARR_QUALITY_PROFILE_ID": "5",
            "RADARR_CACHE_TTL_HOURS": "24",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = _collect_env_overrides()

            expected = {
                "quality_profile_id": 5,
                "cache_ttl_hours": 24,
            }
            assert result == expected

    def test_collect_env_overrides_boolean_values(self):
        """Test collecting boolean environment variables."""
        test_cases = [
            ("true", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("anything-else", True),  # Default to True for non-false values
        ]

        for env_value, expected_bool in test_cases:
            with patch.dict(os.environ, {"RADARR_MONITOR": env_value}, clear=True):
                result = _collect_env_overrides()
                assert result["monitor"] == expected_bool

    def test_collect_env_overrides_tags_list(self):
        """Test collecting tags as comma-separated list."""
        env_vars = {
            "RADARR_TAGS": "tag1,tag2,tag3",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = _collect_env_overrides()

            assert result["tags"] == ["tag1", "tag2", "tag3"]

    def test_collect_env_overrides_tags_with_spaces(self):
        """Test collecting tags with spaces around commas."""
        env_vars = {
            "RADARR_TAGS": "tag1, tag2 , tag3,  tag4  ",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = _collect_env_overrides()

            assert result["tags"] == ["tag1", "tag2", "tag3", "tag4"]

    def test_collect_env_overrides_tags_empty_values(self):
        """Test collecting tags with empty values."""
        env_vars = {
            "RADARR_TAGS": "tag1,,tag2,,,tag3",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = _collect_env_overrides()

            assert result["tags"] == ["tag1", "tag2", "tag3"]

    def test_collect_env_overrides_mixed_types(self):
        """Test collecting mix of different types."""
        env_vars = {
            "RADARR_BASE_URL": "http://localhost:7878",
            "RADARR_QUALITY_PROFILE_ID": "3",
            "RADARR_MONITOR": "false",
            "RADARR_TAGS": "action, drama",
            "RADARR_CACHE_TTL_HOURS": "8",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = _collect_env_overrides()

            expected = {
                "radarr_base_url": "http://localhost:7878",
                "quality_profile_id": 3,
                "monitor": False,
                "tags": ["action", "drama"],
                "cache_ttl_hours": 8,
            }
            assert result == expected


class TestLoadSettings:
    """Test settings loading functionality."""

    def test_load_settings_from_env_only(self):
        """Test loading settings from environment variables only."""
        env_vars = {
            "RADARR_BASE_URL": "http://localhost:7878",
            "RADARR_API_KEY": "test-key",
            "LLM_PROVIDER": "openai",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch("radarr_manager.config.settings._determine_config_path", return_value=None):
                result = load_settings(load_env=False)

                assert isinstance(result, SettingsLoadResult)
                assert result.settings.radarr_base_url == "http://localhost:7878"
                assert result.settings.radarr_api_key == "test-key"
                assert result.settings.llm_provider == "openai"
                assert result.source_path is None

    def test_load_settings_from_toml_file(self):
        """Test loading settings from TOML configuration file."""
        toml_content = """
        [radarr]
        base_url = "http://radarr:7878"
        api_key = "toml-key"
        quality_profile_id = 2

        [provider]
        name = "gemini"
        region = "EU"
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            config_path = Path(f.name)

        try:
            with patch.dict(os.environ, {}, clear=True):
                result = load_settings(config_path=config_path, load_env=False)

                assert result.settings.radarr_base_url == "http://radarr:7878"
                assert result.settings.radarr_api_key == "toml-key"
                assert result.settings.quality_profile_id == 2
                assert result.settings.llm_provider == "gemini"
                assert result.settings.region == "EU"
                assert result.source_path == config_path
        finally:
            config_path.unlink()

    def test_load_settings_env_overrides_toml(self):
        """Test that environment variables override TOML configuration."""
        toml_content = """
        [radarr]
        base_url = "http://toml:7878"
        api_key = "toml-key"

        [provider]
        name = "static"
        """

        env_vars = {
            "RADARR_API_KEY": "env-key",  # Should override TOML
            "LLM_PROVIDER": "openai",     # Should override TOML
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            config_path = Path(f.name)

        try:
            with patch.dict(os.environ, env_vars, clear=True):
                result = load_settings(config_path=config_path, load_env=False)

                assert result.settings.radarr_base_url == "http://toml:7878"  # From TOML
                assert result.settings.radarr_api_key == "env-key"           # From env
                assert result.settings.llm_provider == "openai"             # From env
        finally:
            config_path.unlink()

    def test_load_settings_with_dotenv(self):
        """Test loading settings with .env file loading enabled."""
        with patch("radarr_manager.config.settings.load_dotenv") as mock_load_dotenv:
            with patch("radarr_manager.config.settings._determine_config_path", return_value=None):
                with patch.dict(os.environ, {}, clear=True):
                    load_settings(load_env=True)
                    mock_load_dotenv.assert_called_once()

    def test_load_settings_without_dotenv(self):
        """Test loading settings with .env file loading disabled."""
        with patch("radarr_manager.config.settings.load_dotenv") as mock_load_dotenv:
            with patch("radarr_manager.config.settings._determine_config_path", return_value=None):
                with patch.dict(os.environ, {}, clear=True):
                    load_settings(load_env=False)
                    mock_load_dotenv.assert_not_called()

    def test_load_settings_nonexistent_config_file(self):
        """Test loading settings with non-existent config file path."""
        nonexistent_path = Path("/nonexistent/config.toml")

        with patch.dict(os.environ, {}, clear=True):
            result = load_settings(config_path=nonexistent_path, load_env=False)

            # Should succeed with default settings since file doesn't exist
            assert isinstance(result.settings, Settings)
            assert result.source_path == nonexistent_path  # Returns the path even if it doesn't exist

    def test_load_settings_malformed_toml(self):
        """Test loading settings with malformed TOML file."""
        malformed_toml = """
        [radarr
        base_url = "missing bracket"
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(malformed_toml)
            config_path = Path(f.name)

        try:
            with patch.dict(os.environ, {}, clear=True):
                # Should raise an exception due to malformed TOML
                with pytest.raises(Exception):  # tomllib will raise a parsing error
                    load_settings(config_path=config_path, load_env=False)
        finally:
            config_path.unlink()


@pytest.mark.integration
class TestSettingsIntegration:
    """Integration tests for settings loading with real files."""

    def test_load_real_dotenv_file(self):
        """Test loading with a real .env file."""
        env_content = """
        RADARR_BASE_URL=http://integration:7878
        RADARR_API_KEY=integration-key
        LLM_PROVIDER=openai
        RADARR_QUALITY_PROFILE_ID=1
        RADARR_MONITOR=true
        RADARR_TAGS=integration,test
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(env_content)
            env_path = Path(f.name)

        try:
            # Change to the directory containing the .env file
            original_cwd = os.getcwd()
            os.chdir(env_path.parent)

            # Rename to .env so load_dotenv picks it up
            env_file = env_path.parent / ".env"
            env_path.rename(env_file)

            result = load_settings(load_env=True)

            assert result.settings.radarr_base_url == "http://integration:7878"
            assert result.settings.radarr_api_key == "integration-key"
            assert result.settings.llm_provider == "openai"
            assert result.settings.quality_profile_id == 1
            assert result.settings.monitor is True
            assert result.settings.tags == ["integration", "test"]

        finally:
            os.chdir(original_cwd)
            if env_file.exists():
                env_file.unlink()

    def test_load_with_real_config_hierarchy(self):
        """Test loading with realistic configuration hierarchy."""
        # Create a temporary TOML config
        toml_content = """
        [radarr]
        base_url = "http://config:7878"
        quality_profile_id = 5
        root_folder_path = "/config/movies"

        [provider]
        name = "gemini"
        cache_ttl_hours = 24
        region = "CA"

        [providers.gemini]
        api_key = "config-gemini-key"
        """

        env_vars = {
            "RADARR_API_KEY": "env-override-key",  # Override missing TOML value
            "LLM_PROVIDER": "openai",              # Override TOML value
            "OPENAI_API_KEY": "env-openai-key",    # Additional env value
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            config_path = Path(f.name)

        try:
            with patch.dict(os.environ, env_vars, clear=True):
                result = load_settings(config_path=config_path, load_env=False)

                # From TOML
                assert result.settings.radarr_base_url == "http://config:7878"
                assert result.settings.quality_profile_id == 5
                assert result.settings.root_folder_path == "/config/movies"
                assert result.settings.cache_ttl_hours == 24
                assert result.settings.region == "CA"
                assert result.settings.gemini_api_key == "config-gemini-key"

                # From env (overrides and additions)
                assert result.settings.radarr_api_key == "env-override-key"
                assert result.settings.llm_provider == "openai"  # Overridden
                assert result.settings.openai_api_key == "env-openai-key"

                assert result.source_path == config_path

        finally:
            config_path.unlink()