"""Enrichment service for fetching ratings data from Radarr."""

from __future__ import annotations

import logging
from typing import Any

from radarr_manager.clients.radarr import RadarrClient
from radarr_manager.models import MovieSuggestion

logger = logging.getLogger(__name__)


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
                logger.info(
                    f"[ENRICH] {movie.title}: IMDb {imdb_str} ({imdb_votes:,} votes), "
                    f"RT {rt_critics or 'N/A'}%/{rt_audience or 'N/A'}%, MC {metacritic or 'N/A'}"
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
        metadata: dict[str, Any] = {
            "tmdb_id": lookup.get("tmdbId"),
            "imdb_id": lookup.get("imdbId"),
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
