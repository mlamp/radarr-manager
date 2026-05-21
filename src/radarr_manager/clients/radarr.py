from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT = 30.0
LIST_MOVIES_TIMEOUT = 120.0  # Large libraries can take a while
USER_AGENT = "radarr-manager/0.1.0"
RECENT_TITLES_SAMPLE_SIZE = 50

logger = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy library matching."""
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    return " ".join(cleaned.split())


@dataclass(frozen=True)
class LibraryIndex:
    """Snapshot of a Radarr library used to short-circuit per-title API lookups.

    Lookups use a two-tier policy enforced by ``is_owned``:
      1. If a TMDB id is supplied and present, the title is owned.
      2. Else if both title AND year are supplied and the normalized (title, year)
         tuple is present, the title is owned.
      3. Otherwise return False — title-without-year never matches, so the
         existing per-title Radarr lookup remains the source of truth for that case.
    """

    tmdb_ids: frozenset[int]
    title_year_keys: frozenset[tuple[str, int]]
    recent_titles: tuple[str, ...]
    total_count: int

    def is_owned(
        self,
        *,
        title: str | None = None,
        year: int | None = None,
        tmdb_id: int | None = None,
    ) -> bool:
        if tmdb_id is not None and tmdb_id in self.tmdb_ids:
            return True
        if title and year is not None:
            key = (_normalize_title(title), year)
            if key in self.title_year_keys:
                return True
        return False

    @classmethod
    def empty(cls) -> LibraryIndex:
        return cls(
            tmdb_ids=frozenset(),
            title_year_keys=frozenset(),
            recent_titles=(),
            total_count=0,
        )

    @classmethod
    def from_movies(cls, movies: list[Mapping[str, Any]]) -> LibraryIndex:
        tmdb_ids: set[int] = set()
        title_year_keys: set[tuple[str, int]] = set()
        for movie in movies:
            tmdb = movie.get("tmdbId")
            if isinstance(tmdb, int) and tmdb > 0:
                tmdb_ids.add(tmdb)
            title = movie.get("title")
            year = movie.get("year")
            if isinstance(title, str) and title and isinstance(year, int) and year > 0:
                title_year_keys.add((_normalize_title(title), year))

        def _added_sort_key(movie: Mapping[str, Any]) -> datetime:
            added = movie.get("added")
            if isinstance(added, str) and added:
                try:
                    return datetime.fromisoformat(added.replace("Z", "+00:00"))
                except ValueError:
                    return datetime.min
            return datetime.min

        ordered = sorted(movies, key=_added_sort_key, reverse=True)
        recent: list[str] = []
        for movie in ordered:
            title = movie.get("title")
            if isinstance(title, str) and title:
                recent.append(title)
            if len(recent) >= RECENT_TITLES_SAMPLE_SIZE:
                break

        return cls(
            tmdb_ids=frozenset(tmdb_ids),
            title_year_keys=frozenset(title_year_keys),
            recent_titles=tuple(recent),
            total_count=len(movies),
        )


async def build_library_index(client: RadarrClient) -> LibraryIndex:
    """Snapshot the Radarr library; on any failure return an empty index.

    Caller can always rely on a usable LibraryIndex — agents that consume it
    treat an empty index as "no upstream filter available" and fall back to
    per-title Radarr lookups.
    """
    try:
        movies = await client.list_movies()
    except Exception as exc:
        logger.warning("Failed to build library index: %s; proceeding without it", exc)
        return LibraryIndex.empty()
    return LibraryIndex.from_movies(movies)


class RadarrClient:
    """Thin asynchronous wrapper around the Radarr v3 API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        # Ensure base_url includes /api/v3 for Radarr v3 API
        normalized_url = base_url.rstrip("/")
        if not normalized_url.endswith("/api/v3"):
            normalized_url = f"{normalized_url}/api/v3"

        headers = {
            "X-Api-Key": api_key,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=normalized_url,
            headers=headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> Mapping[str, Any]:
        return await self._get_json("/system/status")

    async def lookup_movie(self, term: str) -> list[dict[str, Any]]:
        params = {"term": term}
        response = await self._client.get("/movie/lookup", params=params)
        response.raise_for_status()
        return response.json()

    async def lookup_movie_by_tmdb(self, tmdb_id: int) -> list[dict[str, Any]]:
        """Lookup movie by TMDB ID.

        Args:
            tmdb_id: The Movie Database ID

        Returns:
            List of movie results (usually 1 item)
        """
        return await self.lookup_movie(f"tmdb:{tmdb_id}")

    async def lookup_movie_by_imdb(self, imdb_id: str) -> list[dict[str, Any]]:
        """Lookup movie by IMDB ID.

        Args:
            imdb_id: IMDB ID (e.g., "tt0133093")

        Returns:
            List of movie results (usually 1 item)
        """
        return await self.lookup_movie(f"imdb:{imdb_id}")

    async def get_movie_by_tmdb(self, tmdb_id: int) -> dict[str, Any] | None:
        """Get movie from Radarr library by TMDB ID.

        Args:
            tmdb_id: The Movie Database ID

        Returns:
            Movie dictionary if found in library, None otherwise
        """
        movies = await self.list_movies()
        for movie in movies:
            if movie.get("tmdbId") == tmdb_id:
                return movie
        return None

    async def add_movie(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response = await self._client.post("/movie", json=payload)
        response.raise_for_status()
        return response.json()

    async def list_root_folders(self) -> list[dict[str, Any]]:
        return await self._get_json("/rootfolder")

    async def list_quality_profiles(self) -> list[dict[str, Any]]:
        return await self._get_json("/qualityprofile")

    async def list_movies(self) -> list[dict[str, Any]]:
        # Use longer timeout for large libraries
        response = await self._client.get("/movie", timeout=LIST_MOVIES_TIMEOUT)
        response.raise_for_status()
        return response.json()

    async def ensure_movie(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async for attempt in _retry_policy():
            with attempt:
                return await self.add_movie(payload)
        raise RuntimeError("Unable to add movie after retries")

    async def _get_json(self, path: str) -> Any:
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def __aenter__(self) -> RadarrClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        await self.close()


@asynccontextmanager
async def radarr_client(
    base_url: str,
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
):
    client = RadarrClient(base_url=base_url, api_key=api_key, timeout=timeout)
    try:
        yield client
    finally:
        await client.close()


def build_add_movie_payload(
    *,
    lookup: Mapping[str, Any],
    quality_profile_id: int,
    root_folder_path: str,
    monitor: bool,
    minimum_availability: str | None = None,
    tags: Iterable[str] | None = None,
    search_on_add: bool = True,
) -> dict[str, Any]:
    """Assemble the payload expected by Radarr's POST /movie endpoint."""

    payload = {
        "tmdbId": lookup.get("tmdbId"),
        "title": lookup.get("title"),
        "qualityProfileId": quality_profile_id,
        "titleSlug": lookup.get("titleSlug"),
        "year": lookup.get("year"),
        "monitored": monitor,
        "rootFolderPath": root_folder_path,
        "addOptions": {
            "searchForMovie": search_on_add,
            "monitor": "movieOnly" if monitor else "none",
        },
    }
    if minimum_availability:
        payload["minimumAvailability"] = minimum_availability
    if tags:
        numeric_tags: list[int] = []
        for tag in tags:
            try:
                numeric_tags.append(int(tag))
            except (TypeError, ValueError):
                continue
        if numeric_tags:
            payload["tags"] = numeric_tags
    return payload


def _retry_policy() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=6),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )


__all__ = [
    "LibraryIndex",
    "RadarrClient",
    "build_add_movie_payload",
    "build_library_index",
    "radarr_client",
]
