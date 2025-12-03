"""Hybrid discovery provider combining scraper reliability with LLM intelligence."""

from __future__ import annotations

import logging
from typing import Any

from radarr_manager.models import MovieSuggestion
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError
from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.scrapers.base import ScrapedMovie, ScraperProvider

logger = logging.getLogger(__name__)


class HybridDiscoveryProvider(MovieDiscoveryProvider):
    """
    Hybrid discovery that combines web scraping with LLM enrichment.

    Flow:
    1. Scraper reliably fetches movie titles from RT/IMDB pages
    2. OpenAI adds additional discoveries + enriches with overviews
    3. Results are deduplicated and merged
    """

    name = "hybrid"

    def __init__(
        self,
        *,
        scraper: ScraperProvider,
        openai_provider: OpenAIProvider | None = None,
        debug: bool = False,
    ) -> None:
        self._scraper = scraper
        self._openai = openai_provider
        self._debug = debug

    async def discover(
        self, *, limit: int, region: str | None = None
    ) -> list[MovieSuggestion]:
        """
        Discover movies using hybrid scraper + LLM approach.

        1. Scrape titles from RT/IMDB for reliability
        2. Optionally use OpenAI to add more discoveries
        3. Merge and deduplicate results
        """
        if self._debug:
            logger.info("[HYBRID] Starting hybrid discovery...")

        # Step 1: Get reliable titles from scraper
        scraped_movies = await self._scrape_titles()

        if self._debug:
            logger.info(f"[HYBRID] Scraper found {len(scraped_movies)} movies")

        # Step 2: Get additional discoveries from OpenAI (if available)
        openai_suggestions: list[MovieSuggestion] = []
        if self._openai:
            try:
                openai_suggestions = await self._openai.discover(
                    limit=limit, region=region
                )
                if self._debug:
                    logger.info(
                        f"[HYBRID] OpenAI found {len(openai_suggestions)} movies"
                    )
            except ProviderError as exc:
                if self._debug:
                    logger.warning(f"[HYBRID] OpenAI discovery failed: {exc}")
                # Continue with just scraped movies

        # Step 3: Convert scraped movies to suggestions
        scraped_suggestions = [
            self._scraped_to_suggestion(movie) for movie in scraped_movies
        ]

        # Step 4: Merge and deduplicate (OpenAI suggestions take precedence for metadata)
        merged = self._merge_suggestions(scraped_suggestions, openai_suggestions)

        if self._debug:
            logger.info(f"[HYBRID] Merged result: {len(merged)} unique movies")
            for idx, s in enumerate(merged[:10], 1):
                source_info = s.sources[0] if s.sources else "unknown"
                logger.info(
                    f"[HYBRID]   {idx}. {s.title} ({s.year or 'TBA'}) "
                    f"[{source_info}] confidence: {s.confidence:.2f}"
                )

        return merged

    async def _scrape_titles(self) -> list[ScrapedMovie]:
        """Scrape movie titles from all configured sources."""
        try:
            return await self._scraper.discover_all()
        except Exception as exc:
            if self._debug:
                logger.warning(f"[HYBRID] Scraper error: {exc}")
            return []

    def _scraped_to_suggestion(self, movie: ScrapedMovie) -> MovieSuggestion:
        """Convert a scraped movie to a MovieSuggestion."""
        # Build release date from year if available
        release_date = f"{movie.year}-01-01" if movie.year else None

        return MovieSuggestion(
            title=movie.title,
            release_date=release_date,
            overview=None,  # Will be enriched later via Radarr lookup
            franchise=None,
            confidence=0.85,  # Scraped titles are reliable
            sources=[f"scraper:{movie.source}"],
        )

    def _merge_suggestions(
        self,
        scraped: list[MovieSuggestion],
        openai: list[MovieSuggestion],
    ) -> list[MovieSuggestion]:
        """
        Merge scraped and OpenAI suggestions, deduplicating by title.

        OpenAI suggestions take precedence when there's a match because
        they include richer metadata (overview, franchise, etc.).
        """
        result: list[MovieSuggestion] = []
        seen_titles: set[str] = set()

        # First, add all OpenAI suggestions (they have richer metadata)
        for suggestion in openai:
            normalized = self._normalize_title(suggestion.title)
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                result.append(suggestion)

        # Then add scraped suggestions that weren't found by OpenAI
        for suggestion in scraped:
            normalized = self._normalize_title(suggestion.title)
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                # Mark as scraper-exclusive discovery
                suggestion = MovieSuggestion(
                    title=suggestion.title,
                    release_date=suggestion.release_date,
                    overview=suggestion.overview,
                    franchise=suggestion.franchise,
                    confidence=0.80,  # Slightly lower since OpenAI didn't find it
                    sources=["scraper-exclusive"] + suggestion.sources,
                )
                result.append(suggestion)

        return result

    def _normalize_title(self, title: str) -> str:
        """Normalize a movie title for comparison."""
        # Lowercase, remove common suffixes, strip punctuation
        normalized = title.lower().strip()

        # Remove common suffixes that might differ between sources
        suffixes_to_remove = [
            "(2024)",
            "(2025)",
            "(2026)",
            ": part one",
            ": part two",
            " - part 1",
            " - part 2",
        ]
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()

        # Remove special characters for fuzzy matching
        normalized = "".join(c for c in normalized if c.isalnum() or c.isspace())
        normalized = " ".join(normalized.split())  # Normalize whitespace

        return normalized


__all__ = ["HybridDiscoveryProvider"]
