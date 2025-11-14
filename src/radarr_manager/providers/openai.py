from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from openai import AsyncOpenAI

from radarr_manager.models import MovieSuggestion
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a film research assistant. Always return a single JSON object with a 'suggestions' array. "
    "Each element MUST include: title, optional release_date (YYYY-MM-DD), overview, franchise, confidence (0-1), "
    "sources (array of URLs or outlet names), and MANDATORY metadata object with tmdb_id and imdb_id. "
    "CRITICAL: For EVERY movie suggestion, you MUST search for and include both tmdb_id (numeric TMDB ID) and imdb_id (string like tt1234567) in the metadata object. "
    "Example format: {\"title\": \"Movie Title\", \"metadata\": {\"tmdb_id\": 12345, \"imdb_id\": \"tt1234567\"}, ...} "
    "Focus on major film releases from the past month or the next four months that have strong commercial momentum. "
    "Include widely anticipated movies with broad Western audience appeal including: Hollywood blockbusters, major studio releases, "
    "globally recognized franchises (Marvel, DC, Disney, Universal, Warner Bros), AND prestige films from acclaimed studios "
    "(Lionsgate, A24, Sony Pictures, Neon, Searchlight Pictures, Focus Features). "
    "QUALITY REQUIREMENTS: For released movies, exclude those with IMDb ratings below 6.5/10. "
    "For PRE-RELEASE movies (no IMDb rating yet), include them if they meet ANY of these criteria: "
    "(1) Major studio tentpole/franchise film, (2) A-list cast or acclaimed director, (3) Strong marketing buzz or trailer views, "
    "(4) Based on bestselling book/successful IP, (5) Award season contender, (6) Wide theatrical release confirmed. "
    "EXCLUDE low-budget regional films, direct-to-streaming B-movies, and poorly received sequels. "
    "NO Bollywood, Nollywood, or other regional cinema unless they have exceptional global critical acclaim (8.0+ IMDb). "
    "Prioritize: Major studio releases, acclaimed directors, A-list actors, franchise films, award contenders, prestige dramas/thrillers. "
    "Every suggestion must have genuine mainstream appeal and critical/audience approval (or strong pre-release anticipation). "
    "Return raw JSON only—no markdown, explanations, or keys outside the schema."
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
        debug: bool = False,
    ) -> None:
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is required for the OpenAI provider")

        self._client = client or AsyncOpenAI(api_key=api_key)
        self._model = model or "gpt-4o-mini"
        self._region = region
        self._cache_ttl_hours = cache_ttl_hours
        self._debug = debug

    async def discover(self, *, limit: int, region: str | None = None) -> list[MovieSuggestion]:
        target_region = region or self._region or "US"
        prompt = self._build_prompt(limit=limit, region=target_region)

        if self._debug:
            logger.info(f"[DEBUG] Requesting {limit} movie suggestions from OpenAI ({self._model})")
            logger.info(f"[DEBUG] Region: {target_region}")

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

        if self._debug:
            logger.info(f"[DEBUG] LLM returned {len(suggestions_data)} suggestions")

        suggestions: list[MovieSuggestion] = []
        validation_errors = []
        for item in suggestions_data:
            try:
                suggestion = MovieSuggestion.model_validate(item)
                suggestions.append(suggestion)
            except Exception as exc:  # pragma: no cover - validation errors bubble to user
                validation_errors.append(f"{item.get('title', 'Unknown')}: {exc}")
                if self._debug:
                    logger.warning(f"[DEBUG] Validation failed for: {item.get('title', 'Unknown')} - {exc}")

        if validation_errors and not self._debug:
            raise ProviderError(f"Invalid suggestion payload: {validation_errors[0]}")

        truncated = suggestions[:limit]

        if self._debug:
            logger.info(f"[DEBUG] Validated {len(suggestions)} suggestions, returning {len(truncated)}")
            for idx, s in enumerate(truncated, 1):
                imdb_rating = "N/A"
                if s.metadata and "imdb_rating" in s.metadata:
                    imdb_rating = s.metadata["imdb_rating"]
                logger.info(
                    f"[DEBUG]   {idx}. {s.title} ({s.year or 'TBA'}) "
                    f"- confidence: {s.confidence:.2f}, IMDb: {imdb_rating}"
                )

            if len(suggestions) > limit:
                skipped = suggestions[limit:]
                logger.info(f"[DEBUG] Truncated {len(skipped)} suggestions due to limit:")
                for s in skipped:
                    logger.info(f"[DEBUG]   - {s.title} ({s.year or 'TBA'})")

        return truncated

    def _build_prompt(self, *, limit: int, region: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            "You are a film research assistant. Use web_search to gather authoritative sources about "
            "upcoming or newly released wide box-office movies. Focus on titles with strong commercial "
            "traction or franchise momentum. For EACH movie, search for and include its TMDB ID (numeric) "
            "and IMDB ID (format: tt1234567) in the metadata object. Return fresh information as of "
            f"{timestamp}. Provide at most {limit} movies targeted for region {region} with complete metadata including IDs."
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
