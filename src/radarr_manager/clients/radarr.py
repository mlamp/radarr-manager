from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Iterable, Mapping

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT = 20.0
USER_AGENT = "radarr-manager/0.1.0"


class RadarrClient:
    """Thin asynchronous wrapper around the Radarr v3 API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        headers = {
            "X-Api-Key": api_key,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
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

    async def add_movie(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response = await self._client.post("/movie", json=payload)
        response.raise_for_status()
        return response.json()

    async def list_root_folders(self) -> list[dict[str, Any]]:
        return await self._get_json("/rootfolder")

    async def list_quality_profiles(self) -> list[dict[str, Any]]:
        return await self._get_json("/qualityprofile")

    async def list_movies(self) -> list[dict[str, Any]]:
        return await self._get_json("/movie")

    async def ensure_movie(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async for attempt in _retry_policy():
            with attempt:
                return await self.add_movie(payload)
        raise RuntimeError("Unable to add movie after retries")

    async def _get_json(self, path: str) -> Any:
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def __aenter__(self) -> "RadarrClient":
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
            "searchForMovie": False,
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


__all__ = ["RadarrClient", "build_add_movie_payload", "radarr_client"]
