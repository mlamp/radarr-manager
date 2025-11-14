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
        if not dry_run and (self._quality_profile_id is None or self._root_folder_path is None):
            raise RuntimeError(
                "quality_profile_id and root_folder_path must be configured for live sync operations",
            )

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

            # Always use title-based lookup instead of trusting LLM-provided IDs
            # LLMs frequently hallucinate TMDB/IMDB IDs, leading to wrong movie matches
            # Radarr's search API handles fuzzy matching and returns authoritative IDs
            lookup_candidates = await self._client.lookup_movie(suggestion.title)

            if not lookup_candidates:
                skipped.append(suggestion.title)
                continue

            # Prefer candidates that match the suggested year (fuzzy matching)
            # If suggestion has a year, prioritize results within 1 year tolerance
            lookup = None
            if suggestion.year and lookup_candidates:
                for candidate in lookup_candidates:
                    candidate_year = candidate.get("year")
                    if candidate_year and abs(int(candidate_year) - int(suggestion.year)) <= 1:
                        lookup = candidate
                        break

            # Fall back to first result if no year match found
            if not lookup:
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

            # In dry-run mode, just track as queued without actually adding
            if dry_run:
                queued.append(suggestion.title)
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

        return SyncSummary(dry_run=dry_run, queued=queued, skipped=skipped, errors=errors)


__all__ = ["SyncService"]
