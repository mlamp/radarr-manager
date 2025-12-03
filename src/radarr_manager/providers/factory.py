from __future__ import annotations

from radarr_manager.config import Settings
from radarr_manager.providers.agentic import AgenticProvider
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError
from radarr_manager.providers.hybrid import HybridDiscoveryProvider
from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.providers.smart_agentic import SmartAgenticProvider
from radarr_manager.providers.static import StaticListProvider
from radarr_manager.scrapers.factory import build_scraper


def build_provider(
    settings: Settings,
    override: str | None = None,
    debug: bool = False,
    prompt: str | None = None,
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

    if discovery_mode == "agentic":
        return _build_agentic_provider(settings, debug, prompt)

    if discovery_mode == "smart_agentic" or discovery_mode == "smart":
        return _build_smart_agentic_provider(settings, debug, prompt)

    raise ProviderError(
        f"Discovery mode '{discovery_mode}' is not implemented. "
        "Valid modes: openai, hybrid, scraper, agentic, smart_agentic, static"
    )


def _build_hybrid_provider(settings: Settings, debug: bool) -> HybridDiscoveryProvider:
    """Build hybrid provider with scraper + OpenAI."""
    scraper = build_scraper(
        provider=settings.scraper_provider,
        api_url=settings.scraper_api_url,
        api_key=settings.scraper_api_key,
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


def _build_scraper_only_provider(settings: Settings, debug: bool) -> HybridDiscoveryProvider:
    """Build scraper-only provider (no OpenAI)."""
    scraper = build_scraper(
        provider=settings.scraper_provider,
        api_url=settings.scraper_api_url,
        api_key=settings.scraper_api_key,
        debug=debug,
    )

    return HybridDiscoveryProvider(
        scraper=scraper,
        openai_provider=None,  # No OpenAI
        debug=debug,
    )


def _build_agentic_provider(
    settings: Settings, debug: bool, prompt: str | None = None
) -> AgenticProvider:
    """Build agentic provider with orchestrator + agents architecture."""
    # Build scraper if configured
    scraper = None
    if settings.scraper_enabled or settings.scraper_api_url:
        try:
            scraper = build_scraper(
                provider=settings.scraper_provider,
                api_url=settings.scraper_api_url,
                api_key=settings.scraper_api_key,
                debug=debug,
            )
        except Exception:
            # Scraper not available, will use direct Crawl4AI API
            pass

    return AgenticProvider(
        scraper=scraper,
        scraper_api_url=settings.scraper_api_url or "http://localhost:11235",
        scraper_api_key=settings.scraper_api_key,
        llm_api_key=settings.openai_api_key,
        llm_model=settings.openai_model or "gpt-4o-mini",
        prompt=prompt,
        debug=debug,
    )


def _build_smart_agentic_provider(
    settings: Settings, debug: bool, prompt: str | None = None
) -> SmartAgenticProvider:
    """
    Build smart agentic provider with LLM orchestrator + smart agents.

    This is the advanced architecture where:
    - A reasoning LLM (GPT-4/Claude) orchestrates discovery
    - Specialized agents (fetch, search, validate, rank) do the work
    - Agents communicate via structured markdown reports
    """
    # Determine orchestrator model - use a smarter model for reasoning
    orchestrator_model = settings.openai_model or "gpt-4o"
    if orchestrator_model in ("gpt-4o-mini", "gpt-3.5-turbo"):
        # Upgrade to smarter model for orchestration
        orchestrator_model = "gpt-4o"

    # Agent model - use cheaper model for agent tasks
    agent_model = "gpt-4o-mini"

    return SmartAgenticProvider(
        orchestrator_api_key=settings.openai_api_key,
        orchestrator_model=orchestrator_model,
        orchestrator_provider="openai",
        agent_api_key=settings.openai_api_key,
        agent_model=agent_model,
        scraper_api_url=settings.scraper_api_url or "http://localhost:11235",
        scraper_api_key=settings.scraper_api_key,
        discovery_prompt=prompt,
        debug=debug,
    )


__all__ = ["build_provider"]
