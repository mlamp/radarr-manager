from __future__ import annotations

from typing import Protocol

from radarr_manager.models import MovieSuggestion


class MovieDiscoveryProvider(Protocol):
    """Protocol for discovery providers that emit blockbuster suggestions."""

    name: str

    async def discover(self, *, limit: int, region: str | None = None) -> list[MovieSuggestion]:
        """Return suggested movies sorted by relevance."""


class ProviderError(RuntimeError):
    """Raised when a provider fails to produce suggestions."""


__all__ = ["MovieDiscoveryProvider", "ProviderError"]
