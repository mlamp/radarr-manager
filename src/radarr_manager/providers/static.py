from __future__ import annotations

from datetime import date

from radarr_manager.models import MovieSuggestion


class StaticListProvider:
    """Returns a fixed list of blockbuster-style suggestions for local testing."""

    name = "static"

    async def discover(self, *, limit: int, region: str | None = None) -> list[MovieSuggestion]:
        suggestions = [
            MovieSuggestion(
                title="Atlas Rising",
                release_date=date.today(),
                overview="Prototype sci-fi thriller placeholder.",
                franchise="Atlas",
                confidence=0.4,
                sources=["static"],
            ),
            MovieSuggestion(
                title="Neon Heist",
                release_date=date.today(),
                overview="Stylized action set-piece placeholder.",
                confidence=0.35,
                sources=["static"],
            ),
        ]
        return suggestions[:limit]


__all__ = ["StaticListProvider"]
