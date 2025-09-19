from __future__ import annotations

from typing import Iterable

import httpx

from radarr_manager.clients.radarr import RadarrClient, build_add_movie_payload
from radarr_manager.models import MovieSuggestion, SyncSummary


class SyncService:
    """Coordinates discovery results with Radarr movie ingestion."""

    def __init__(
        self,
        client: RadarrClient,
        *,
        quality_profile_id: int | None,
        root_folder_path: str | None,
        monitor: bool,
        minimum_availability: str | None,
        tags: Iterable[str] | None,
    ) -> None:
        self._client = client
        self._quality_profile_id = quality_profile_id
        self._root_folder_path = root_folder_path
        self._monitor = monitor
        self._minimum_availability = minimum_availability
        self._tags = list(tags or [])

    async def sync(self, suggestions: list[MovieSuggestion], *, dry_run: bool, force: bool) -> SyncSummary:
        if dry_run:
            queued = [suggestion.title for suggestion in suggestions]
            return SyncSummary(dry_run=True, queued=queued)

        if self._quality_profile_id is None or self._root_folder_path is None:
            raise RuntimeError(
                "quality_profile_id and root_folder_path must be configured for live sync operations",
            )

        if not force:
            # TODO: integrate duplicate detection before insert operations.
            pass

        queued: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        existing_movies = await self._client.list_movies()
        existing_tmdb_ids: set[int] = set()
        for movie in existing_movies:
            tmdb_raw = movie.get("tmdbId")
            try:
                if tmdb_raw is not None:
                    existing_tmdb_ids.add(int(tmdb_raw))
            except (TypeError, ValueError):  # defensive guard for unexpected payloads
                continue

        for suggestion in suggestions:
            if suggestion.year is None:
                skipped.append(suggestion.title)
                continue

            # Try TMDB/IMDB ID lookup first if available in metadata
            lookup_candidates = []
            if suggestion.metadata:
                tmdb_id = suggestion.metadata.get("tmdb_id")
                imdb_id = suggestion.metadata.get("imdb_id")

                if tmdb_id:
                    lookup_candidates = await self._client.lookup_movie(f"tmdb:{tmdb_id}")
                elif imdb_id:
                    lookup_candidates = await self._client.lookup_movie(f"imdb:{imdb_id}")

            # Fall back to title search if no ID lookup or no results
            if not lookup_candidates:
                lookup_candidates = await self._client.lookup_movie(suggestion.title)

            if not lookup_candidates:
                skipped.append(suggestion.title)
                continue

            lookup = lookup_candidates[0]
            lookup_year = lookup.get("year")
            if lookup_year in {None, 0, "", "0000"}:
                skipped.append(suggestion.title)
                continue

            tmdb_id = lookup.get("tmdbId")
            try:
                tmdb_int = int(tmdb_id) if tmdb_id is not None else None
            except (TypeError, ValueError):
                tmdb_int = None

            if tmdb_int is not None and not force and tmdb_int in existing_tmdb_ids:
                skipped.append(suggestion.title)
                continue

            payload = build_add_movie_payload(
                lookup=lookup,
                quality_profile_id=self._quality_profile_id,
                root_folder_path=self._root_folder_path,
                monitor=self._monitor,
                minimum_availability=self._minimum_availability,
                tags=self._tags,
            )
            try:
                await self._client.ensure_movie(payload)
            except httpx.HTTPStatusError as exc:
                try:
                    error_details = exc.response.json()
                except ValueError:  # response was not JSON
                    error_details = exc.response.text
                errors.append(
                    f"{suggestion.title}: {exc} — {error_details}",
                )
            except Exception as exc:  # pragma: no cover - best-effort logging path
                errors.append(f"{suggestion.title}: {exc}")
                continue

            queued.append(suggestion.title)
            if tmdb_int is not None:
                existing_tmdb_ids.add(tmdb_int)

        return SyncSummary(dry_run=False, queued=queued, skipped=skipped, errors=errors)


__all__ = ["SyncService"]
