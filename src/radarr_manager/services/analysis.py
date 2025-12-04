"""Deep analysis service for per-movie quality evaluation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from radarr_manager.models import MovieSuggestion

logger = logging.getLogger(__name__)


@dataclass
class MovieAnalysis:
    """Comprehensive analysis result for a single movie."""

    movie: MovieSuggestion
    quality_score: float
    recommendation: str
    red_flags: list[str]
    strengths: list[str]
    rating_details: dict[str, Any]
    should_add: bool


MAJOR_FRANCHISES = {
    "marvel",
    "mcu",
    "marvel cinematic universe",
    "dc",
    "dceu",
    "dc extended universe",
    "dc universe",
    "disney",
    "pixar",
    "star wars",
    "harry potter",
    "wizarding world",
    "fast & furious",
    "fast and furious",
    "jurassic",
    "jurassic world",
    "jurassic park",
    "transformers",
    "mission impossible",
    "james bond",
    "007",
    "avatar",
    "lord of the rings",
    "hobbit",
    "batman",
    "superman",
    "spider-man",
    "spiderman",
    "x-men",
    "avengers",
    "guardians of the galaxy",
    "toy story",
    "incredibles",
    "minions",
    "despicable me",
    "shrek",
    "kung fu panda",
    "how to train your dragon",
    "frozen",
    "moana",
    "john wick",
    "planet of the apes",
    "godzilla",
    "monsterverse",
    "conjuring",
    "knives out",
    "paddington",
    "spongebob",
}


class DeepAnalysisService:
    """Service for performing deep per-movie quality analysis."""

    def __init__(self, *, debug: bool = False) -> None:
        self._debug = debug

    def _is_major_franchise(self, movie: MovieSuggestion) -> bool:
        """Check if movie belongs to a major franchise."""
        if not movie.franchise:
            return False
        franchise_lower = movie.franchise.lower()
        # Check if franchise name matches or contains a major franchise keyword
        return any(major in franchise_lower for major in MAJOR_FRANCHISES)

    async def analyze_movie(self, movie: MovieSuggestion) -> MovieAnalysis:
        """
        Perform deep analysis on a single movie.

        Evaluates:
        - Multi-source rating validation (RT, IMDb, Metacritic)
        - Rating confidence (vote counts, score consistency)
        - Red flag detection (low votes, score gaps, etc.)
        - Quality assessment based on comprehensive criteria

        Returns MovieAnalysis with recommendation and quality score.
        """
        metadata = movie.metadata or {}

        # Extract ratings
        imdb_rating = metadata.get("imdb_rating")
        imdb_votes = metadata.get("imdb_votes", 0)
        rt_critics = metadata.get("rt_critics_score")
        rt_audience = metadata.get("rt_audience_score")
        metacritic = metadata.get("metacritic_score")

        if self._debug:
            logger.info(f"[DEEP ANALYSIS] Analyzing: {movie.title}")
            imdb_str = f"{imdb_rating}/10" if imdb_rating is not None else "N/A"
            imdb_votes_str = f"{imdb_votes:,}" if imdb_votes else "0"
            rt_critics_str = f"{rt_critics}%" if rt_critics is not None else "N/A"
            rt_audience_str = f"{rt_audience}%" if rt_audience is not None else "N/A"
            metacritic_str = str(metacritic) if metacritic is not None else "N/A"
            logger.info(
                f"  IMDb: {imdb_str} ({imdb_votes_str} votes), "
                f"RT: {rt_critics_str} critics / {rt_audience_str} audience, "
                f"Metacritic: {metacritic_str}"
            )

        is_major_franchise = self._is_major_franchise(movie)
        red_flags = self._detect_red_flags(movie, metadata, is_major_franchise)
        strengths = self._identify_strengths(movie, metadata, is_major_franchise)
        quality_score = self._calculate_quality_score(
            metadata, red_flags, strengths, is_major_franchise
        )
        rating_details = self._build_rating_details(metadata)

        # Determine recommendation
        recommendation = self._generate_recommendation(movie, quality_score, red_flags, strengths)

        # Decision: should we add this movie?
        # Reject re-releases (old movies getting theatrical re-runs)
        is_rerelease = metadata.get("is_rerelease", False)
        if is_rerelease:
            should_add = False
            actual_year = metadata.get("actual_year")
            red_flags.append(f"Re-release of {actual_year} film - not a new movie")
        else:
            should_add = quality_score >= 6.0 and len(red_flags) <= 2

        if self._debug:
            logger.info(f"  Quality Score: {quality_score:.1f}/10")
            logger.info(f"  Recommendation: {recommendation}")
            logger.info(f"  Red Flags: {len(red_flags)}")
            logger.info(f"  Decision: {'✓ ADD' if should_add else '✗ SKIP'}")

        return MovieAnalysis(
            movie=movie,
            quality_score=quality_score,
            recommendation=recommendation,
            red_flags=red_flags,
            strengths=strengths,
            rating_details=rating_details,
            should_add=should_add,
        )

    def _detect_red_flags(
        self, movie: MovieSuggestion, metadata: dict[str, Any], is_major_franchise: bool
    ) -> list[str]:
        """Detect quality red flags that might indicate a poor movie."""
        flags = []

        imdb_rating = metadata.get("imdb_rating")
        imdb_votes = metadata.get("imdb_votes") or 0  # Handle None explicitly
        rt_critics = metadata.get("rt_critics_score")
        rt_audience = metadata.get("rt_audience_score")
        metacritic = metadata.get("metacritic_score")

        # Low vote count = unreliable rating
        if imdb_votes and imdb_votes < 1000:
            flags.append(f"Very low IMDb vote count ({imdb_votes:,}) - rating unreliable")
        elif imdb_votes and imdb_votes < 5000:
            flags.append(f"Low IMDb vote count ({imdb_votes:,}) - limited audience data")

        # Poor ratings - more lenient thresholds for major franchises
        # Major franchises: IMDb >= 5.0, RT >= 25%, Metacritic >= 35
        # Regular movies: IMDb >= 6.0, RT >= 40%, Metacritic >= 50
        imdb_threshold = 5.0 if is_major_franchise else 6.0
        rt_threshold = 25 if is_major_franchise else 40
        metacritic_threshold = 35 if is_major_franchise else 50

        if imdb_rating and imdb_rating < imdb_threshold:
            flags.append(f"Low IMDb rating ({imdb_rating}/10)")

        if rt_critics is not None and rt_critics < rt_threshold:
            flags.append(f"Poor RT critics score ({rt_critics}%)")

        if rt_audience is not None and rt_audience < 50:
            flags.append(f"Poor RT audience score ({rt_audience}%)")

        if metacritic is not None and metacritic < metacritic_threshold:
            flags.append(f"Poor Metacritic score ({metacritic}/100)")

        # Large critic/audience gap (> 30 points)
        if rt_critics is not None and rt_audience is not None:
            gap = abs(rt_critics - rt_audience)
            if gap > 30:
                flags.append(f"Large RT critic/audience gap ({gap} points) - divisive reception")

        # No ratings available at all
        if not any([imdb_rating, rt_critics, rt_audience, metacritic]):
            flags.append("No ratings available - unreleased or unreviewed")

        # Critics-only with no audience data - unreliable for general appeal
        if rt_critics is not None and rt_audience is None and (not imdb_votes or imdb_votes < 1000):
            flags.append("Critics-only rating - no audience data to confirm general appeal")

        return flags

    def _identify_strengths(
        self, movie: MovieSuggestion, metadata: dict[str, Any], is_major_franchise: bool
    ) -> list[str]:
        """Identify quality strengths that indicate a good movie."""
        strengths = []

        imdb_rating = metadata.get("imdb_rating")
        imdb_votes = metadata.get("imdb_votes") or 0  # Handle None explicitly
        rt_critics = metadata.get("rt_critics_score")
        rt_audience = metadata.get("rt_audience_score")
        metacritic = metadata.get("metacritic_score")

        # High confidence rating
        if imdb_votes and imdb_votes > 50000:
            strengths.append(f"High IMDb vote count ({imdb_votes:,}) - reliable rating")

        # Strong ratings
        if imdb_rating and imdb_rating >= 7.5:
            strengths.append(f"Excellent IMDb rating ({imdb_rating}/10)")
        elif imdb_rating and imdb_rating >= 7.0:
            strengths.append(f"Good IMDb rating ({imdb_rating}/10)")

        if rt_critics is not None and rt_critics >= 80:
            strengths.append(f"Certified Fresh on RT ({rt_critics}% critics)")
        elif rt_critics is not None and rt_critics >= 70:
            strengths.append(f"Fresh on RT ({rt_critics}% critics)")

        if rt_audience is not None and rt_audience >= 80:
            strengths.append(f"Strong audience approval ({rt_audience}% RT audience)")

        if metacritic is not None and metacritic >= 75:
            strengths.append(f"Strong Metacritic score ({metacritic}/100)")

        # Consensus across sources
        if (
            rt_critics is not None
            and rt_audience is not None
            and abs(rt_critics - rt_audience) < 10
        ):
            strengths.append("Critics and audience agree on quality")

        # High confidence from provider
        if movie.confidence >= 0.85:
            strengths.append(f"High discovery confidence ({movie.confidence:.0%})")

        # Major franchise bonus
        if is_major_franchise:
            strengths.append(f"Major franchise ({movie.franchise}) - relaxed quality thresholds")
        elif movie.franchise:
            strengths.append(f"Part of {movie.franchise} franchise")

        return strengths

    def _calculate_quality_score(
        self,
        metadata: dict[str, Any],
        red_flags: list[str],
        strengths: list[str],
        is_major_franchise: bool,
    ) -> float:
        """
        Calculate overall quality score (0-10) based on multi-source ratings.

        Weighs RT scores more heavily than IMDb as requested by user.
        Major franchises get a baseline boost to account for critic/audience splits.
        """
        scores = []

        imdb_rating = metadata.get("imdb_rating")
        imdb_votes = metadata.get("imdb_votes") or 0  # Handle None explicitly
        rt_critics = metadata.get("rt_critics_score")
        rt_audience = metadata.get("rt_audience_score")
        metacritic = metadata.get("metacritic_score")

        # RT Critics Score (highest weight: 35%)
        if rt_critics is not None:
            scores.append(("rt_critics", rt_critics / 10, 0.35))

        # RT Audience Score (second highest: 30%)
        if rt_audience is not None:
            scores.append(("rt_audience", rt_audience / 10, 0.30))

        # Metacritic (20%)
        if metacritic is not None:
            scores.append(("metacritic", metacritic / 10, 0.20))

        # IMDb (lowest weight: 15%, but adjust for vote count confidence)
        if imdb_rating is not None:
            weight = 0.15
            # Reduce weight if low vote count
            if imdb_votes < 1000:
                weight *= 0.5
            elif imdb_votes < 5000:
                weight *= 0.75
            scores.append(("imdb", imdb_rating, weight))

        if not scores:
            # No ratings available - use provider confidence as fallback
            # Major franchises get benefit of the doubt
            return 6.0 if is_major_franchise else 5.0

        # Normalize weights to sum to 1.0
        total_weight = sum(weight for _, _, weight in scores)
        normalized_scores = [(name, score, weight / total_weight) for name, score, weight in scores]

        # Calculate weighted average
        quality_score = sum(score * weight for _, score, weight in normalized_scores)

        # Penalize sparse data - if we have fewer than 2 rating sources, cap the max score
        # A movie with only critics score shouldn't be "highly recommended"
        num_sources = len(scores)
        if num_sources == 1:
            quality_score = min(quality_score, 6.5)  # Cap at "GOOD" level
        elif num_sources == 2:
            # If missing audience data entirely, also cap
            has_audience_data = rt_audience is not None or (imdb_votes and imdb_votes >= 1000)
            if not has_audience_data:
                quality_score = min(quality_score, 7.0)  # Cap at "RECOMMENDED" level

        # Apply penalties for red flags
        penalty = min(len(red_flags) * 0.5, 3.0)
        quality_score = max(0, quality_score - penalty)

        # Apply bonus for strengths
        bonus = min(len(strengths) * 0.2, 2.0)
        quality_score = min(10, quality_score + bonus)

        # Major franchise bonus: +1.5 to help offset typical critic/audience splits
        if is_major_franchise:
            quality_score = min(10, quality_score + 1.5)

        return round(quality_score, 1)

    def _build_rating_details(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Build detailed rating breakdown for display."""
        return {
            "imdb_rating": metadata.get("imdb_rating"),
            "imdb_votes": metadata.get("imdb_votes"),
            "rt_critics_score": metadata.get("rt_critics_score"),
            "rt_audience_score": metadata.get("rt_audience_score"),
            "metacritic_score": metadata.get("metacritic_score"),
        }

    def _generate_recommendation(
        self,
        movie: MovieSuggestion,
        quality_score: float,
        red_flags: list[str],
        strengths: list[str],
    ) -> str:
        """Generate human-readable recommendation text."""
        if quality_score >= 8.0:
            return "HIGHLY RECOMMENDED - Excellent quality across all metrics"
        elif quality_score >= 7.0:
            return "RECOMMENDED - Strong quality, worth adding"
        elif quality_score >= 6.0:
            return "GOOD - Above average, suitable for library"
        elif quality_score >= 5.0:
            return "MIXED - Some concerns, review manually"
        else:
            return "NOT RECOMMENDED - Quality concerns, likely skip"


__all__ = ["DeepAnalysisService", "MovieAnalysis"]
