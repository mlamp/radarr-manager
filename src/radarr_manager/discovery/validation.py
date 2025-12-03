"""Movie title validation and filtering rules.

This module provides shared validation logic used by both parsers (during scraping)
and the AnalysisAgent (during analysis). It extracts patterns that indicate
non-movie content and applies consistent filtering rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RejectionReason(str, Enum):
    """Reason why a title was rejected."""

    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    CONTAINS_PERCENTAGE = "contains_percentage"
    ONLY_NUMBERS = "only_numbers"
    ALL_CAPS_SHORT = "all_caps_short"
    UI_ELEMENT = "ui_element"
    RATING_TEXT = "rating_text"
    NAVIGATION_TEXT = "navigation_text"
    PROMOTIONAL_TEXT = "promotional_text"
    STREAMING_TEXT = "streaming_text"
    GENERIC_PLACEHOLDER = "generic_placeholder"
    YEAR_ONLY = "year_only"
    DUPLICATE = "duplicate"


@dataclass
class ValidationResult:
    """Result of validating a movie title."""

    is_valid: bool
    title: str
    reason: RejectionReason | None = None
    cleaned_title: str | None = None


# Patterns that indicate UI elements, not movie titles
UI_ELEMENT_PATTERNS = [
    r"^(menu|nav|header|footer|sidebar|button|link|icon)$",
    r"^(close|open|expand|collapse|show|hide|toggle)$",
    r"^(next|prev|previous|back|forward|more|less)$",
    r"^(loading|please wait|processing)$",
    r"^(sign in|log in|sign up|register|subscribe)$",
    r"^(search|filter|sort|view all|see all|see more)$",
]

# Patterns that indicate rating/review text
RATING_PATTERNS = [
    r"\d+%",  # Percentage ratings
    r"rating",
    r"score",
    r"review",
    r"critic",
    r"audience",
    r"tomatometer",
    r"popcornmeter",
    r"metascore",
    r"imdb rating",
    r"rotten|fresh|certified",
    r"stars?(\s+out\s+of)?",
    r"^\d+(\.\d+)?\/\d+$",  # X/10 format
]

# Patterns that indicate navigation/promotional text
NAVIGATION_PATTERNS = [
    r"^(home|about|contact|help|faq|support)$",
    r"^(terms|privacy|policy|copyright|disclaimer)$",
    r"^(advertise|careers|press|investors)$",
    r"trailer",
    r"teaser",
    r"clip",
    r"behind the scenes",
    r"featurette",
    r"interview",
    r"red carpet",
]

# Patterns that indicate streaming/availability text
STREAMING_PATTERNS = [
    r"watch now",
    r"stream",
    r"available",
    r"rent",
    r"buy",
    r"subscribe",
    r"free trial",
    r"premium",
    r"coming soon",
    r"in theaters",
    r"on demand",
    r"digital",
    r"blu-ray",
    r"dvd",
]

# Patterns that indicate generic/placeholder text
GENERIC_PATTERNS = [
    r"^(untitled|unknown|tba|tbd|n/a)$",
    r"^movie\s*\d*$",
    r"^film\s*\d*$",
    r"^title\s*\d*$",
    r"^new\s+(movie|film|release)$",
    r"^(top|best|popular)\s+(movies?|films?)$",
]

# Combined invalid patterns for quick check
ALL_INVALID_PATTERNS = (
    UI_ELEMENT_PATTERNS
    + RATING_PATTERNS
    + NAVIGATION_PATTERNS
    + STREAMING_PATTERNS
    + GENERIC_PATTERNS
)


def clean_title(title: str) -> str:
    """Clean up a movie title by removing formatting artifacts."""
    # Remove markdown formatting
    title = re.sub(r"\*\*|\*|__|_", "", title)
    # Remove trailing punctuation
    title = title.rstrip(".,;:-")
    # Normalize whitespace
    title = " ".join(title.split())
    return title.strip()


def validate_title(title: str, *, strict: bool = False) -> ValidationResult:
    """
    Validate a movie title using rule-based checks.

    Args:
        title: The title to validate
        strict: If True, apply stricter validation rules

    Returns:
        ValidationResult with is_valid flag and rejection reason if invalid
    """
    # Clean the title first
    cleaned = clean_title(title)
    original = title

    # Length checks
    if len(cleaned) < 2:
        return ValidationResult(
            is_valid=False,
            title=original,
            reason=RejectionReason.TOO_SHORT,
            cleaned_title=cleaned,
        )

    if len(cleaned) > 80:
        return ValidationResult(
            is_valid=False,
            title=original,
            reason=RejectionReason.TOO_LONG,
            cleaned_title=cleaned,
        )

    # Percentage in title (usually rating artifacts)
    if "%" in cleaned:
        return ValidationResult(
            is_valid=False,
            title=original,
            reason=RejectionReason.CONTAINS_PERCENTAGE,
            cleaned_title=cleaned,
        )

    title_lower = cleaned.lower()

    # Only numbers
    if re.match(r"^\d+$", cleaned):
        return ValidationResult(
            is_valid=False,
            title=original,
            reason=RejectionReason.ONLY_NUMBERS,
            cleaned_title=cleaned,
        )

    # Short all-caps (usually abbreviations, not titles)
    if re.match(r"^[A-Z]{2,4}$", cleaned):
        return ValidationResult(
            is_valid=False,
            title=original,
            reason=RejectionReason.ALL_CAPS_SHORT,
            cleaned_title=cleaned,
        )

    # Year only (e.g., "2024", "2025")
    if re.match(r"^(19|20)\d{2}$", cleaned):
        return ValidationResult(
            is_valid=False,
            title=original,
            reason=RejectionReason.YEAR_ONLY,
            cleaned_title=cleaned,
        )

    # Check against pattern categories
    for pattern in UI_ELEMENT_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return ValidationResult(
                is_valid=False,
                title=original,
                reason=RejectionReason.UI_ELEMENT,
                cleaned_title=cleaned,
            )

    for pattern in RATING_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return ValidationResult(
                is_valid=False,
                title=original,
                reason=RejectionReason.RATING_TEXT,
                cleaned_title=cleaned,
            )

    for pattern in NAVIGATION_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return ValidationResult(
                is_valid=False,
                title=original,
                reason=RejectionReason.NAVIGATION_TEXT,
                cleaned_title=cleaned,
            )

    for pattern in STREAMING_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return ValidationResult(
                is_valid=False,
                title=original,
                reason=RejectionReason.STREAMING_TEXT,
                cleaned_title=cleaned,
            )

    for pattern in GENERIC_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return ValidationResult(
                is_valid=False,
                title=original,
                reason=RejectionReason.GENERIC_PLACEHOLDER,
                cleaned_title=cleaned,
            )

    # Strict mode additional checks
    if strict:
        # Require title to start with capital letter or number
        if not re.match(r"^[A-Z0-9]", cleaned):
            return ValidationResult(
                is_valid=False,
                title=original,
                reason=RejectionReason.GENERIC_PLACEHOLDER,
                cleaned_title=cleaned,
            )

    # Title is valid
    return ValidationResult(
        is_valid=True,
        title=original,
        cleaned_title=cleaned,
    )


def is_valid_title(title: str) -> bool:
    """Simple boolean check for title validity."""
    return validate_title(title).is_valid


@dataclass
class ValidatedMovie:
    """A movie that has passed validation."""

    title: str
    year: int | None = None
    source: str = ""
    confidence: float = 0.8
    sources: list[str] | None = None
    overview: str | None = None
    extra: dict | None = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = [self.source] if self.source else []


@dataclass
class RejectedMovie:
    """A movie that failed validation."""

    title: str
    reason: RejectionReason
    source: str = ""


def validate_movie_list(
    movies: list,
    *,
    strict: bool = False,
    deduplicate: bool = True,
) -> tuple[list[ValidatedMovie], list[RejectedMovie]]:
    """
    Validate a list of parsed movies.

    Args:
        movies: List of ParsedMovie objects
        strict: Apply strict validation rules
        deduplicate: Remove duplicate titles

    Returns:
        Tuple of (validated_movies, rejected_movies)
    """
    validated: list[ValidatedMovie] = []
    rejected: list[RejectedMovie] = []
    seen_titles: set[str] = set()

    for movie in movies:
        title = getattr(movie, "title", str(movie))
        year = getattr(movie, "year", None)
        source = getattr(movie, "source", "unknown")
        extra = getattr(movie, "extra", None)

        # Validate title
        result = validate_title(title, strict=strict)

        if not result.is_valid:
            rejected.append(
                RejectedMovie(
                    title=title,
                    reason=result.reason,
                    source=source,
                )
            )
            continue

        # Use cleaned title
        clean = result.cleaned_title or title
        key = clean.lower()

        # Deduplication
        if deduplicate and key in seen_titles:
            # Find existing and merge sources
            for v in validated:
                if v.title.lower() == key:
                    if source and source not in v.sources:
                        v.sources.append(source)
                    # Update year if we have it and existing doesn't
                    if year and not v.year:
                        v.year = year
                    break
            continue

        seen_titles.add(key)

        # Extract overview from extra if available
        overview = None
        if extra and isinstance(extra, dict):
            overview = extra.get("overview")

        validated.append(
            ValidatedMovie(
                title=clean,
                year=year,
                source=source,
                sources=[source] if source else [],
                overview=overview,
                extra=extra,
            )
        )

    # Sort by source count (more sources = higher confidence)
    validated.sort(key=lambda m: -len(m.sources))

    return validated, rejected


__all__ = [
    "RejectionReason",
    "ValidationResult",
    "ValidatedMovie",
    "RejectedMovie",
    "clean_title",
    "validate_title",
    "is_valid_title",
    "validate_movie_list",
]
