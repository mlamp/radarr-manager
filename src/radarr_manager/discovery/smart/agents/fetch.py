"""Smart Fetch Agent - retrieves movies from URLs and returns structured reports."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from radarr_manager.discovery.parsers import get_parser
from radarr_manager.discovery.smart.agents.base import SmartAgent, TimedExecution
from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    AgentType,
    MovieData,
    ReportSection,
    ReportStatus,
)

if TYPE_CHECKING:
    from radarr_manager.scrapers.base import ScraperProvider

logger = logging.getLogger(__name__)


class SmartFetchAgent(SmartAgent):
    """
    Smart agent that fetches movie data from URLs.

    Capabilities:
    - Fetches content via Crawl4AI scraper
    - Parses HTML using specialized parsers (RT, IMDB, etc.)
    - Returns structured report with movie data

    Example tool call from orchestrator:
    ```json
    {
        "name": "fetch_movies",
        "arguments": {
            "url": "https://www.rottentomatoes.com/browse/movies_in_theaters",
            "parser": "rt_theaters",
            "max_movies": 30
        }
    }
    ```
    """

    agent_type = AgentType.FETCH
    name = "fetch_movies"
    description = (
        "Fetch movie data from a URL using web scraping. "
        "Supports Rotten Tomatoes (in theaters, at home) and IMDB (moviemeter). "
        "Returns a list of movies with titles, years, and source information."
    )

    def __init__(
        self,
        scraper: ScraperProvider | None = None,
        api_url: str = "http://localhost:11235",
        api_key: str | None = None,
        debug: bool = False,
    ) -> None:
        super().__init__(debug)
        self._scraper = scraper
        self._api_url = api_url
        self._api_key = api_key

    async def execute(self, **kwargs: Any) -> AgentReport:
        """
        Fetch movies from the specified URL.

        Args:
            url: The URL to fetch
            parser: Parser to use (rt_theaters, rt_home, imdb_moviemeter, generic)
            max_movies: Maximum number of movies to return (default: 50)

        Returns:
            AgentReport with fetched movies
        """
        url = kwargs.get("url", "")
        parser_name = kwargs.get("parser", "generic")
        max_movies = kwargs.get("max_movies", 50)

        if not url:
            return self._create_failure_report("No URL provided")

        self._log(f"Fetching: {url} with parser: {parser_name}")

        with TimedExecution() as timer:
            try:
                # Fetch content
                content = await self._fetch_content(url)
                content_size = len(content)
                self._log(f"Received {content_size} bytes")

                # Parse movies
                parser = get_parser(parser_name)
                parsed_movies = parser.parse(content, url)
                self._log(f"Parsed {len(parsed_movies)} movies")

                # Convert to MovieData
                movies: list[MovieData] = []
                for pm in parsed_movies[:max_movies]:
                    movies.append(
                        MovieData(
                            title=pm.title,
                            year=pm.year,
                            confidence=0.8,
                            sources=[pm.source],
                            metadata=pm.extra or {},
                        )
                    )

                # Build report sections
                sections = [
                    ReportSection(
                        heading="Source Details",
                        content=(
                            f"- URL: {url}\n"
                            f"- Parser: {parser_name}\n"
                            f"- Content size: {content_size:,} bytes"
                        ),
                    ),
                ]

                return AgentReport(
                    agent_type=self.agent_type,
                    agent_name=self.name,
                    status=ReportStatus.SUCCESS,
                    summary=f"Fetched {len(movies)} movies from {parser_name}",
                    sections=sections,
                    movies=movies,
                    stats={
                        "raw_parsed": len(parsed_movies),
                        "returned": len(movies),
                        "content_size_bytes": content_size,
                    },
                    execution_time_ms=timer.elapsed_ms,
                )

            except Exception as exc:
                logger.warning(f"[FETCH] Failed for {url}: {exc}")
                return AgentReport(
                    agent_type=self.agent_type,
                    agent_name=self.name,
                    status=ReportStatus.FAILURE,
                    summary=f"Failed to fetch from {url}",
                    issues=[str(exc)],
                    stats={"error": str(exc)},
                    execution_time_ms=timer.elapsed_ms,
                )

    async def _fetch_content(self, url: str) -> str:
        """Fetch page content via Crawl4AI or scraper."""
        # Use scraper's fetch method if available
        if self._scraper and hasattr(self._scraper, "_fetch_page"):
            return await self._scraper._fetch_page(url)

        # Direct Crawl4AI API call
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

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
                f"{self._api_url}/crawl",
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

        raise RuntimeError(f"Crawl4AI failed: {data.get('error', 'Unknown error')}")

    def _get_parameters_schema(self) -> dict[str, Any]:
        """Get the JSON schema for fetch_movies parameters."""
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "URL to fetch movies from. Supported sites: "
                        "rottentomatoes.com (in_theaters, at_home), imdb.com (moviemeter)"
                    ),
                },
                "parser": {
                    "type": "string",
                    "enum": ["rt_theaters", "rt_home", "imdb_moviemeter", "generic"],
                    "description": "Parser to use for extracting movie data",
                    "default": "generic",
                },
                "max_movies": {
                    "type": "integer",
                    "description": "Maximum number of movies to return",
                    "default": 50,
                },
            },
            "required": ["url"],
        }


__all__ = ["SmartFetchAgent"]
