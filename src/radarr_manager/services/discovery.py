from __future__ import annotations

from radarr_manager.models import MovieSuggestion
from radarr_manager.providers.base import MovieDiscoveryProvider


class DiscoveryService:
    """Coordinates movie discovery across providers."""

    def __init__(self, provider: MovieDiscoveryProvider, *, region: str | None = None) -> None:
        self._provider = provider
        self._region = region

    async def discover(self, *, limit: int) -> list[MovieSuggestion]:
        return await self._provider.discover(limit=limit, region=self._region)


__all__ = ["DiscoveryService"]
