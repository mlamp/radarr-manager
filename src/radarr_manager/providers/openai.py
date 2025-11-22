from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI

from radarr_manager.models import MovieSuggestion
from radarr_manager.providers.base import MovieDiscoveryProvider, ProviderError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a film research assistant. Always return a single JSON object with a 'suggestions' array. "
    "Each element MUST include: title, optional release_date (YYYY-MM-DD), overview, franchise, confidence (0-1), "
    "sources (array of URLs or outlet names), and MANDATORY metadata object with comprehensive ratings data. "
    "CRITICAL: For EVERY movie suggestion, you MUST search for and include in the metadata object: "
    "- tmdb_id (numeric TMDB ID), imdb_id (string like tt1234567), imdb_rating (numeric, e.g. 7.3), imdb_votes (integer) "
    "- rt_critics_score (Rotten Tomatoes critics %, 0-100), rt_audience_score (RT audience %, 0-100) "
    "- metacritic_score (Metacritic score, 0-100, null if unavailable) "
    "Use web_search to find current ratings from IMDb, Rotten Tomatoes, and Metacritic. "
    'Example format: {"title": "Movie Title", "metadata": {"tmdb_id": 12345, "imdb_id": "tt1234567", "imdb_rating": 7.3, '
    '"imdb_votes": 45000, "rt_critics_score": 85, "rt_audience_score": 92, "metacritic_score": 78}, ...} '
    "Focus on major film releases from the past three months or the next four months that have strong commercial momentum. "
    "Include: blockbusters, franchises (Marvel, DC, Disney, Universal, Warner Bros), prestige films (Lionsgate, A24, Sony Pictures, "
    "Neon, Searchlight, Focus Features, Aura Entertainment, IFC, Bleecker Street), AND well-reviewed mid-budget theatrical releases "
    "(IMDb 7.0+/RT 60%+) with recognizable casts, including action-comedies, dramedies, and genre films. Prioritize quality over budget. "
    "OSCAR WINNER PRIORITY: STRONGLY prioritize movies starring actors who have won the Academy Award for Best Actor or Best Actress. "
    "When selecting between multiple quality options, always prefer films featuring Oscar-winning lead actors. "
    "Examples of Best Actor winners to prioritize: Brendan Fraser, Will Smith, Anthony Hopkins, Gary Oldman, Casey Affleck, "
    "Leonardo DiCaprio, Eddie Redmayne, Matthew McConaughey, Daniel Day-Lewis, Colin Firth, Jeff Bridges, Sean Penn, Forest Whitaker, "
    "Philip Seymour Hoffman, Jamie Foxx, Denzel Washington, Russell Crowe, Tom Hanks, Al Pacino, Nicolas Cage, Cillian Murphy. "
    "Examples of Best Actress winners to prioritize: Michelle Yeoh, Jessica Chastain, Frances McDormand, Olivia Colman, Emma Stone, "
    "Brie Larson, Julianne Moore, Cate Blanchett, Jennifer Lawrence, Natalie Portman, Sandra Bullock, Kate Winslet, Marion Cotillard, "
    "Helen Mirren, Reese Witherspoon, Charlize Theron, Nicole Kidman, Halle Berry, Julia Roberts, Gwyneth Paltrow. "
    "QUALITY REQUIREMENTS: For released movies, exclude those with IMDb ratings below 6.5/10. "
    "For PRE-RELEASE movies (no IMDb rating yet), include them if they meet ANY of these criteria: "
    "(1) Major studio tentpole/franchise film, (2) A-list cast or acclaimed director, (3) Strong marketing buzz or trailer views, "
    "(4) Based on bestselling book/successful IP, (5) Award season contender, (6) Wide theatrical release confirmed. "
    "EXCLUDE low-budget regional films, direct-to-streaming B-movies, and poorly received sequels. "
    "NO Bollywood, Nollywood, or other regional cinema unless they have exceptional global critical acclaim (8.0+ IMDb). "
    "Prioritize: Oscar-winning actors, major studio releases, acclaimed directors, franchise films, award contenders, prestige dramas/thrillers. "
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
                    logger.warning(
                        f"[DEBUG] Validation failed for: {item.get('title', 'Unknown')} - {exc}"
                    )

        if validation_errors and not self._debug:
            raise ProviderError(f"Invalid suggestion payload: {validation_errors[0]}")

        truncated = suggestions[:limit]

        if self._debug:
            logger.info(
                f"[DEBUG] Validated {len(suggestions)} suggestions, returning {len(truncated)}"
            )
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
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        return (
            "Use web_search for upcoming/recent wide theatrical movies. Search: IMDb, Rotten Tomatoes "
            "(https://www.rottentomatoes.com/browse/movies_in_theaters for currently playing), Metacritic, and TMDB. "
            "Include recent 2025 theatrical releases from Aug-Nov, blockbusters, franchises, prestige films, AND "
            "mid-budget releases (action-comedies, dramedies). PRIORITIZE movies featuring Academy Award-winning actors "
            "(Best Actor/Best Actress winners). When available, prefer films with Oscar-winning lead performances. "
            f"REQUIRED for each movie: TMDB ID, IMDb ID, IMDb rating + vote count, RT critics score, RT audience score, "
            f"Metacritic score (if available). {timestamp}. Max {limit} movies for region {region}."
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
