"""Enrichment service for fetching ratings data from Radarr."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from radarr_manager.clients.radarr import RadarrClient
from radarr_manager.models import MovieSuggestion

logger = logging.getLogger(__name__)

# Movies older than this many years are flagged as re-releases
RE_RELEASE_THRESHOLD_YEARS = 2


class EnrichmentService:
    """Service for enriching movie suggestions with ratings data from Radarr."""

    def __init__(self, client: RadarrClient, *, debug: bool = False) -> None:
        self._client = client
        self._debug = debug

    async def enrich_suggestions(
        self, suggestions: list[MovieSuggestion]
    ) -> list[MovieSuggestion]:
        """
        Enrich movie suggestions with ratings data from Radarr lookup.

        For each suggestion, looks up the movie in Radarr and extracts:
        - IMDb rating and vote count
        - Rotten Tomatoes critics and audience scores
        - Metacritic score
        - TMDB ID and IMDb ID

        Returns new MovieSuggestion objects with enriched metadata.
        """
        enriched = []
        for movie in suggestions:
            enriched_movie = await self._enrich_single(movie)
            enriched.append(enriched_movie)
        return enriched

    async def _enrich_single(self, movie: MovieSuggestion) -> MovieSuggestion:
        """Enrich a single movie suggestion with Radarr data."""
        try:
            results = await self._client.lookup_movie(movie.title)
            if not results:
                if self._debug:
                    logger.info(f"[ENRICH] No Radarr results for: {movie.title}")
                return movie

            # Find best match (first result is usually best)
            lookup = results[0]
            ratings = lookup.get("ratings", {})

            # Extract ratings from Radarr's format
            metadata = self._extract_ratings(ratings, lookup)

            if self._debug:
                imdb_str = f"{metadata.get('imdb_rating')}/10" if metadata.get("imdb_rating") else "N/A"
                imdb_votes = metadata.get("imdb_votes") or 0
                rt_critics = metadata.get("rt_critics_score")
                rt_audience = metadata.get("rt_audience_score")
                metacritic = metadata.get("metacritic_score")
                in_library = metadata.get("in_library", False)
                is_rerelease = metadata.get("is_rerelease", False)
                actual_year = metadata.get("actual_year")
                tags = []
                if in_library:
                    tags.append("IN LIBRARY")
                if is_rerelease:
                    tags.append(f"RE-RELEASE from {actual_year}")
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                logger.info(
                    f"[ENRICH] {movie.title}: IMDb {imdb_str} ({imdb_votes:,} votes), "
                    f"RT {rt_critics or 'N/A'}%/{rt_audience or 'N/A'}%, MC {metacritic or 'N/A'}{tag_str}"
                )

            # Return new MovieSuggestion with enriched metadata
            return MovieSuggestion(
                title=movie.title,
                release_date=movie.release_date,
                overview=movie.overview,
                franchise=movie.franchise,
                confidence=movie.confidence,
                sources=movie.sources,
                metadata=metadata,
            )

        except Exception as exc:
            if self._debug:
                logger.warning(f"[ENRICH] Failed to enrich {movie.title}: {exc}")
            return movie

    def _extract_ratings(
        self, ratings: dict[str, Any], lookup: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract ratings from Radarr's ratings structure."""
        # Check if movie is already in Radarr library
        # If 'id' is present and non-None, movie exists in library
        radarr_id = lookup.get("id")
        in_library = radarr_id is not None

        # Get actual release year from TMDB data
        actual_year = lookup.get("year")
        current_year = datetime.now().year

        # Detect re-releases: movies where actual year is significantly older
        is_rerelease = False
        if actual_year and actual_year < (current_year - RE_RELEASE_THRESHOLD_YEARS):
            is_rerelease = True

        # Extract original language for regional cinema detection
        original_language = lookup.get("originalLanguage", {})
        original_language_name = original_language.get("name") if original_language else None

        metadata: dict[str, Any] = {
            "tmdb_id": lookup.get("tmdbId"),
            "imdb_id": lookup.get("imdbId"),
            "radarr_id": radarr_id,
            "in_library": in_library,
            "actual_year": actual_year,
            "is_rerelease": is_rerelease,
            "original_language": original_language_name,
            "imdb_rating": None,
            "imdb_votes": None,
            "rt_critics_score": None,
            "rt_audience_score": None,
            "metacritic_score": None,
        }

        # IMDb
        imdb_data = ratings.get("imdb", {})
        if imdb_data:
            value = imdb_data.get("value")
            if value and value > 0:
                metadata["imdb_rating"] = round(value, 1)
            votes = imdb_data.get("votes")
            if votes and votes > 0:
                metadata["imdb_votes"] = votes

        # Rotten Tomatoes
        rt_data = ratings.get("rottenTomatoes", {})
        if rt_data:
            value = rt_data.get("value")
            if value and value > 0:
                metadata["rt_critics_score"] = int(value)

        # Note: Radarr doesn't provide RT audience score separately
        # It might be available in some API responses but not consistently

        # Metacritic
        mc_data = ratings.get("metacritic", {})
        if mc_data:
            value = mc_data.get("value")
            if value and value > 0:
                metadata["metacritic_score"] = int(value)

        return metadata


__all__ = ["EnrichmentService"]
