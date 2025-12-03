"""Firecrawl-based web scraper for movie discovery."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from radarr_manager.scrapers.base import ScrapedMovie, ScraperError, ScraperProvider

logger = logging.getLogger(__name__)

# Patterns to extract movie titles from scraped content
RT_MOVIE_PATTERN = re.compile(
    r"(?:^|\n)([A-Z][^(\n]{2,50})\s*\((\d{4})\)",
    re.MULTILINE,
)
IMDB_MOVIE_PATTERN = re.compile(
    r"(\d+)\.\s*([^(\n]{2,60})\s*\((\d{4})\)",
    re.MULTILINE,
)


class FirecrawlScraper(ScraperProvider):
    """Scraper using Firecrawl API for reliable web scraping."""

    name = "firecrawl"

    def __init__(
        self,
        *,
        api_url: str = "http://localhost:3002",
        api_key: str | None = None,
        debug: bool = False,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._debug = debug

    async def scrape_movies(self, url: str) -> list[ScrapedMovie]:
        """Scrape movie titles from a URL using Firecrawl."""
        if self._debug:
            logger.info(f"[SCRAPER] Fetching: {url}")

        try:
            content = await self._fetch_page(url)
        except Exception as exc:
            raise ScraperError(f"Failed to scrape {url}: {exc}") from exc

        # Parse movies based on the source
        if "rottentomatoes.com" in url:
            movies = self._parse_rt_content(content, url)
        elif "imdb.com" in url:
            movies = self._parse_imdb_content(content, url)
        else:
            movies = self._parse_generic_content(content, url)

        if self._debug:
            logger.info(f"[SCRAPER] Found {len(movies)} movies from {url}")

        return movies

    async def _fetch_page(self, url: str) -> str:
        """Fetch page content via Firecrawl API."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "waitFor": 3000,  # Wait for JS rendering
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._api_url}/v1/scrape",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                error_text = response.text[:500]
                raise ScraperError(
                    f"Firecrawl API error {response.status_code}: {error_text}"
                )

            data = response.json()

        # Extract markdown content from response
        if data.get("success") and data.get("data"):
            return data["data"].get("markdown", "")
        elif data.get("markdown"):
            return data["markdown"]
        else:
            raise ScraperError(f"Unexpected Firecrawl response format: {data.keys()}")

    def _parse_rt_content(self, content: str, url: str) -> list[ScrapedMovie]:
        """Parse Rotten Tomatoes page content for movie titles."""
        movies: list[ScrapedMovie] = []

        # RT format typically has movie cards with title and year
        # Look for patterns like "Movie Title (2024)" or markdown links
        lines = content.split("\n")

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Skip navigation/menu items
            if any(
                skip in line.lower()
                for skip in [
                    "sign in",
                    "menu",
                    "search",
                    "home",
                    "movies",
                    "tv shows",
                    "more",
                    "what to watch",
                    "rotten tomatoes",
                    "certified fresh",
                    "audience score",
                    "tomatometer",
                    "see all",
                    "view all",
                ]
            ):
                continue

            # Try to extract title (Year) pattern
            match = re.search(r"^([A-Z][^(\[\]]{2,50}?)\s*\((\d{4})\)", line)
            if match:
                title = match.group(1).strip()
                year = int(match.group(2))

                # Skip if title is too generic or contains scores
                if len(title) > 3 and "%" not in title:
                    movies.append(
                        ScrapedMovie(
                            title=title,
                            year=year,
                            source="rt",
                            url=url,
                        )
                    )
                continue

            # Try markdown link pattern [Title](url)
            link_match = re.search(r"\[([^\]]{3,50})\]\(/m/[a-z0-9_]+\)", line)
            if link_match:
                title = link_match.group(1).strip()
                if len(title) > 3 and "%" not in title:
                    movies.append(
                        ScrapedMovie(
                            title=title,
                            source="rt",
                            url=url,
                        )
                    )

        return movies

    def _parse_imdb_content(self, content: str, url: str) -> list[ScrapedMovie]:
        """Parse IMDB moviemeter page content."""
        movies: list[ScrapedMovie] = []

        # IMDB moviemeter format: "1. Movie Title (2024)"
        for match in IMDB_MOVIE_PATTERN.finditer(content):
            rank = int(match.group(1))
            title = match.group(2).strip()
            year = int(match.group(3))

            # Only take top movies (reasonable limit)
            if rank <= 50 and len(title) > 2:
                movies.append(
                    ScrapedMovie(
                        title=title,
                        year=year,
                        source="imdb",
                        url=url,
                        extra={"rank": rank},
                    )
                )

        # Also try markdown table format that IMDB sometimes uses
        lines = content.split("\n")
        for line in lines:
            # Look for table rows with movie data
            if "|" in line and "(" in line and ")" in line:
                # Extract title from table cell
                match = re.search(r"\|\s*([^|]{3,50}?)\s*\((\d{4})\)", line)
                if match:
                    title = match.group(1).strip()
                    year = int(match.group(2))
                    if len(title) > 2 and not any(
                        skip in title.lower()
                        for skip in ["rank", "title", "year", "rating"]
                    ):
                        movies.append(
                            ScrapedMovie(
                                title=title,
                                year=year,
                                source="imdb",
                                url=url,
                            )
                        )

        return movies

    def _parse_generic_content(self, content: str, url: str) -> list[ScrapedMovie]:
        """Generic parser for unknown page formats."""
        movies: list[ScrapedMovie] = []

        # Look for common title (year) patterns
        for match in re.finditer(r"([A-Z][^(\n\[\]]{2,50}?)\s*\((\d{4})\)", content):
            title = match.group(1).strip()
            year = int(match.group(2))
            if len(title) > 3:
                movies.append(
                    ScrapedMovie(
                        title=title,
                        year=year,
                        source="generic",
                        url=url,
                    )
                )

        return movies


__all__ = ["FirecrawlScraper"]
