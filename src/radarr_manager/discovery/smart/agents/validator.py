"""Smart Validator Agent - validates and filters movie data using Python rules + optional LLM."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from radarr_manager.discovery.smart.agents.base import SmartAgent, TimedExecution
from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    AgentType,
    MovieData,
    ReportSection,
    ReportStatus,
)
from radarr_manager.discovery.validation import (
    validate_title,
)

logger = logging.getLogger(__name__)

RE_RELEASE_THRESHOLD_YEARS = 2


class SmartValidatorAgent(SmartAgent):
    """
    Smart agent that validates and filters movie data.

    Capabilities:
    - Validates movie titles using rule-based filtering
    - Detects duplicates and merges sources
    - Filters based on configurable criteria
    - Enriches movies via Radarr lookup (optional)
    - Filters out movies already in library (optional)
    - Filters out re-releases (optional)
    - Returns structured report with valid/rejected movies

    Example tool call from orchestrator:
    ```json
    {
        "name": "validate_movies",
        "arguments": {
            "movies": [...],
            "deduplicate": true,
            "min_confidence": 0.5,
            "filter_tv_shows": true,
            "enrich": true,
            "filter_in_library": true,
            "filter_rereleases": true
        }
    }
    ```
    """

    agent_type = AgentType.VALIDATOR
    name = "validate_movies"
    description = (
        "Validate and filter a list of movies. "
        "Removes invalid titles (TV shows, collections, duplicates), "
        "merges duplicate entries, and applies quality filters. "
        "Can also enrich with Radarr data and filter out in-library movies and re-releases."
    )

    def __init__(
        self,
        radarr_base_url: str | None = None,
        radarr_api_key: str | None = None,
        debug: bool = False,
    ) -> None:
        super().__init__(debug)
        self._radarr_base_url = radarr_base_url
        self._radarr_api_key = radarr_api_key

    async def execute(self, **kwargs: Any) -> AgentReport:
        """
        Validate and filter movies.

        Args:
            movies: List of MovieData dicts to validate
            deduplicate: Whether to merge duplicates (default: True)
            min_confidence: Minimum confidence threshold (default: 0.0)
            filter_tv_shows: Filter out TV show patterns (default: True)
            filter_collections: Filter out collection/franchise titles (default: True)
            enrich: Enrich movies with Radarr lookup data (default: False)
            filter_in_library: Filter out movies already in Radarr library (default: False)
            filter_rereleases: Filter out re-releases of old movies (default: False)
            filter_foreign: Filter out non-English films unless exceptional (default: False)

        Returns:
            AgentReport with validated movies and rejection breakdown
        """
        movies_data = kwargs.get("movies", [])
        deduplicate = kwargs.get("deduplicate", True)
        min_confidence = kwargs.get("min_confidence", 0.0)
        filter_tv_shows = kwargs.get("filter_tv_shows", True)
        filter_collections = kwargs.get("filter_collections", True)
        enrich = kwargs.get("enrich", False)
        filter_in_library = kwargs.get("filter_in_library", False)
        filter_rereleases = kwargs.get("filter_rereleases", False)
        filter_foreign = kwargs.get("filter_foreign", False)

        if not movies_data:
            return self._create_failure_report("No movies provided for validation")

        self._log(f"Validating {len(movies_data)} movies")

        with TimedExecution() as timer:
            # Convert input to MovieData objects
            movies = self._parse_input_movies(movies_data)

            # Track statistics
            total_input = len(movies)
            rejection_breakdown: dict[str, int] = {}

            # Phase 1: Title validation
            valid_movies: list[MovieData] = []
            rejected_movies: list[MovieData] = []

            for movie in movies:
                # Validate title - returns ValidationResult object
                validation_result = validate_title(movie.title, strict=filter_tv_shows)

                if not validation_result.is_valid:
                    movie.is_valid = False
                    reason_value = (
                        validation_result.reason.value if validation_result.reason else "unknown"
                    )
                    movie.rejection_reason = reason_value
                    rejection_breakdown[reason_value] = rejection_breakdown.get(reason_value, 0) + 1
                    rejected_movies.append(movie)
                elif filter_collections and self._is_collection(movie.title):
                    movie.is_valid = False
                    movie.rejection_reason = "collection"
                    rejection_breakdown["collection"] = rejection_breakdown.get("collection", 0) + 1
                    rejected_movies.append(movie)
                elif movie.confidence < min_confidence:
                    movie.is_valid = False
                    movie.rejection_reason = "low_confidence"
                    rejection_breakdown["low_confidence"] = (
                        rejection_breakdown.get("low_confidence", 0) + 1
                    )
                    rejected_movies.append(movie)
                else:
                    valid_movies.append(movie)

            self._log(
                f"Title validation: {len(valid_movies)} valid, {len(rejected_movies)} rejected"
            )

            # Phase 2: Deduplication
            duplicates_merged = 0
            if deduplicate and valid_movies:
                valid_movies, duplicates_merged = self._deduplicate(valid_movies)
                self._log(
                    f"Deduplication: merged {duplicates_merged}, {len(valid_movies)} unique"
                )

            # Phase 3: Enrichment and library/re-release/foreign filtering
            in_library_count = 0
            rerelease_count = 0
            foreign_count = 0
            if enrich and self._has_radarr and valid_movies:
                (
                    valid_movies,
                    in_library_count,
                    rerelease_count,
                    foreign_count,
                    enrichment_rejected,
                ) = await self._enrich_and_filter(
                    valid_movies,
                    filter_in_library=filter_in_library,
                    filter_rereleases=filter_rereleases,
                    filter_foreign=filter_foreign,
                )
                rejected_movies.extend(enrichment_rejected)
                if in_library_count > 0:
                    rejection_breakdown["in_library"] = in_library_count
                if rerelease_count > 0:
                    rejection_breakdown["rerelease"] = rerelease_count
                if foreign_count > 0:
                    rejection_breakdown["foreign"] = foreign_count
                self._log(
                    f"Enrichment: {in_library_count} in library, {rerelease_count} re-releases, "
                    f"{foreign_count} foreign, {len(valid_movies)} remaining"
                )

            # Build report sections
            sections = [
                ReportSection(
                    heading="Validation Settings",
                    content=(
                        f"- Deduplicate: {deduplicate}\n"
                        f"- Min confidence: {min_confidence}\n"
                        f"- Filter TV shows: {filter_tv_shows}\n"
                        f"- Filter collections: {filter_collections}\n"
                        f"- Enrich from Radarr: {enrich}\n"
                        f"- Filter in-library: {filter_in_library}\n"
                        f"- Filter re-releases: {filter_rereleases}\n"
                        f"- Filter foreign: {filter_foreign}"
                    ),
                ),
            ]

            if rejection_breakdown:
                breakdown_lines = "\n".join(
                    f"- {k}: {v}"
                    for k, v in sorted(rejection_breakdown.items(), key=lambda x: -x[1])
                )
                sections.append(
                    ReportSection(
                        heading="Rejection Breakdown",
                        content=breakdown_lines,
                    )
                )

            # Sample of rejected movies for debugging
            if rejected_movies:
                rejected_sample = rejected_movies[:5]
                rejected_lines = "\n".join(
                    f"- {m.title}: {m.rejection_reason}" for m in rejected_sample
                )
                if len(rejected_movies) > 5:
                    rejected_lines += f"\n- ... and {len(rejected_movies) - 5} more"
                sections.append(
                    ReportSection(
                        heading="Rejected Movies (sample)",
                        content=rejected_lines,
                    )
                )

            return AgentReport(
                agent_type=self.agent_type,
                agent_name=self.name,
                status=ReportStatus.SUCCESS,
                summary=(
                    f"Validated {total_input} movies: "
                    f"{len(valid_movies)} valid, {len(rejected_movies)} rejected"
                ),
                sections=sections,
                movies=valid_movies,
                stats={
                    "total_input": total_input,
                    "valid_count": len(valid_movies),
                    "rejected_count": len(rejected_movies),
                    "duplicates_merged": duplicates_merged,
                    "in_library_filtered": in_library_count,
                    "rereleases_filtered": rerelease_count,
                    "foreign_filtered": foreign_count,
                    "rejection_breakdown": rejection_breakdown,
                },
                execution_time_ms=timer.elapsed_ms,
            )

    @property
    def _has_radarr(self) -> bool:
        """Check if Radarr client can be created."""
        return bool(self._radarr_base_url and self._radarr_api_key)

    async def _enrich_and_filter(
        self,
        movies: list[MovieData],
        filter_in_library: bool = True,
        filter_rereleases: bool = True,
        filter_foreign: bool = False,
    ) -> tuple[list[MovieData], int, int, int, list[MovieData]]:
        """
        Enrich movies with Radarr lookup data and filter based on criteria.

        Foreign films are filtered unless they're exceptional (IMDB 8.0+ AND 20k+ votes).

        Returns:
            Tuple of (valid_movies, in_library_count, rerelease_count, foreign_count, rejected)
        """
        from radarr_manager.clients.radarr import RadarrClient

        valid: list[MovieData] = []
        rejected: list[MovieData] = []
        in_library_count = 0
        rerelease_count = 0
        foreign_count = 0
        current_year = datetime.now().year

        async with RadarrClient(
            base_url=self._radarr_base_url,
            api_key=self._radarr_api_key,
        ) as client:
            for movie in movies:
                try:
                    results = await client.lookup_movie(movie.title)
                    if not results:
                        valid.append(movie)
                        continue

                    lookup = results[0]
                    radarr_id = lookup.get("id")
                    in_library = radarr_id is not None
                    actual_year = lookup.get("year")
                    is_rerelease = (
                        actual_year is not None
                        and actual_year < (current_year - RE_RELEASE_THRESHOLD_YEARS)
                    )

                    # Extract original language
                    original_language = lookup.get("originalLanguage", {})
                    original_language_name = (
                        original_language.get("name") if original_language else None
                    )
                    is_foreign = original_language_name and original_language_name != "English"

                    # Update movie metadata with enrichment data
                    movie.metadata["tmdb_id"] = lookup.get("tmdbId")
                    movie.metadata["imdb_id"] = lookup.get("imdbId")
                    movie.metadata["radarr_id"] = radarr_id
                    movie.metadata["in_library"] = in_library
                    movie.metadata["actual_year"] = actual_year
                    movie.metadata["is_rerelease"] = is_rerelease
                    movie.metadata["original_language"] = original_language_name
                    movie.metadata["is_foreign"] = is_foreign

                    # Extract ratings
                    ratings = lookup.get("ratings", {})
                    imdb_data = ratings.get("imdb", {})
                    imdb_rating = None
                    imdb_votes = 0
                    if imdb_data:
                        if imdb_data.get("value"):
                            imdb_rating = round(imdb_data["value"], 1)
                            movie.ratings["imdb_rating"] = imdb_rating
                        if imdb_data.get("votes"):
                            imdb_votes = imdb_data["votes"]
                            movie.ratings["imdb_votes"] = imdb_votes

                    rt_data = ratings.get("rottenTomatoes", {})
                    if rt_data and rt_data.get("value"):
                        movie.metadata["rt_critics_score"] = int(rt_data["value"])

                    mc_data = ratings.get("metacritic", {})
                    if mc_data and mc_data.get("value"):
                        movie.metadata["metacritic_score"] = int(mc_data["value"])

                    # Check if foreign film is exceptional (8.0+ IMDB AND 20k+ votes)
                    is_exceptional_foreign = (
                        imdb_rating is not None
                        and imdb_rating >= 8.0
                        and imdb_votes >= 20000
                    )

                    # Filter based on criteria
                    if filter_in_library and in_library:
                        movie.is_valid = False
                        movie.rejection_reason = "in_library"
                        in_library_count += 1
                        rejected.append(movie)
                        self._log(f"Filtered (in library): {movie.title}")
                    elif filter_rereleases and is_rerelease:
                        movie.is_valid = False
                        movie.rejection_reason = "rerelease"
                        rerelease_count += 1
                        rejected.append(movie)
                        self._log(f"Filtered (re-release from {actual_year}): {movie.title}")
                    elif filter_foreign and is_foreign and not is_exceptional_foreign:
                        movie.is_valid = False
                        movie.rejection_reason = "foreign"
                        foreign_count += 1
                        rejected.append(movie)
                        self._log(
                            f"Filtered (foreign '{original_language_name}'): {movie.title}"
                        )
                    else:
                        valid.append(movie)

                except Exception as exc:
                    logger.warning(f"Failed to enrich {movie.title}: {exc}")
                    valid.append(movie)

        return valid, in_library_count, rerelease_count, foreign_count, rejected

    def _parse_input_movies(self, movies_data: list[Any]) -> list[MovieData]:
        """Parse input movies from various formats."""
        movies: list[MovieData] = []
        for item in movies_data:
            if isinstance(item, MovieData):
                movies.append(item)
            elif isinstance(item, dict):
                movies.append(MovieData.from_dict(item))
            elif hasattr(item, "to_dict"):
                movies.append(MovieData.from_dict(item.to_dict()))
        return movies

    def _is_collection(self, title: str) -> bool:
        """Check if title appears to be a collection rather than a single movie."""
        title_lower = title.lower()
        collection_patterns = [
            "collection",
            "complete series",
            "trilogy",
            "quadrilogy",
            "box set",
            "anthology",
            "marathon",
            "double feature",
        ]
        return any(pattern in title_lower for pattern in collection_patterns)

    def _deduplicate(self, movies: list[MovieData]) -> tuple[list[MovieData], int]:
        """
        Deduplicate movies by title, merging sources.

        Returns:
            Tuple of (deduplicated movies, count of duplicates merged)
        """
        seen: dict[str, MovieData] = {}
        duplicates_merged = 0

        for movie in movies:
            key = movie.title.lower().strip()

            if key in seen:
                existing = seen[key]
                # Merge sources
                for source in movie.sources:
                    if source not in existing.sources:
                        existing.sources.append(source)
                # Take higher confidence
                if movie.confidence > existing.confidence:
                    existing.confidence = movie.confidence
                # Take year if missing
                if movie.year and not existing.year:
                    existing.year = movie.year
                # Merge metadata
                existing.metadata.update(movie.metadata)
                duplicates_merged += 1
            else:
                seen[key] = movie

        return list(seen.values()), duplicates_merged

    def _get_parameters_schema(self) -> dict[str, Any]:
        """Get the JSON schema for validate_movies parameters."""
        return {
            "type": "object",
            "properties": {
                "movies": {
                    "type": "array",
                    "description": "List of movies to validate",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "year": {"type": ["integer", "null"]},
                            "overview": {"type": ["string", "null"]},
                            "confidence": {"type": "number"},
                            "sources": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title"],
                    },
                },
                "deduplicate": {
                    "type": "boolean",
                    "description": "Whether to merge duplicate entries",
                    "default": True,
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum confidence threshold (0-1)",
                    "default": 0.0,
                },
                "filter_tv_shows": {
                    "type": "boolean",
                    "description": "Filter out TV show patterns",
                    "default": True,
                },
                "filter_collections": {
                    "type": "boolean",
                    "description": "Filter out collection/franchise titles",
                    "default": True,
                },
                "enrich": {
                    "type": "boolean",
                    "description": "Enrich movies with Radarr lookup data (ratings, IDs)",
                    "default": False,
                },
                "filter_in_library": {
                    "type": "boolean",
                    "description": "Filter out movies already in Radarr library",
                    "default": False,
                },
                "filter_rereleases": {
                    "type": "boolean",
                    "description": "Filter out re-releases of old movies (requires enrich=true)",
                    "default": False,
                },
                "filter_foreign": {
                    "type": "boolean",
                    "description": "Filter non-English films unless exceptional (8.0+, 20k+ votes)",
                    "default": False,
                },
            },
            "required": ["movies"],
        }


__all__ = ["SmartValidatorAgent"]
