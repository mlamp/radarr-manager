"""Discovery Agent - orchestrates movie discovery using available tools."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from radarr_manager.discovery.parsers import ParsedMovie, get_parser
from radarr_manager.discovery.prompt import DiscoveryPrompt, DiscoverySource, SourceType

if TYPE_CHECKING:
    from radarr_manager.providers.base import MovieSuggestion
    from radarr_manager.scrapers.base import ScraperProvider

logger = logging.getLogger(__name__)


class DiscoveryError(RuntimeError):
    """Raised when discovery fails."""

    pass


@dataclass
class ToolAvailability:
    """Tracks which tools are available for discovery."""

    scraper: ScraperProvider | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_provider: str = "openai"

    @property
    def has_scraper(self) -> bool:
        return self.scraper is not None

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)


@dataclass
class DiscoveryResult:
    """Result of a discovery operation."""

    movies: list[Any]  # List of MovieSuggestion
    sources_used: list[str] = field(default_factory=list)
    scraped_count: int = 0
    llm_count: int = 0
    fallback_used: bool = False


class DiscoveryAgent:
    """
    Agentic movie discovery system.

    Orchestrates discovery using a prompt-driven approach:
    1. Parse prompt for sources (URLs to scrape, queries to search)
    2. Execute sources using available tools (scraper, LLM web search)
    3. Merge and deduplicate results
    4. Optionally enhance with LLM
    """

    def __init__(
        self,
        tools: ToolAvailability,
        debug: bool = False,
    ) -> None:
        self._tools = tools
        self._debug = debug

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
            DiscoveryResult with merged movie suggestions
        """
        effective_limit = limit or prompt.limit

        # Update variables if region provided
        if region:
            prompt.variables["region"] = region

        # Calculate fetch_limit (limit + 20% buffer for deduplication)
        fetch_limit = int(effective_limit * 1.2)
        prompt.variables["fetch_limit"] = fetch_limit

        sources = prompt.get_resolved_sources()
        if self._debug:
            logger.info(f"[AGENT] Starting discovery with {len(sources)} sources")

        # Separate sources by type
        scrape_sources = [s for s in sources if s.type == SourceType.SCRAPE]
        search_sources = [s for s in sources if s.type == SourceType.WEB_SEARCH]

        all_movies: list[ParsedMovie] = []
        sources_used: list[str] = []
        scraped_count = 0
        llm_count = 0
        fallback_used = False

        # Execute scrape sources if scraper available
        if scrape_sources and self._tools.has_scraper:
            scraped = await self._execute_scrape_sources(scrape_sources)
            all_movies.extend(scraped)
            scraped_count = len(scraped)
            sources_used.extend([f"scrape:{s.parser}" for s in scrape_sources])
            if self._debug:
                logger.info(
                    f"[AGENT] Scraped {scraped_count} movies from {len(scrape_sources)} sources"
                )
        elif scrape_sources and prompt.fallback_to_web_search:
            # Fallback: Convert scrape sources to search queries
            if self._debug:
                logger.info("[AGENT] No scraper available, falling back to web search")
            fallback_used = True
            fallback_queries = self._scrape_to_search_queries(scrape_sources)
            search_sources.extend(fallback_queries)

        # Execute web search sources if LLM available
        if search_sources and self._tools.has_llm:
            llm_movies = await self._execute_search_sources(search_sources, prompt, effective_limit)
            llm_count = len(llm_movies)
            all_movies.extend(llm_movies)
            sources_used.append("llm_web_search")
            if self._debug:
                logger.info(f"[AGENT] LLM web search found {llm_count} movies")

        # Merge and deduplicate
        suggestions = self._merge_to_suggestions(all_movies, effective_limit)

        # LLM enhancement pass (optional)
        if prompt.llm_enhancement.enabled and self._tools.has_llm and suggestions:
            suggestions = await self._enhance_with_llm(suggestions, prompt)

        if self._debug:
            logger.info(f"[AGENT] Final result: {len(suggestions)} unique movies")

        return DiscoveryResult(
            movies=suggestions,
            sources_used=sources_used,
            scraped_count=scraped_count,
            llm_count=llm_count,
            fallback_used=fallback_used,
        )

    async def _execute_scrape_sources(self, sources: list[DiscoverySource]) -> list[ParsedMovie]:
        """Execute scrape sources in parallel."""
        assert self._tools.scraper is not None

        async def scrape_one(source: DiscoverySource) -> list[ParsedMovie]:
            if not source.url:
                return []
            try:
                if self._debug:
                    logger.info(f"[AGENT] Scraping: {source.url}")

                content = await self._fetch_content(source.url)
                parser = get_parser(source.parser or "generic")
                movies = parser.parse(content, source.url)

                if self._debug:
                    logger.info(f"[AGENT] Parsed {len(movies)} movies from {source.url}")
                return movies
            except Exception as exc:
                logger.warning(f"[AGENT] Scrape failed for {source.url}: {exc}")
                return []

        results = await asyncio.gather(*[scrape_one(s) for s in sources])
        return [movie for result in results for movie in result]

    async def _fetch_content(self, url: str) -> str:
        """Fetch page content via scraper."""
        scraper = self._tools.scraper
        assert scraper is not None

        # Use the scraper's internal fetch method if available
        if hasattr(scraper, "_fetch_page"):
            return await scraper._fetch_page(url)

        # Fallback: Direct Crawl4AI call
        api_url = getattr(scraper, "_api_url", "http://localhost:11235")
        api_key = getattr(scraper, "_api_key", None)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "urls": [url],
            "browser_config": {
                "type": "BrowserConfig",
                "params": {"headless": True},
            },
            "crawler_config": {
                "type": "CrawlerRunConfig",
                "params": {
                    "cache_mode": "bypass",
                    "wait_until": "networkidle",
                },
            },
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{api_url}/crawl",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if data.get("success") and data.get("results"):
            result = data["results"][0]
            markdown = result.get("markdown")
            if isinstance(markdown, dict):
                return markdown.get("raw_markdown", "") or markdown.get("fit_markdown", "")
            elif isinstance(markdown, str):
                return markdown
            return result.get("html", "")

        raise DiscoveryError(f"Scraper failed: {data.get('error', 'Unknown error')}")

    async def _execute_search_sources(
        self,
        sources: list[DiscoverySource],
        prompt: DiscoveryPrompt,
        limit: int,
    ) -> list[ParsedMovie]:
        """Execute web search sources using LLM."""
        if not self._tools.has_llm:
            return []

        # Combine all search queries into one LLM request
        queries = [s.query for s in sources if s.query]
        if not queries:
            # Generate a default query from prompt description
            queries = [prompt.description]

        combined_query = " OR ".join(queries)

        try:
            suggestions = await self._llm_web_search(combined_query, limit)
            # Convert suggestions to ParsedMovie format
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
            logger.warning(f"[AGENT] LLM web search failed: {exc}")
            return []

    async def _llm_web_search(self, query: str, limit: int) -> list[Any]:
        """Execute LLM web search for movies."""
        # Import OpenAI provider dynamically to avoid circular imports
        from radarr_manager.providers.openai import OpenAIProvider

        provider = OpenAIProvider(
            api_key=self._tools.llm_api_key or "",
            model=self._tools.llm_model,
            region=None,
            cache_ttl_hours=6,
            debug=self._debug,
        )

        return await provider.discover(limit=limit)

    def _scrape_to_search_queries(self, sources: list[DiscoverySource]) -> list[DiscoverySource]:
        """Convert scrape sources to search queries as fallback."""
        fallback_queries = []
        for source in sources:
            if not source.url:
                continue
            # Generate search query based on source type
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

    def _merge_to_suggestions(self, movies: list[ParsedMovie], limit: int) -> list[Any]:
        """Merge parsed movies into deduplicated suggestions."""
        # Import here to avoid circular import
        from datetime import date

        from radarr_manager.models.movie import MovieSuggestion

        seen_titles: dict[str, MovieSuggestion] = {}

        for movie in movies:
            key = movie.title.lower()

            if key in seen_titles:
                # Merge sources
                existing = seen_titles[key]
                if movie.source not in existing.sources:
                    existing.sources.append(movie.source)
                # Update release_date if we have year and existing doesn't
                if movie.year and not existing.release_date:
                    existing.release_date = date(movie.year, 1, 1)
            else:
                # Create new suggestion
                confidence = movie.extra.get("confidence", 0.8) if movie.extra else 0.8
                overview = movie.extra.get("overview", "") if movie.extra else ""

                # Convert year to release_date
                release_date = date(movie.year, 1, 1) if movie.year else None

                seen_titles[key] = MovieSuggestion(
                    title=movie.title,
                    release_date=release_date,
                    overview=overview or None,
                    confidence=confidence,
                    sources=[movie.source],
                )

        # Sort by source count (more sources = higher confidence), then alphabetically
        suggestions = list(seen_titles.values())
        suggestions.sort(key=lambda s: (-len(s.sources), s.title))

        return suggestions[:limit]

    async def _enhance_with_llm(
        self,
        suggestions: list[MovieSuggestion],
        prompt: DiscoveryPrompt,
    ) -> list[MovieSuggestion]:
        """Enhance suggestions with LLM (add descriptions, validate)."""
        # For now, just return suggestions as-is
        # TODO: Implement LLM enhancement pass
        return suggestions


__all__ = ["DiscoveryAgent", "DiscoveryError", "DiscoveryResult", "ToolAvailability"]
