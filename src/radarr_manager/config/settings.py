from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

CONFIG_PATH_ENV = "RADARR_MANAGER_CONFIG"


class Settings(BaseModel):
    """Application configuration resolved from env vars and optional TOML files."""

    radarr_base_url: str | None = Field(default=None, alias="RADARR_BASE_URL")
    radarr_api_key: str | None = Field(default=None, alias="RADARR_API_KEY")
    llm_provider: str | None = Field(default=None, alias="LLM_PROVIDER")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str | None = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    grok_api_key: str | None = Field(default=None, alias="GROK_API_KEY")

    quality_profile_id: int | None = Field(default=None, alias="RADARR_QUALITY_PROFILE_ID")
    root_folder_path: str | None = Field(default=None, alias="RADARR_ROOT_FOLDER_PATH")
    minimum_availability: str | None = Field(default=None, alias="RADARR_MINIMUM_AVAILABILITY")
    monitor: bool = Field(default=True, alias="RADARR_MONITOR")
    tags: list[str] = Field(default_factory=list, alias="RADARR_TAGS")

    cache_ttl_hours: int = Field(default=6)
    region: str | None = Field(default=None)

    # MCP Service Configuration
    mcp_host: str = Field(default="127.0.0.1", alias="MCP_HOST")
    mcp_port: int = Field(default=8091, alias="MCP_PORT")
    mcp_transport: str = Field(default="stdio", alias="MCP_TRANSPORT")

    model_config = {
        "populate_by_name": True,
        "str_strip_whitespace": True,
        "extra": "ignore",
    }

    def require_radarr(self) -> None:
        """Ensure Radarr connection settings are available."""
        if not self.radarr_base_url or not self.radarr_api_key:
            raise SettingsError(
                "Missing RADARR_BASE_URL or RADARR_API_KEY. Configure environment or TOML file.",
            )


class SettingsError(RuntimeError):
    """Raised when configuration cannot be resolved."""


@dataclass(frozen=True)
class SettingsLoadResult:
    settings: Settings
    source_path: Path | None


def load_settings(config_path: Path | None = None, *, load_env: bool = True) -> SettingsLoadResult:
    """Load settings from .env files, environment variables, and optional TOML configuration."""

    if load_env:
        load_dotenv()

    resolved_path = _determine_config_path(config_path)
    config_data: dict[str, Any] = {}

    if resolved_path and resolved_path.exists():
        with resolved_path.open("rb") as handle:
            toml_payload = tomllib.load(handle)
        config_data = _flatten_toml(toml_payload)

    env_data = _collect_env_overrides()
    merged = {**config_data, **env_data}

    try:
        settings = Settings.model_validate(merged)
    except ValidationError as exc:  # pragma: no cover - surfaced via CLI messaging
        raise SettingsError(str(exc)) from exc

    return SettingsLoadResult(settings=settings, source_path=resolved_path)


def _determine_config_path(config_path: Path | None) -> Path | None:
    if config_path:
        return config_path

    env_override = os.getenv(CONFIG_PATH_ENV)
    if env_override:
        return Path(env_override).expanduser().resolve()

    default_path = Path.home() / ".config" / "radarr-manager" / "config.toml"
    return default_path if default_path.exists() else None


def _flatten_toml(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    radarr_cfg = payload.get("radarr", {})
    if "base_url" in radarr_cfg:
        result["radarr_base_url"] = radarr_cfg.get("base_url")
    if "api_key" in radarr_cfg:
        result["radarr_api_key"] = radarr_cfg.get("api_key")
    if "quality_profile_id" in radarr_cfg:
        result["quality_profile_id"] = radarr_cfg.get("quality_profile_id")
    if "root_folder_path" in radarr_cfg:
        result["root_folder_path"] = radarr_cfg.get("root_folder_path")
    if "minimum_availability" in radarr_cfg:
        result["minimum_availability"] = radarr_cfg.get("minimum_availability")
    if "monitor" in radarr_cfg:
        result["monitor"] = bool(radarr_cfg.get("monitor"))
    if "tags" in radarr_cfg:
        tags_value = radarr_cfg.get("tags")
        if isinstance(tags_value, (list, tuple)):
            result["tags"] = [str(tag) for tag in tags_value]
        elif isinstance(tags_value, str):
            result["tags"] = [tag.strip() for tag in tags_value.split(",") if tag.strip()]

    provider_cfg = payload.get("provider", {})
    if "name" in provider_cfg:
        result["llm_provider"] = provider_cfg.get("name")
    if "cache_ttl_hours" in provider_cfg:
        result["cache_ttl_hours"] = int(provider_cfg.get("cache_ttl_hours"))
    if "region" in provider_cfg:
        result["region"] = provider_cfg.get("region")

    providers_cfg = payload.get("providers", {})
    openai_cfg = providers_cfg.get("openai", {}) if isinstance(providers_cfg, dict) else {}
    if "api_key" in openai_cfg:
        result["openai_api_key"] = openai_cfg.get("api_key")
    if "model" in openai_cfg:
        result["openai_model"] = openai_cfg.get("model")

    gemini_cfg = providers_cfg.get("gemini", {}) if isinstance(providers_cfg, dict) else {}
    if "api_key" in gemini_cfg:
        result["gemini_api_key"] = gemini_cfg.get("api_key")

    grok_cfg = providers_cfg.get("grok", {}) if isinstance(providers_cfg, dict) else {}
    if "api_key" in grok_cfg:
        result["grok_api_key"] = grok_cfg.get("api_key")

    return result


def _collect_env_overrides() -> dict[str, Any]:
    mapping: dict[str, str] = {
        "RADARR_BASE_URL": "radarr_base_url",
        "RADARR_API_KEY": "radarr_api_key",
        "LLM_PROVIDER": "llm_provider",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "GEMINI_API_KEY": "gemini_api_key",
        "GROK_API_KEY": "grok_api_key",
        "RADARR_QUALITY_PROFILE_ID": "quality_profile_id",
        "RADARR_ROOT_FOLDER_PATH": "root_folder_path",
        "RADARR_MINIMUM_AVAILABILITY": "minimum_availability",
        "RADARR_MONITOR": "monitor",
        "RADARR_TAGS": "tags",
        "RADARR_CACHE_TTL_HOURS": "cache_ttl_hours",
        "RADARR_REGION": "region",
        "MCP_HOST": "mcp_host",
        "MCP_PORT": "mcp_port",
        "MCP_TRANSPORT": "mcp_transport",
    }

    result: dict[str, Any] = {}
    for env_name, field in mapping.items():
        if env_name not in os.environ:
            continue
        value = os.environ[env_name]
        if field in {"quality_profile_id", "cache_ttl_hours", "mcp_port"}:
            result[field] = int(value)
        elif field == "monitor":
            result[field] = value.lower() not in {"false", "0", "no"}
        elif field == "tags":
            result[field] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            result[field] = value
    return result


__all__ = ["Settings", "SettingsError", "SettingsLoadResult", "load_settings"]
