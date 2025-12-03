"""Pydantic schemas for MCP tool parameters and responses."""

from typing import Any

from pydantic import BaseModel, Field

# Tool Parameter Schemas


class SearchMovieParams(BaseModel):
    """Parameters for search_movie tool."""

    title: str = Field(..., description="Movie title to search for")
    year: int | None = Field(None, description="Release year for better accuracy")


class AddMovieParams(BaseModel):
    """Parameters for add_movie tool."""

    title: str | None = Field(None, description="Movie title to search for")
    year: int | None = Field(None, description="Release year")
    tmdb_id: int | None = Field(None, description="TMDB ID (e.g., 123456)")
    imdb_id: str | None = Field(None, description="IMDB ID (e.g., tt1234567)")
    force: bool = Field(False, description="Bypass quality gate")
    deep_analysis: bool = Field(True, description="Enable quality analysis")
    quality_threshold: float = Field(
        5.0, ge=0.0, le=10.0, description="Minimum quality score (0-10)"
    )
    dry_run: bool = Field(True, description="Preview without modifying Radarr")
    search_on_add: bool = Field(True, description="Automatically search for movie after adding")


class AnalyzeQualityParams(BaseModel):
    """Parameters for analyze_quality tool."""

    title: str = Field(..., description="Movie title")
    year: int | None = Field(None, description="Release year")
    tmdb_id: int | None = Field(None, description="TMDB ID")


class DiscoverMoviesParams(BaseModel):
    """Parameters for discover_movies tool."""

    limit: int = Field(10, ge=1, le=50, description="Number of movies to discover")
    region: str | None = Field(None, description="Region for discovery (e.g., 'US')")


class SyncMoviesParams(BaseModel):
    """Parameters for sync_movies tool."""

    limit: int = Field(10, ge=1, le=50, description="Number of movies to sync")
    dry_run: bool = Field(True, description="Preview without modifying Radarr")
    deep_analysis: bool = Field(True, description="Enable quality analysis")


# Tool Response Schemas


class SearchMovieResponse(BaseModel):
    """Response from search_movie tool."""

    exists: bool = Field(..., description="Whether movie exists in Radarr")
    movie: dict[str, Any] | None = Field(None, description="Movie details if exists")
    message: str = Field(..., description="Human-readable message")


class QualityAnalysisResponse(BaseModel):
    """Quality analysis details."""

    overall_score: float = Field(..., description="Overall quality score (0-10)")
    threshold: float | None = Field(None, description="Quality threshold used")
    passed: bool = Field(..., description="Whether quality check passed")
    recommendation: str = Field(..., description="Recommendation text")
    ratings: dict[str, Any] = Field(..., description="Source ratings breakdown")
    red_flags: list[str] = Field(default_factory=list, description="Quality concerns")


class AddMovieResponse(BaseModel):
    """Response from add_movie tool."""

    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Human-readable message")
    error: str | None = Field(None, description="Error type if failed")
    movie: dict[str, Any] = Field(default_factory=dict, description="Movie details")
    quality_analysis: QualityAnalysisResponse | None = Field(
        None, description="Quality analysis if deep_analysis enabled"
    )
    can_override: bool = Field(False, description="Can override with force flag")
    override_instructions: str | None = Field(None, description="How to override")
    warning: str | None = Field(None, description="Warning message")


class MovieSuggestion(BaseModel):
    """Movie suggestion from discovery."""

    title: str = Field(..., description="Movie title")
    year: int | None = Field(None, description="Release year")
    tmdb_id: int | None = Field(None, description="TMDB ID")
    imdb_id: str | None = Field(None, description="IMDB ID")
    reason: str | None = Field(None, description="Why this movie was suggested")
    quality_score: float | None = Field(None, description="Quality score if analyzed")


class DiscoverMoviesResponse(BaseModel):
    """Response from discover_movies tool."""

    success: bool = Field(..., description="Whether operation succeeded")
    movies: list[MovieSuggestion] = Field(default_factory=list, description="Discovered movies")
    count: int = Field(..., description="Number of movies found")
    message: str = Field(..., description="Human-readable message")


class SyncResult(BaseModel):
    """Result from syncing a single movie."""

    title: str = Field(..., description="Movie title")
    year: int | None = Field(None, description="Release year")
    status: str = Field(..., description="Status: added, exists, skipped, error")
    reason: str | None = Field(None, description="Reason for status")
    quality_score: float | None = Field(None, description="Quality score if analyzed")


class SyncMoviesResponse(BaseModel):
    """Response from sync_movies tool."""

    success: bool = Field(..., description="Whether operation succeeded")
    results: list[SyncResult] = Field(default_factory=list, description="Sync results")
    summary: dict[str, int] = Field(default_factory=dict, description="Summary counts by status")
    message: str = Field(..., description="Human-readable message")
