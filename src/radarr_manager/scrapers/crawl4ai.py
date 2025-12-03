"""Crawl4AI-based web scraper for movie discovery."""

from __future__ import annotations

import logging
import re

import httpx

from radarr_manager.scrapers.base import ScrapedMovie, ScraperError, ScraperProvider

logger = logging.getLogger(__name__)


class Crawl4AIScraper(ScraperProvider):
    """Scraper using Crawl4AI API for reliable web scraping."""

    name = "crawl4ai"

    def __init__(
        self,
        *,
        api_url: str = "http://localhost:11235",
        api_key: str | None = None,
        debug: bool = False,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._debug = debug

    async def scrape_movies(self, url: str) -> list[ScrapedMovie]:
        """Scrape movie titles from a URL using Crawl4AI."""
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
        """Fetch page content via Crawl4AI API."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Crawl4AI request format
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

            if response.status_code != 200:
                error_text = response.text[:500]
                raise ScraperError(
                    f"Crawl4AI API error {response.status_code}: {error_text}"
                )

            data = response.json()

        # Extract markdown content from Crawl4AI response
        if data.get("success") and data.get("results"):
            result = data["results"][0]
            # Handle both old (string) and new (dict) markdown formats
            markdown = result.get("markdown")
            if isinstance(markdown, dict):
                # New format: markdown is a dict with raw_markdown, fit_markdown, etc.
                return markdown.get("raw_markdown", "") or markdown.get("fit_markdown", "")
            elif isinstance(markdown, str):
                return markdown
            else:
                return result.get("html", "")
        else:
            error_msg = data.get("error", "Unknown error")
            raise ScraperError(f"Crawl4AI request failed: {error_msg}")

    def _parse_rt_content(self, content: str, url: str) -> list[ScrapedMovie]:
        """Parse Rotten Tomatoes page content for movie titles."""
        movies: list[ScrapedMovie] = []
        seen_titles: set[str] = set()

        # Pattern 1: Movie links with ratings and dates
        # Format: [ XX% YY% Title Opened/Opens Month DD, YYYY ](url/m/...)
        # or: [ XX% Title Opened/Opens Month DD, YYYY ](url/m/...)
        movie_link_pattern = re.compile(
            r"\[\s*(?:\d+%\s*)?(?:\d+%\s*)?"  # Optional ratings (XX% YY%)
            r"([A-Z][^[\]]{2,80}?)"  # Title (starts with capital)
            r"\s+(?:Opened?|Opens)\s+"  # Opened/Opens
            r"[A-Z][a-z]{2}\s+\d{1,2},\s+(\d{4})"  # Month DD, YYYY
            r"\s*\]\s*\(https?://www\.rottentomatoes\.com/m/",
            re.IGNORECASE,
        )

        for match in movie_link_pattern.finditer(content):
            title = match.group(1).strip()
            year = int(match.group(2))
            title = self._clean_title(title)

            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(
                    ScrapedMovie(
                        title=title,
                        year=year,
                        source="rt",
                        url=url,
                    )
                )

        # Pattern 2: Certified fresh picks format
        # Format: [ XX% Title Link to Title ](url/m/...)
        cert_fresh_pattern = re.compile(
            r"\[\s*\d+%\s+"  # Rating XX%
            r"([A-Z][^[\]]{2,60}?)"  # Title
            r"\s+Link to\s+"  # "Link to"
            r"[^[\]]+\s*\]"  # Rest of link text
            r"\s*\(https?://www\.rottentomatoes\.com/m/",
        )

        for match in cert_fresh_pattern.finditer(content):
            title = match.group(1).strip()
            title = self._clean_title(title)

            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(
                    ScrapedMovie(
                        title=title,
                        source="rt",
                        url=url,
                    )
                )

        # Pattern 3: Simple watchlist format
        # Format: [ XX% Title Opened/Opens Month DD, YYYY ](url) Watchlist
        watchlist_pattern = re.compile(
            r"\[\s*(?:\d+%\s*)?"  # Optional rating
            r"([A-Z][^[\]]{2,60}?)"  # Title
            r"\s+(?:Opened?|Opens)\s+"
            r"[A-Z][a-z]{2}\s+\d{1,2},\s+(\d{4})"
            r"\s*\]\s*\([^)]+\)\s*Watchlist",
            re.IGNORECASE,
        )

        for match in watchlist_pattern.finditer(content):
            title = match.group(1).strip()
            year = int(match.group(2))
            title = self._clean_title(title)

            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(
                    ScrapedMovie(
                        title=title,
                        year=year,
                        source="rt",
                        url=url,
                    )
                )

        return movies

    def _parse_imdb_content(self, content: str, url: str) -> list[ScrapedMovie]:
        """Parse IMDB moviemeter page content."""
        movies: list[ScrapedMovie] = []
        seen_titles: set[str] = set()

        # Primary pattern: Markdown headers with IMDB links
        # Format: ### [Title](https://www.imdb.com/title/ttXXXXXXX/?ref_=chtmvm_t_N)
        header_pattern = re.compile(
            r"###\s*\[([^\]]{2,80})\]"  # ### [Title]
            r"\(https?://www\.imdb\.com/title/tt\d+/\?ref_=chtmvm_t_(\d+)\)",  # (url with rank)
        )

        for match in header_pattern.finditer(content):
            title = match.group(1).strip()
            rank = int(match.group(2))
            title = self._clean_title(title)

            # Only take top 100 movies
            if (
                rank <= 100
                and self._is_valid_title(title)
                and title.lower() not in seen_titles
            ):
                seen_titles.add(title.lower())
                movies.append(
                    ScrapedMovie(
                        title=title,
                        source="imdb",
                        url=url,
                        extra={"rank": rank},
                    )
                )

        # Fallback pattern: Simple markdown links to IMDB titles
        if not movies:
            link_pattern = re.compile(
                r"\[([^\]]{3,80})\]\(https?://www\.imdb\.com/title/tt\d+"
            )
            for match in link_pattern.finditer(content):
                title = match.group(1).strip()
                title = self._clean_title(title)
                if self._is_valid_title(title) and title.lower() not in seen_titles:
                    seen_titles.add(title.lower())
                    movies.append(
                        ScrapedMovie(
                            title=title,
                            source="imdb",
                            url=url,
                        )
                    )

        return movies

    def _parse_generic_content(self, content: str, url: str) -> list[ScrapedMovie]:
        """Generic parser for unknown page formats."""
        movies: list[ScrapedMovie] = []
        seen_titles: set[str] = set()

        # Look for common title (year) patterns
        for match in re.finditer(r"([A-Z][^(\n\[\]]{2,55}?)\s*\((\d{4})\)", content):
            title = match.group(1).strip()
            year = int(match.group(2))
            title = self._clean_title(title)

            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(
                    ScrapedMovie(
                        title=title,
                        year=year,
                        source="generic",
                        url=url,
                    )
                )

        return movies

    def _clean_title(self, title: str) -> str:
        """Clean up a movie title."""
        # Remove markdown formatting
        title = re.sub(r"\*\*|\*|__|_", "", title)
        # Remove trailing punctuation
        title = title.rstrip(".,;:-")
        # Normalize whitespace
        title = " ".join(title.split())
        return title.strip()

    def _is_valid_title(self, title: str) -> bool:
        """Check if a string looks like a valid movie title."""
        if len(title) < 2 or len(title) > 80:
            return False

        # Skip if it's mostly numbers or percentages
        if "%" in title:
            return False

        # Skip common non-title patterns
        invalid_patterns = [
            r"^\d+$",  # Just numbers
            r"^[A-Z]{2,}$",  # All caps abbreviations
            r"rating",
            r"score",
            r"review",
            r"trailer",
            r"watch now",
            r"stream",
            r"available",
        ]
        title_lower = title.lower()
        for pattern in invalid_patterns:
            if re.search(pattern, title_lower):
                return False

        return True


__all__ = ["Crawl4AIScraper"]
