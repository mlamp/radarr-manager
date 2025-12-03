"""Fetch Agent - retrieves content from URLs via Crawl4AI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

from radarr_manager.discovery.agents.base import Agent, AgentMessage, AgentResult, AgentStatus
from radarr_manager.discovery.parsers import ParsedMovie, get_parser

if TYPE_CHECKING:
    from radarr_manager.scrapers.base import ScraperProvider

logger = logging.getLogger(__name__)


@dataclass
class FetchRequest(AgentMessage):
    """Request to fetch and parse content from a URL."""

    url: str = ""
    parser_name: str = "generic"
    priority: int = 1


@dataclass
class FetchResult(AgentResult):
    """Result of a fetch operation."""

    url: str = ""
    movies: list[ParsedMovie] = field(default_factory=list)
    raw_content_length: int = 0


class FetchAgent(Agent[FetchRequest, FetchResult]):
    """
    Agent that fetches content from URLs and parses movie data.

    Uses Crawl4AI (or direct HTTP fallback) to retrieve page content,
    then applies the appropriate parser to extract movie information.
    """

    name = "fetch"

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

    async def execute(self, request: FetchRequest) -> FetchResult:
        """Fetch URL content and parse for movies."""
        self._log(f"Fetching: {request.url}")

        try:
            content = await self._fetch_content(request.url)
            self._log(f"Received {len(content)} bytes from {request.url}")

            parser = get_parser(request.parser_name)
            movies = parser.parse(content, request.url)
            self._log(f"Parsed {len(movies)} movies using {request.parser_name} parser")

            return FetchResult(
                agent_id=self.name,
                url=request.url,
                movies=movies,
                raw_content_length=len(content),
                status=AgentStatus.SUCCESS,
            )

        except Exception as exc:
            logger.warning(f"[FETCH] Failed for {request.url}: {exc}")
            return FetchResult(
                agent_id=self.name,
                url=request.url,
                movies=[],
                status=AgentStatus.FAILURE,
                error=str(exc),
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


__all__ = ["FetchAgent", "FetchRequest", "FetchResult"]
