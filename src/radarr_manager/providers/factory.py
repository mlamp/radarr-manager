from __future__ import annotations

from radarr_manager.config import Settings
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError
from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.providers.static import StaticListProvider


def build_provider(
    settings: Settings, override: str | None = None, debug: bool = False
) -> MovieDiscoveryProvider:
    """Construct a discovery provider based on configuration or CLI overrides."""

    provider_name = (override or settings.llm_provider or "static").lower()

    if provider_name == "static":
        return StaticListProvider()

    if provider_name == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            region=settings.region,
            cache_ttl_hours=settings.cache_ttl_hours,
            debug=debug,
        )

    raise ProviderError(
        f"Provider '{provider_name}' is not implemented yet. Add provider integration in providers/*.py",
    )


__all__ = ["build_provider"]
