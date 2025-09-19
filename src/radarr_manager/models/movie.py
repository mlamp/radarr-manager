from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class MovieSuggestion(BaseModel):
    """Normalized movie candidate emitted by discovery providers."""

    title: str
    release_date: date | None = None
    overview: str | None = None
    franchise: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }

    @property
    def year(self) -> int | None:
        """Convenience accessor for the release year."""
        return self.release_date.year if self.release_date else None


class SyncSummary(BaseModel):
    """Outcome of a synchronization attempt."""

    dry_run: bool
    queued: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def total_candidates(self) -> int:
        return len(self.queued) + len(self.skipped)
