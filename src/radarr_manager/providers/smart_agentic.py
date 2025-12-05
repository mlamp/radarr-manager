"""Smart Agentic Provider - wraps the Smart LLM Orchestrator as a MovieDiscoveryProvider."""

from __future__ import annotations

import logging

from radarr_manager.discovery.smart.orchestrator import (
    SmartOrchestrator,
    SmartOrchestratorConfig,
)
from radarr_manager.models.movie import MovieSuggestion
from radarr_manager.providers.base import MovieDiscoveryProvider

logger = logging.getLogger(__name__)


class SmartAgenticProvider(MovieDiscoveryProvider):
    """
    Smart agentic movie discovery provider using LLM Orchestrator + Smart Agents.

    This provider uses a reasoning LLM (Claude/GPT-4) to orchestrate specialized
    agents for movie discovery. The orchestrator:
    - Understands user intent from natural language prompts
    - Decides which agents to call and in what order
    - Interprets agent reports and adapts strategy
    - Returns curated, ranked movie suggestions

    Architecture:
    ┌─────────────────────────────────────────┐
    │         SmartAgenticProvider            │
    └──────────────────┬──────────────────────┘
                       │
    ┌──────────────────▼──────────────────────┐
    │          SmartOrchestrator              │
    │         (Claude 3.5 / GPT-4o)           │
    │     "The brain" - reasoning LLM         │
    └──────────────────┬──────────────────────┘
                       │ tool calls
          ┌────────────┼────────────┬────────────┐
          ▼            ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │  Fetch   │ │  Search  │ │ Validate │ │  Ranker  │
    │  Agent   │ │  Agent   │ │  Agent   │ │  Agent   │
    │          │ │          │ │          │ │          │
    │  No LLM  │ │  mini    │ │  No LLM  │ │  mini    │
    │  (fast)  │ │  (cheap) │ │  (fast)  │ │  (cheap) │
    └──────────┘ └──────────┘ └──────────┘ └──────────┘
                       │
                       ▼
              Structured Reports
                 (Markdown)
    """

    name = "smart_agentic"

    def __init__(
        self,
        *,
        # Orchestrator LLM (the "brain")
        orchestrator_api_key: str | None = None,
        orchestrator_model: str = "gpt-4o",
        orchestrator_provider: str = "openai",
        # Agent LLM (cheaper, for agent tasks)
        agent_api_key: str | None = None,
        agent_model: str = "gpt-4o-mini",
        # Scraper
        scraper_api_url: str = "http://localhost:11235",
        scraper_api_key: str | None = None,
        # Radarr (for early enrichment/filtering)
        radarr_base_url: str | None = None,
        radarr_api_key: str | None = None,
        # Custom prompt for discovery
        discovery_prompt: str | None = None,
        # Settings
        max_iterations: int = 5,
        debug: bool = False,
    ) -> None:
        """
        Initialize the smart agentic provider.

        Args:
            orchestrator_api_key: API key for orchestrator LLM (GPT-4, Claude)
            orchestrator_model: Model for orchestration (default: gpt-4o)
            orchestrator_provider: Provider for orchestrator (openai or anthropic)
            agent_api_key: API key for agent LLMs (can be same as orchestrator)
            agent_model: Model for agents (default: gpt-4o-mini, cheaper)
            scraper_api_url: Crawl4AI API URL
            scraper_api_key: Crawl4AI API key
            radarr_base_url: Radarr API URL for early enrichment/filtering
            radarr_api_key: Radarr API key
            discovery_prompt: Optional custom prompt for discovery
            max_iterations: Maximum orchestrator reasoning iterations
            debug: Enable debug logging
        """
        self._debug = debug
        self._discovery_prompt = discovery_prompt

        # Use orchestrator key for agents if not specified
        effective_agent_key = agent_api_key or orchestrator_api_key

        # Build config
        config = SmartOrchestratorConfig(
            orchestrator_api_key=orchestrator_api_key,
            orchestrator_model=orchestrator_model,
            orchestrator_provider=orchestrator_provider,
            agent_api_key=effective_agent_key,
            agent_model=agent_model,
            scraper_api_url=scraper_api_url,
            scraper_api_key=scraper_api_key,
            radarr_base_url=radarr_base_url,
            radarr_api_key=radarr_api_key,
            max_iterations=max_iterations,
        )

        self._orchestrator = SmartOrchestrator(config=config, debug=debug)

        if self._debug:
            logger.info("[SMART-AGENTIC] Initialized with:")
            logger.info(f"  - Orchestrator: {orchestrator_model} ({orchestrator_provider})")
            logger.info(f"  - Agent model: {agent_model}")
            logger.info(f"  - Scraper: {scraper_api_url}")
            if radarr_base_url:
                logger.info(f"  - Radarr: {radarr_base_url} (early filtering enabled)")

    async def discover(
        self,
        *,
        limit: int,
        region: str | None = None,
    ) -> list[MovieSuggestion]:
        """
        Discover movies using the smart LLM orchestrator.

        The orchestrator will:
        1. Interpret the discovery prompt
        2. Decide which agents to call (fetch, search, validate, rank)
        3. Coordinate agent execution
        4. Return ranked, validated movie suggestions

        Args:
            limit: Maximum number of movies to return
            region: Region for localized results (default: US)

        Returns:
            List of movie suggestions
        """
        region = region or "US"

        # Build the discovery prompt
        if self._discovery_prompt:
            prompt = self._discovery_prompt
        else:
            prompt = (
                f"Find {limit} trending movies suitable for a home theater collection. "
                f"Include a mix of current theatrical releases and popular streaming content. "
                f"Prioritize quality (high RT/IMDB scores) and mainstream appeal."
            )

        if self._debug:
            logger.info(f"[SMART-AGENTIC] Discovery prompt: {prompt}")
            logger.info(f"[SMART-AGENTIC] Limit: {limit}, Region: {region}")

        # Run the orchestrator
        suggestions = await self._orchestrator.discover(
            prompt=prompt,
            limit=limit,
            region=region,
        )

        if self._debug:
            logger.info(f"[SMART-AGENTIC] Discovered {len(suggestions)} movies")
            for idx, s in enumerate(suggestions[:5], 1):
                logger.info(f"  {idx}. {s.title} ({s.year}) - conf: {s.confidence:.2f}")
            if len(suggestions) > 5:
                logger.info(f"  ... and {len(suggestions) - 5} more")

        return suggestions

    def with_prompt(self, prompt: str) -> SmartAgenticProvider:
        """
        Return a new provider with a custom discovery prompt.

        This allows users to specify exactly what they want:
        - "Find 10 horror movies for Halloween"
        - "Get Oscar-worthy dramas from this season"
        - "Discover sci-fi movies with high IMDB scores"

        Args:
            prompt: Custom discovery prompt

        Returns:
            New SmartAgenticProvider instance with the custom prompt
        """
        return SmartAgenticProvider(
            orchestrator_api_key=self._orchestrator._config.orchestrator_api_key,
            orchestrator_model=self._orchestrator._config.orchestrator_model,
            orchestrator_provider=self._orchestrator._config.orchestrator_provider,
            agent_api_key=self._orchestrator._config.agent_api_key,
            agent_model=self._orchestrator._config.agent_model,
            scraper_api_url=self._orchestrator._config.scraper_api_url,
            scraper_api_key=self._orchestrator._config.scraper_api_key,
            radarr_base_url=self._orchestrator._config.radarr_base_url,
            radarr_api_key=self._orchestrator._config.radarr_api_key,
            discovery_prompt=prompt,
            max_iterations=self._orchestrator._config.max_iterations,
            debug=self._debug,
        )


__all__ = ["SmartAgenticProvider"]
