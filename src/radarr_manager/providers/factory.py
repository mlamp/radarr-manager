from __future__ import annotations

from radarr_manager.config import Settings
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError
from radarr_manager.providers.hybrid import HybridDiscoveryProvider
from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.providers.static import StaticListProvider
from radarr_manager.scrapers.factory import build_scraper


def build_provider(
    settings: Settings, override: str | None = None, debug: bool = False
) -> MovieDiscoveryProvider:
    """Construct a discovery provider based on configuration or CLI overrides."""

    # Check for discovery mode override or setting
    discovery_mode = (override or settings.discovery_mode or "openai").lower()

    # Legacy provider names map to discovery modes
    if discovery_mode == "static":
        return StaticListProvider()

    if discovery_mode == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            region=settings.region,
            cache_ttl_hours=settings.cache_ttl_hours,
            debug=debug,
        )

    if discovery_mode == "hybrid":
        return _build_hybrid_provider(settings, debug)

    if discovery_mode == "scraper":
        return _build_scraper_only_provider(settings, debug)

    raise ProviderError(
        f"Discovery mode '{discovery_mode}' is not implemented. "
        "Valid modes: openai, hybrid, scraper, static"
    )


def _build_hybrid_provider(settings: Settings, debug: bool) -> HybridDiscoveryProvider:
    """Build hybrid provider with scraper + OpenAI."""
    scraper = build_scraper(
        provider=settings.scraper_provider,
        api_url=settings.firecrawl_api_url,
        api_key=settings.firecrawl_api_key,
        debug=debug,
    )

    openai_provider = None
    if settings.openai_api_key:
        openai_provider = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            region=settings.region,
            cache_ttl_hours=settings.cache_ttl_hours,
            debug=debug,
        )

    return HybridDiscoveryProvider(
        scraper=scraper,
        openai_provider=openai_provider,
        debug=debug,
    )


def _build_scraper_only_provider(
    settings: Settings, debug: bool
) -> HybridDiscoveryProvider:
    """Build scraper-only provider (no OpenAI)."""
    scraper = build_scraper(
        provider=settings.scraper_provider,
        api_url=settings.firecrawl_api_url,
        api_key=settings.firecrawl_api_key,
        debug=debug,
    )

    return HybridDiscoveryProvider(
        scraper=scraper,
        openai_provider=None,  # No OpenAI
        debug=debug,
    )


__all__ = ["build_provider"]
