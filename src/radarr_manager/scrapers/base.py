"""Base class for web scraping providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScrapedMovie:
    """A movie discovered via web scraping."""

    title: str
    source: str
    year: int | None = None
    url: str | None = None
    extra: dict = field(default_factory=dict)


class ScraperError(Exception):
    """Raised when scraping fails."""

    pass


class ScraperProvider(ABC):
    """Base class for web scraping providers."""

    name: str = "base"

    @abstractmethod
    async def scrape_movies(self, url: str) -> list[ScrapedMovie]:
        """
        Scrape movie titles from a URL.

        Args:
            url: The URL to scrape (e.g., RT in-theaters page)

        Returns:
            List of ScrapedMovie objects with titles and metadata

        Raises:
            ScraperError: If scraping fails
        """
        pass

    async def discover_all(self) -> list[ScrapedMovie]:
        """
        Scrape movies from all configured sources.

        Returns combined results from RT and IMDB pages.
        """
        sources = [
            (
                "https://www.rottentomatoes.com/browse/movies_in_theaters/sort:popular",
                "rt_theaters",
            ),
            (
                "https://www.rottentomatoes.com/browse/movies_at_home/sort:popular",
                "rt_home",
            ),
            ("https://www.imdb.com/chart/moviemeter/", "imdb_meter"),
        ]

        all_movies: list[ScrapedMovie] = []
        seen_titles: set[str] = set()

        for url, source_name in sources:
            try:
                movies = await self.scrape_movies(url)
                for movie in movies:
                    # Deduplicate by normalized title
                    normalized = movie.title.lower().strip()
                    if normalized not in seen_titles:
                        seen_titles.add(normalized)
                        movie.source = source_name
                        all_movies.append(movie)
            except ScraperError:
                # Log but continue with other sources
                continue

        return all_movies


__all__ = ["ScraperProvider", "ScrapedMovie", "ScraperError"]
