"""Analysis Agent - Python validation + optional LLM enhancement."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from radarr_manager.discovery.agents.base import (
    Agent,
    AgentMessage,
    AgentResult,
    AgentStatus,
)
from radarr_manager.discovery.parsers import ParsedMovie
from radarr_manager.discovery.validation import (
    RejectionReason,
    ValidatedMovie,
    validate_movie_list,
)

logger = logging.getLogger(__name__)


@dataclass
class AnalysisRequest(AgentMessage):
    """Request for analysis of movie candidates."""

    movies: list[ParsedMovie] = field(default_factory=list)
    limit: int = 50
    criteria: str = ""  # Custom criteria from prompt
    region: str = "US"
    enhance_with_llm: bool = True  # Whether to use LLM for enhancement
    strict_validation: bool = False  # Strict Python validation rules


@dataclass
class AnalyzedMovie:
    """Movie after analysis (validation + optional enhancement)."""

    title: str
    year: int | None = None
    overview: str | None = None
    confidence: float = 0.8
    sources: list[str] = field(default_factory=list)
    is_valid: bool = True
    rejection_reason: str | None = None


@dataclass
class AnalysisResult(AgentResult):
    """Result of analysis."""

    movies: list[AnalyzedMovie] = field(default_factory=list)
    total_input: int = 0
    validated_count: int = 0
    rejected_count: int = 0
    enhanced_count: int = 0
    rejection_breakdown: dict[str, int] = field(default_factory=dict)


class AnalysisAgent(Agent[AnalysisRequest, AnalysisResult]):
    """
    Agent that validates and enhances movie suggestions.

    Two-phase approach:
    1. Python validation: Apply rule-based filtering (red flags, invalid patterns)
    2. LLM enhancement (optional): Add plot overviews, adjust confidence

    This approach:
    - Uses fast, deterministic Python rules for filtering garbage
    - Reserves expensive LLM calls for value-add enhancement
    - Provides clear rejection reasons for debugging
    """

    name = "analysis"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        provider: str = "openai",
        debug: bool = False,
    ) -> None:
        super().__init__(debug)
        self._api_key = api_key
        self._model = model
        self._provider = provider

    async def execute(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Analyze movie candidates: validate with Python, enhance with LLM.

        Flow:
        1. Python validation pass - filter out invalid titles
        2. Deduplication - merge duplicate titles, combine sources
        3. LLM enhancement pass (optional) - add overviews, adjust confidence
        """
        if not request.movies:
            return AnalysisResult(
                agent_id=self.name,
                status=AgentStatus.SUCCESS,
                total_input=0,
            )

        total_input = len(request.movies)
        self._log(f"Analyzing {total_input} movie candidates")

        # Phase 1: Python validation + deduplication
        validated, rejected = validate_movie_list(
            request.movies,
            strict=request.strict_validation,
            deduplicate=True,
        )

        # Build rejection breakdown
        rejection_breakdown: dict[str, int] = {}
        for r in rejected:
            reason_name = r.reason.value if isinstance(r.reason, RejectionReason) else str(r.reason)
            rejection_breakdown[reason_name] = rejection_breakdown.get(reason_name, 0) + 1

        self._log(f"Python validation: {len(validated)} valid, {len(rejected)} rejected")
        if rejection_breakdown:
            self._log(f"Rejection breakdown: {rejection_breakdown}")

        # Phase 2: Convert to AnalyzedMovie with base confidence
        analyzed = self._build_analyzed_movies(validated)

        # Phase 3: LLM enhancement (optional)
        enhanced_count = 0
        if request.enhance_with_llm and self._api_key and analyzed:
            # Only enhance movies that need overviews
            needs_enhancement = [m for m in analyzed if not m.overview]

            if needs_enhancement:
                self._log(f"Enhancing {len(needs_enhancement)} movies with LLM")
                try:
                    enhanced = await self._llm_enhance(
                        needs_enhancement,
                        request.criteria,
                        request.region,
                    )
                    enhanced_count = len(enhanced)

                    # Merge enhanced data back
                    enhanced_lookup = {m.title.lower(): m for m in enhanced}
                    merge_count = 0
                    for movie in analyzed:
                        key = movie.title.lower()
                        if key in enhanced_lookup:
                            enh = enhanced_lookup[key]
                            movie.overview = enh.overview or movie.overview
                            movie.confidence = enh.confidence
                            if enh.year and not movie.year:
                                movie.year = enh.year
                            merge_count += 1

                    if self._debug:
                        self._log(f"Merged {merge_count} enhanced movies back")
                        # Sample of movies with overviews
                        with_overview = [m for m in analyzed if m.overview]
                        if with_overview:
                            self._log(f"Movies with overviews: {len(with_overview)}")

                except Exception as exc:
                    logger.warning(f"[ANALYSIS] LLM enhancement failed: {exc}")
                    # Continue without enhancement - validation already done

        self._log(f"Analysis complete: {len(analyzed)} movies, {enhanced_count} enhanced")

        # Sort by confidence then source count
        analyzed.sort(key=lambda m: (-m.confidence, -len(m.sources), m.title))

        return AnalysisResult(
            agent_id=self.name,
            movies=analyzed[: request.limit],
            total_input=total_input,
            validated_count=len(validated),
            rejected_count=len(rejected),
            enhanced_count=enhanced_count,
            rejection_breakdown=rejection_breakdown,
            status=AgentStatus.SUCCESS,
        )

    def _build_analyzed_movies(self, validated: list[ValidatedMovie]) -> list[AnalyzedMovie]:
        """Convert validated movies to analyzed movies with confidence scores."""
        analyzed: list[AnalyzedMovie] = []

        for movie in validated:
            # Calculate base confidence from source count and data completeness
            confidence = self._calculate_confidence(movie)

            analyzed.append(
                AnalyzedMovie(
                    title=movie.title,
                    year=movie.year,
                    overview=movie.overview,
                    confidence=confidence,
                    sources=movie.sources or [],
                    is_valid=True,
                )
            )

        return analyzed

    def _calculate_confidence(self, movie: ValidatedMovie) -> float:
        """
        Calculate confidence score based on data quality signals.

        Factors:
        - Number of sources (more sources = higher confidence)
        - Has year (more complete data)
        - Has overview (more complete data)
        - Source quality (scraped > llm_web_search)
        """
        base = 0.6

        # Source count bonus (up to +0.2)
        source_count = len(movie.sources) if movie.sources else 1
        source_bonus = min(0.2, source_count * 0.05)

        # Data completeness bonus
        completeness_bonus = 0.0
        if movie.year:
            completeness_bonus += 0.05
        if movie.overview:
            completeness_bonus += 0.05

        # Source quality bonus
        quality_bonus = 0.0
        if movie.sources:
            # Scraped sources are more reliable
            scraped_sources = [s for s in movie.sources if not s.startswith("llm")]
            if scraped_sources:
                quality_bonus = 0.1

        confidence = base + source_bonus + completeness_bonus + quality_bonus
        return min(0.95, round(confidence, 2))

    async def _llm_enhance(
        self,
        movies: list[AnalyzedMovie],
        criteria: str,
        region: str,
    ) -> list[AnalyzedMovie]:
        """
        Use LLM to enhance movies with plot overviews.

        Note: This does NOT validate - that's already done with Python rules.
        LLM is only used to add value (overviews, year confirmation).
        """
        # Build movie list for prompt
        movie_list = "\n".join(
            f"- {m.title}" + (f" ({m.year})" if m.year else "")
            for m in movies[:50]  # Cap at 50 for token limits
        )

        criteria_text = f"\nContext: {criteria}" if criteria else ""

        system_prompt = (
            "You are a movie database assistant. For each movie in the list, "
            "provide a brief plot overview (1-2 sentences) and confirm the release year.\n\n"
            f"Region: {region}\n"
            f"{criteria_text}\n\n"
            "IMPORTANT: Return a JSON object with a 'movies' key containing an array:\n"
            '{"movies": [\n'
            '  {"title": "Movie Title", "year": 2024, "overview": "Brief plot summary."},\n'
            '  {"title": "Another Movie", "year": 2025, "overview": "Another summary."}\n'
            "]}\n\n"
            "Include ALL movies from the input list. "
            "If you don't recognize a movie, set overview to null but still include it."
        )

        user_prompt = f"Add plot overviews for these movies:\n\n{movie_list}"

        # Call LLM
        response = await self._call_llm(system_prompt, user_prompt)

        # Parse response
        return self._parse_enhancement_response(response, movies)

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM API."""
        if self._provider != "openai":
            raise ValueError(f"Unsupported LLM provider: {self._provider}")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]

    def _parse_enhancement_response(
        self,
        response: str,
        original_movies: list[AnalyzedMovie],
    ) -> list[AnalyzedMovie]:
        """Parse LLM enhancement response."""
        try:
            data = json.loads(response)

            # Handle various response formats
            if isinstance(data, list):
                movies_data = data
            elif isinstance(data, dict):
                if self._debug:
                    self._log(f"LLM response keys: {list(data.keys())}")

                # Try common keys
                movies_data = (
                    data.get("movies")
                    or data.get("results")
                    or data.get("data")
                    or data.get("movie_list")
                    or data.get("enhanced_movies")
                    or []
                )

                # If still empty, check if dict values are lists of movies
                if not movies_data:
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            if isinstance(value[0], dict) and "title" in value[0]:
                                movies_data = value
                                if self._debug:
                                    self._log(f"Found movies under key: {key}")
                                break

                # If still empty but dict has title key, it might be a single movie
                if not movies_data and "title" in data:
                    movies_data = [data]
            else:
                movies_data = []

            if self._debug:
                self._log(f"LLM returned {len(movies_data)} movie entries")

            # Build lookup from original (normalize for matching)
            original_lookup: dict[str, AnalyzedMovie] = {}
            for m in original_movies:
                # Store with multiple key variants for fuzzy matching
                key = m.title.lower().strip()
                original_lookup[key] = m
                # Also store without "the " prefix
                if key.startswith("the "):
                    original_lookup[key[4:]] = m

            enhanced: list[AnalyzedMovie] = []
            matched = 0
            for item in movies_data:
                if not isinstance(item, dict):
                    continue

                title = item.get("title", "")
                key = title.lower().strip()

                # Try to find original with flexible matching
                original = original_lookup.get(key)
                if not original and key.startswith("the "):
                    original = original_lookup.get(key[4:])

                if not original:
                    continue

                matched += 1
                # Create enhanced version
                enhanced.append(
                    AnalyzedMovie(
                        title=original.title,  # Use original title for consistency
                        year=item.get("year") or original.year,
                        overview=item.get("overview"),
                        confidence=min(0.95, original.confidence + 0.05),
                        sources=original.sources,
                        is_valid=True,
                    )
                )

            if self._debug:
                self._log(f"Matched {matched} movies from LLM response")

            return enhanced

        except json.JSONDecodeError as exc:
            logger.warning(f"[ANALYSIS] Failed to parse LLM response: {exc}")
            return []
        except Exception as exc:
            logger.warning(f"[ANALYSIS] Error parsing enhancement response: {exc}")
            return []


def analyzed_to_suggestion(movie: AnalyzedMovie) -> Any:
    """Convert AnalyzedMovie to MovieSuggestion."""
    from radarr_manager.models.movie import MovieSuggestion

    release_date = date(movie.year, 1, 1) if movie.year else None

    return MovieSuggestion(
        title=movie.title,
        release_date=release_date,
        overview=movie.overview,
        confidence=movie.confidence,
        sources=movie.sources,
    )


__all__ = [
    "AnalysisAgent",
    "AnalysisRequest",
    "AnalysisResult",
    "AnalyzedMovie",
    "analyzed_to_suggestion",
]
