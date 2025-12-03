"""Agentic discovery provider - orchestrator-driven discovery with specialized agents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from radarr_manager.discovery.orchestrator import Orchestrator, OrchestratorConfig
from radarr_manager.discovery.prompt import DiscoveryPrompt
from radarr_manager.discovery.prompts import get_builtin_prompt, get_default_prompt
from radarr_manager.providers.base import MovieDiscoveryProvider, MovieSuggestion

if TYPE_CHECKING:
    from radarr_manager.scrapers.base import ScraperProvider

logger = logging.getLogger(__name__)


class AgenticProvider(MovieDiscoveryProvider):
    """
    Agentic movie discovery provider using Orchestrator + Agents architecture.

    Architecture:
    ┌─────────────────┐
    │ AgenticProvider │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   Orchestrator   │  ← Coordinates agents
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  FetchAgent(s)   │  ← Crawl4AI for URLs
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  AnalysisAgent   │  ← LLM validates/ranks
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  MovieSuggestions │
    └─────────────────┘
    """

    name = "agentic"

    def __init__(
        self,
        *,
        scraper: ScraperProvider | None = None,
        scraper_api_url: str = "http://localhost:11235",
        scraper_api_key: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str = "gpt-4o-mini",
        llm_provider: str = "openai",
        prompt: DiscoveryPrompt | str | None = None,
        debug: bool = False,
    ) -> None:
        """
        Initialize agentic provider.

        Args:
            scraper: Optional scraper provider instance
            scraper_api_url: Crawl4AI API URL
            scraper_api_key: Crawl4AI API key
            llm_api_key: API key for LLM (OpenAI)
            llm_model: LLM model to use
            llm_provider: LLM provider name
            prompt: Discovery prompt (name, DiscoveryPrompt, or None for default)
            debug: Enable debug logging
        """
        self._debug = debug

        # Load prompt
        if prompt is None:
            self._prompt = get_default_prompt()
        elif isinstance(prompt, str):
            self._prompt = get_builtin_prompt(prompt)
        else:
            self._prompt = prompt

        # Configure orchestrator
        self._config = OrchestratorConfig(
            scraper=scraper,
            scraper_api_url=scraper_api_url,
            scraper_api_key=scraper_api_key,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_provider=llm_provider,
        )

        self._orchestrator = Orchestrator(config=self._config, debug=debug)

    async def discover(
        self,
        *,
        limit: int,
        region: str | None = None,
    ) -> list[MovieSuggestion]:
        """
        Discover movies using the orchestrator and specialized agents.

        Args:
            limit: Maximum number of movies to return
            region: Override region variable in prompt

        Returns:
            List of movie suggestions
        """
        if self._debug:
            logger.info(f"[AGENTIC] Using prompt: {self._prompt.name}")
            logger.info(
                f"[AGENTIC] Config: scraper={self._config.has_scraper}, llm={self._config.has_llm}"
            )

        result = await self._orchestrator.discover(
            prompt=self._prompt,
            limit=limit,
            region=region,
        )

        if self._debug:
            logger.info("[AGENTIC] Discovery complete:")
            logger.info(f"  - Fetch stats: {result.fetch_stats}")
            logger.info(f"  - Analysis stats: {result.analysis_stats}")
            logger.info(f"  - Fallback used: {result.fallback_used}")
            logger.info(f"  - Total movies: {len(result.movies)}")
            logger.info(f"  - Sources: {', '.join(result.sources_used)}")

        return result.movies

    def with_prompt(self, prompt: DiscoveryPrompt | str) -> AgenticProvider:
        """Return a new provider with a different prompt."""
        if isinstance(prompt, str):
            prompt = get_builtin_prompt(prompt)
        return AgenticProvider(
            scraper=self._config.scraper,
            scraper_api_url=self._config.scraper_api_url,
            scraper_api_key=self._config.scraper_api_key,
            llm_api_key=self._config.llm_api_key,
            llm_model=self._config.llm_model,
            llm_provider=self._config.llm_provider,
            prompt=prompt,
            debug=self._debug,
        )


__all__ = ["AgenticProvider"]
