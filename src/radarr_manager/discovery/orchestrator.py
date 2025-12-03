"""Discovery Orchestrator - coordinates agents for movie discovery."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from radarr_manager.discovery.agents.analysis import (
    AnalysisAgent,
    AnalysisRequest,
    analyzed_to_suggestion,
)
from radarr_manager.discovery.agents.base import AgentStatus
from radarr_manager.discovery.agents.fetch import FetchAgent, FetchRequest
from radarr_manager.discovery.parsers import ParsedMovie
from radarr_manager.discovery.prompt import DiscoveryPrompt, SourceType

if TYPE_CHECKING:
    from radarr_manager.scrapers.base import ScraperProvider

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the discovery orchestrator."""

    # Scraper (Crawl4AI)
    scraper: ScraperProvider | None = None
    scraper_api_url: str = "http://localhost:11235"
    scraper_api_key: str | None = None

    # LLM
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_provider: str = "openai"

    @property
    def has_scraper(self) -> bool:
        return self.scraper is not None or bool(self.scraper_api_url)

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)


@dataclass
class DiscoveryResult:
    """Result of a discovery operation."""

    movies: list[Any]  # List of MovieSuggestion
    sources_used: list[str] = field(default_factory=list)
    fetch_stats: dict[str, int] = field(default_factory=dict)
    analysis_stats: dict[str, int] = field(default_factory=dict)
    fallback_used: bool = False


class Orchestrator:
    """
    Orchestrates movie discovery using specialized agents.

    The orchestrator:
    1. Reads the discovery prompt configuration
    2. Dispatches FetchAgent(s) in parallel for each scrape source
    3. Collects all fetch results
    4. Sends aggregated results to AnalysisAgent for validation/ranking
    5. Returns final deduplicated, ranked movie suggestions

    Flow:
    ┌─────────────────┐
    │  DiscoveryPrompt │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   Orchestrator   │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   FetchAgent(s)  │  ← Parallel fetch from URLs
    │   (Crawl4AI)     │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  AnalysisAgent   │  ← LLM validates/ranks
    │  (OpenAI)        │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ MovieSuggestions │
    └─────────────────┘
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        debug: bool = False,
    ) -> None:
        self._config = config
        self._debug = debug

        # Initialize agents
        self._fetch_agent = FetchAgent(
            scraper=config.scraper,
            api_url=config.scraper_api_url,
            api_key=config.scraper_api_key,
            debug=debug,
        )

        self._analysis_agent: AnalysisAgent | None = None
        if config.has_llm:
            self._analysis_agent = AnalysisAgent(
                api_key=config.llm_api_key or "",
                model=config.llm_model,
                provider=config.llm_provider,
                debug=debug,
            )

    async def discover(
        self,
        prompt: DiscoveryPrompt,
        limit: int | None = None,
        region: str | None = None,
    ) -> DiscoveryResult:
        """
        Execute discovery based on the prompt configuration.

        Args:
            prompt: Discovery prompt configuration
            limit: Override limit from prompt
            region: Override region variable

        Returns:
            DiscoveryResult with movie suggestions
        """
        effective_limit = limit or prompt.limit

        # Update variables
        if region:
            prompt.variables["region"] = region

        # Calculate fetch_limit (limit + 20% buffer for deduplication losses)
        fetch_limit = int(effective_limit * 1.2)
        prompt.variables["fetch_limit"] = fetch_limit

        self._log(f"Starting discovery: limit={effective_limit}, fetch_limit={fetch_limit}")

        # Get resolved sources
        sources = prompt.get_resolved_sources()
        scrape_sources = [s for s in sources if s.type == SourceType.SCRAPE]
        search_sources = [s for s in sources if s.type == SourceType.WEB_SEARCH]

        self._log(f"Sources: {len(scrape_sources)} scrape, {len(search_sources)} search")

        all_movies: list[ParsedMovie] = []
        sources_used: list[str] = []
        fetch_stats: dict[str, int] = {"total": 0, "success": 0, "failed": 0}
        fallback_used = False

        # Phase 1: Execute fetch agents in parallel
        if scrape_sources and self._config.has_scraper:
            fetched = await self._execute_fetches(scrape_sources)
            all_movies.extend(fetched["movies"])
            fetch_stats = fetched["stats"]
            sources_used.extend(fetched["sources"])
            self._log(
                f"Fetch complete: {fetch_stats['success']}/{fetch_stats['total']} sources, "
                f"{len(fetched['movies'])} movies"
            )
        elif scrape_sources and prompt.fallback_to_web_search:
            # Fallback: Convert scrape sources to search queries
            self._log("No scraper available, falling back to web search")
            fallback_used = True
            fallback_queries = self._scrape_to_search_queries(scrape_sources)
            search_sources.extend(fallback_queries)

        # Phase 2: Execute web search if configured
        if search_sources and self._config.has_llm:
            searched = await self._execute_web_search(search_sources, prompt, effective_limit)
            all_movies.extend(searched)
            sources_used.append("llm_web_search")
            self._log(f"Web search found {len(searched)} movies")

        # Phase 3: Analysis agent validates (Python) and enhances (LLM)
        analysis_stats: dict[str, Any] = {
            "total": 0,
            "validated": 0,
            "rejected": 0,
            "enhanced": 0,
            "rejection_breakdown": {},
        }
        if self._analysis_agent and all_movies:
            self._log(f"Sending {len(all_movies)} movies to analysis agent")

            analysis_result = await self._analysis_agent.execute(
                AnalysisRequest(
                    agent_id="orchestrator",
                    movies=all_movies,
                    limit=effective_limit,
                    criteria=prompt.llm_enhancement.prompt or "",
                    region=prompt.variables.get("region", "US"),
                    enhance_with_llm=prompt.llm_enhancement.enabled,
                )
            )

            analysis_stats = {
                "total": analysis_result.total_input,
                "validated": analysis_result.validated_count,
                "rejected": analysis_result.rejected_count,
                "enhanced": analysis_result.enhanced_count,
                "rejection_breakdown": analysis_result.rejection_breakdown,
            }

            # Convert to MovieSuggestion
            suggestions = [analyzed_to_suggestion(m) for m in analysis_result.movies]

            self._log(
                f"Analysis complete: {analysis_stats['validated']} valid, "
                f"{analysis_stats['rejected']} rejected, "
                f"{analysis_stats['enhanced']} enhanced"
            )
            if analysis_stats["rejection_breakdown"]:
                self._log(f"Rejection reasons: {analysis_stats['rejection_breakdown']}")
        else:
            # No LLM: simple deduplication
            suggestions = self._simple_merge(all_movies, effective_limit)
            self._log(f"Simple merge: {len(suggestions)} unique movies")

        return DiscoveryResult(
            movies=suggestions,
            sources_used=sources_used,
            fetch_stats=fetch_stats,
            analysis_stats=analysis_stats,
            fallback_used=fallback_used,
        )

    async def _execute_fetches(self, sources: list) -> dict[str, Any]:
        """Execute fetch agents in parallel for all scrape sources."""

        async def fetch_one(source) -> dict[str, Any]:
            if not source.url:
                return {"movies": [], "success": False, "source": None}

            request = FetchRequest(
                agent_id="orchestrator",
                url=source.url,
                parser_name=source.parser or "generic",
                priority=source.priority,
            )

            result = await self._fetch_agent.execute(request)

            return {
                "movies": result.movies,
                "success": result.status == AgentStatus.SUCCESS,
                "source": f"scrape:{source.parser or 'generic'}",
            }

        # Execute all fetches in parallel
        results = await asyncio.gather(*[fetch_one(s) for s in sources])

        # Aggregate results
        all_movies: list[ParsedMovie] = []
        sources_used: list[str] = []
        success_count = 0

        for result in results:
            all_movies.extend(result["movies"])
            if result["success"]:
                success_count += 1
            if result["source"]:
                sources_used.append(result["source"])

        return {
            "movies": all_movies,
            "stats": {
                "total": len(sources),
                "success": success_count,
                "failed": len(sources) - success_count,
            },
            "sources": sources_used,
        }

    async def _execute_web_search(
        self, sources: list, prompt: DiscoveryPrompt, limit: int
    ) -> list[ParsedMovie]:
        """Execute LLM web search for additional movies."""
        if not self._config.has_llm:
            return []

        # Import OpenAI provider for web search
        from radarr_manager.providers.openai import OpenAIProvider

        # Note: queries are available from sources but OpenAI provider uses its own search
        # In future, we could pass combined queries to a dedicated SearchAgent

        try:
            provider = OpenAIProvider(
                api_key=self._config.llm_api_key or "",
                model=self._config.llm_model,
                region=prompt.variables.get("region"),
                cache_ttl_hours=6,
                debug=self._debug,
            )

            suggestions = await provider.discover(limit=limit)

            # Convert to ParsedMovie
            return [
                ParsedMovie(
                    title=s.title,
                    year=s.year,
                    source="llm_web_search",
                    extra={"confidence": s.confidence, "overview": s.overview or ""},
                )
                for s in suggestions
            ]
        except Exception as exc:
            logger.warning(f"[ORCHESTRATOR] Web search failed: {exc}")
            return []

    def _scrape_to_search_queries(self, sources: list) -> list:
        """Convert scrape sources to search queries as fallback."""
        from radarr_manager.discovery.prompt import DiscoverySource

        fallback_queries = []
        for source in sources:
            if not source.url:
                continue

            if "rottentomatoes.com" in source.url:
                if "in_theaters" in source.url:
                    query = "current movies in theaters box office"
                elif "at_home" in source.url:
                    query = "popular streaming movies right now"
                else:
                    query = "trending movies rotten tomatoes"
            elif "imdb.com" in source.url:
                query = "IMDB most popular movies moviemeter"
            else:
                query = "trending movies now"

            fallback_queries.append(
                DiscoverySource(
                    type=SourceType.WEB_SEARCH,
                    query=query,
                    priority=source.priority,
                )
            )

        return fallback_queries

    def _simple_merge(self, movies: list[ParsedMovie], limit: int) -> list[Any]:
        """Simple deduplication without LLM analysis."""
        from datetime import date

        from radarr_manager.models.movie import MovieSuggestion

        seen: dict[str, MovieSuggestion] = {}

        for movie in movies:
            key = movie.title.lower().strip()

            if key in seen:
                if movie.source not in seen[key].sources:
                    seen[key].sources.append(movie.source)
                if movie.year and not seen[key].release_date:
                    seen[key].release_date = date(movie.year, 1, 1)
            else:
                release_date = date(movie.year, 1, 1) if movie.year else None
                overview = movie.extra.get("overview") if movie.extra else None

                seen[key] = MovieSuggestion(
                    title=movie.title,
                    release_date=release_date,
                    overview=overview,
                    confidence=0.8,
                    sources=[movie.source],
                )

        # Sort by source count, then alphabetically
        suggestions = list(seen.values())
        suggestions.sort(key=lambda s: (-len(s.sources), s.title))

        return suggestions[:limit]

    def _log(self, message: str) -> None:
        """Log a debug message if debugging is enabled."""
        if self._debug:
            logger.info(f"[ORCHESTRATOR] {message}")


__all__ = ["Orchestrator", "OrchestratorConfig", "DiscoveryResult"]
