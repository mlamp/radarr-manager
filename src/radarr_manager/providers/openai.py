from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from openai import AsyncOpenAI

from radarr_manager.models import MovieSuggestion
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError

SYSTEM_PROMPT = (
    "You are a film research assistant. Always return a single JSON object with a 'suggestions' array. "
    "Each element must include: title, optional release_date (YYYY-MM-DD), overview, franchise, confidence (0-1), sources (array of URLs or outlet names), and metadata for any extra fields. "
    "Focus on major film releases from the past month or the next two months (latest and upcoming big movies). "
    "Include only widely anticipated or popular films with broad Western audience appeal (e.g., Hollywood blockbusters or globally recognized titles). "
    "Exclude films with very poor ratings or reviews (for example, avoid any movie with an IMDb rating below 5.0 as these are considered low quality:contentReference[oaicite:11]{index=11}). "
    "Exclude regional movies (such as most Bollywood releases) that lack significant popularity in Western markets:contentReference[oaicite:12]{index=12}:contentReference[oaicite:13]{index=13}. "
    "However, if a Bollywood or other international film has achieved exceptional acclaim or high ratings (e.g., ~8.0+ on IMDb for Bollywood, ~7.5+ for other foreign films) and likely appeals to a broad audience, you may include it:contentReference[oaicite:14]{index=14}. "
    "Ensure each suggested movie meets these criteria of recency, broad appeal, and solid quality. "
    "Never include markdown, explanations, or any keys outside the specified schema. Only output the JSON object according to this schema."
)

class OpenAIProvider(MovieDiscoveryProvider):
    """Discovery provider that queries OpenAI with web search enabled."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None,
        region: str | None,
        cache_ttl_hours: int,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is required for the OpenAI provider")

        self._client = client or AsyncOpenAI(api_key=api_key)
        self._model = model or "gpt-4o-mini"
        self._region = region
        self._cache_ttl_hours = cache_ttl_hours

    async def discover(self, *, limit: int, region: str | None = None) -> list[MovieSuggestion]:
        target_region = region or self._region or "US"
        prompt = self._build_prompt(limit=limit, region=target_region)

        try:
            response = await self._client.responses.create(
                model=self._model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {"type": "input_text", "text": SYSTEM_PROMPT},
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                        ],
                    },
                ],
                tools=[{"type": "web_search"}],
                temperature=0.3,
            )
        except Exception as exc:  # pragma: no cover - depends on network APIs
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        payload = self._extract_json(response)
        suggestions_data = payload.get("suggestions", [])

        suggestions: list[MovieSuggestion] = []
        for item in suggestions_data:
            try:
                suggestion = MovieSuggestion.model_validate(item)
            except Exception as exc:  # pragma: no cover - validation errors bubble to user
                raise ProviderError(f"Invalid suggestion payload: {exc}") from exc
            suggestions.append(suggestion)

        return suggestions[:limit]

    def _build_prompt(self, *, limit: int, region: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            "You are a film research assistant. Use web_search to gather authoritative sources about "
            "upcoming or newly released wide box-office movies. Focus on titles with strong commercial "
            "traction or franchise momentum. Return fresh information as of "
            f"{timestamp}. Provide at most {limit} movies targeted for region {region}."
        )

    def _extract_json(self, response: Any) -> dict[str, Any]:
        """Extract JSON content from a Responses API result."""

        if hasattr(response, "output_text") and response.output_text:
            try:
                return json.loads(response.output_text)
            except json.JSONDecodeError:
                pass

        output = getattr(response, "output", None)
        if not output:
            raise ProviderError("OpenAI response did not include output content")

        for item in output:
            contents = getattr(item, "content", [])
            for content in contents:
                text = getattr(content, "text", None)
                if text:
                    candidate = text.strip()
                    if not candidate.startswith("{"):
                        start = candidate.find("{")
                        end = candidate.rfind("}")
                        if start != -1 and end != -1:
                            candidate = candidate[start : end + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError as exc:  # pragma: no cover
                        raise ProviderError(
                            "Failed to parse OpenAI JSON payload. Ensure the model replies with valid JSON.",
                        ) from exc

        raise ProviderError("Unable to parse structured response from OpenAI")


__all__ = ["OpenAIProvider"]
