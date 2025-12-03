"""Smart Validator Agent - validates and filters movie data using Python rules + optional LLM."""

from __future__ import annotations

import logging
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


class SmartValidatorAgent(SmartAgent):
    """
    Smart agent that validates and filters movie data.

    Capabilities:
    - Validates movie titles using rule-based filtering
    - Detects duplicates and merges sources
    - Filters based on configurable criteria
    - Returns structured report with valid/rejected movies

    Example tool call from orchestrator:
    ```json
    {
        "name": "validate_movies",
        "arguments": {
            "movies": [...],
            "deduplicate": true,
            "min_confidence": 0.5,
            "filter_tv_shows": true
        }
    }
    ```
    """

    agent_type = AgentType.VALIDATOR
    name = "validate_movies"
    description = (
        "Validate and filter a list of movies. "
        "Removes invalid titles (TV shows, collections, duplicates), "
        "merges duplicate entries, and applies quality filters."
    )

    def __init__(
        self,
        debug: bool = False,
    ) -> None:
        super().__init__(debug)

    async def execute(self, **kwargs: Any) -> AgentReport:
        """
        Validate and filter movies.

        Args:
            movies: List of MovieData dicts to validate
            deduplicate: Whether to merge duplicates (default: True)
            min_confidence: Minimum confidence threshold (default: 0.0)
            filter_tv_shows: Filter out TV show patterns (default: True)
            filter_collections: Filter out collection/franchise titles (default: True)

        Returns:
            AgentReport with validated movies and rejection breakdown
        """
        movies_data = kwargs.get("movies", [])
        deduplicate = kwargs.get("deduplicate", True)
        min_confidence = kwargs.get("min_confidence", 0.0)
        filter_tv_shows = kwargs.get("filter_tv_shows", True)
        filter_collections = kwargs.get("filter_collections", True)

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

            # Build report sections
            sections = [
                ReportSection(
                    heading="Validation Settings",
                    content=(
                        f"- Deduplicate: {deduplicate}\n"
                        f"- Min confidence: {min_confidence}\n"
                        f"- Filter TV shows: {filter_tv_shows}\n"
                        f"- Filter collections: {filter_collections}"
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
                    "rejection_breakdown": rejection_breakdown,
                },
                execution_time_ms=timer.elapsed_ms,
            )

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
            },
            "required": ["movies"],
        }


__all__ = ["SmartValidatorAgent"]
