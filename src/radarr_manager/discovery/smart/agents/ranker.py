"""Smart Ranker Agent - ranks and filters movies using LLM reasoning."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from radarr_manager.discovery.smart.agents.base import SmartAgent, TimedExecution
from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    AgentType,
    MovieData,
    ReportSection,
    ReportStatus,
)

logger = logging.getLogger(__name__)


class SmartRankerAgent(SmartAgent):
    """
    Smart agent that ranks and enhances movies using LLM reasoning.

    Capabilities:
    - Ranks movies by relevance to specific criteria
    - Adds plot overviews using LLM knowledge
    - Adjusts confidence based on quality signals
    - Can filter by genre, theme, or custom criteria

    Example tool call from orchestrator:
    ```json
    {
        "name": "rank_movies",
        "arguments": {
            "movies": [...],
            "criteria": "Halloween horror movies with supernatural themes",
            "limit": 10,
            "add_overviews": true
        }
    }
    ```
    """

    agent_type = AgentType.RANKER
    name = "rank_movies"
    description = (
        "Rank and enhance a list of movies based on specific criteria. "
        "Uses LLM to understand movie context, add plot summaries, "
        "and rank by relevance to the given criteria."
    )

    SYSTEM_PROMPT = """\
You are a movie ranking assistant. Given a list of movies and ranking criteria:

1. Analyze each movie's relevance to the criteria
2. **USE PROVIDED RATINGS**: If imdb_rating is provided, use it! IMDB 7.0+ = high quality.
3. Rank movies from most to least relevant
4. Add brief plot overviews (1-2 sentences) if missing
5. Adjust confidence scores based on fit with criteria

IMPORTANT: When imdb_rating and imdb_votes are provided in the input, USE THEM for ranking.
- A movie with imdb_rating 7.5 and 20000 votes is high quality and should be included
- Don't exclude movies just because they're not "mainstream" - include acclaimed indie films

Return a JSON object with:
- "ranked_movies": Array of movies in ranked order
  - Each movie has: title, year, overview, confidence (0-1), sources, reasoning
- "excluded_movies": Array of movies that don't fit criteria at all
  - Each has: title, reason

Example:
{
    "ranked_movies": [
        {
            "title": "Nosferatu",
            "year": 2024,
            "overview": "A gothic vampire tale...",
            "confidence": 0.95,
            "sources": ["RT", "IMDB"],
            "reasoning": "IMDB 7.8 with 50K votes, classic supernatural horror"
        }
    ],
    "excluded_movies": [
        {"title": "Concert Film XYZ", "reason": "K-pop concert, not a narrative film"}
    ]
}

Return ONLY valid JSON, no markdown or explanations."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        debug: bool = False,
    ) -> None:
        super().__init__(debug)
        self._api_key = api_key
        self._model = model

    async def execute(self, **kwargs: Any) -> AgentReport:
        """
        Rank and enhance movies based on criteria.

        Args:
            movies: List of MovieData dicts to rank
            criteria: Ranking/filtering criteria
            limit: Maximum number of movies to return (default: 20)
            add_overviews: Whether to add plot overviews (default: True)

        Returns:
            AgentReport with ranked movies
        """
        movies_data = kwargs.get("movies", [])
        criteria = kwargs.get("criteria", "")
        limit = kwargs.get("limit", 20)
        add_overviews = kwargs.get("add_overviews", True)

        if not movies_data:
            return self._create_failure_report("No movies provided for ranking")

        if not self._api_key:
            # Fallback to simple ranking without LLM
            return await self._simple_rank(movies_data, limit)

        self._log(f"Ranking {len(movies_data)} movies with criteria: {criteria}")

        with TimedExecution() as timer:
            try:
                # Parse input movies
                movies = self._parse_input_movies(movies_data)

                # Build LLM prompt with ratings data
                movie_list = json.dumps(
                    [
                        {
                            "title": m.title,
                            "year": m.year,
                            "sources": m.sources,
                            "imdb_rating": m.ratings.get("imdb_rating"),
                            "imdb_votes": m.ratings.get("imdb_votes"),
                        }
                        for m in movies
                    ],
                    indent=2,
                )

                user_prompt = (
                    f"Movies to rank:\n{movie_list}\n\n"
                    f"Ranking criteria: {criteria or 'general theatrical appeal and quality'}\n"
                    f"Return top {limit} movies in ranked order."
                    + (" Add plot overviews for each." if add_overviews else "")
                )

                # Call LLM
                ranked_movies, excluded = await self._rank_with_llm(user_prompt, movies)
                self._log(f"Ranked {len(ranked_movies)} movies, excluded {len(excluded)}")

                # Build report sections
                sections = [
                    ReportSection(
                        heading="Ranking Criteria",
                        content=(
                            f"- Criteria: {criteria or 'general quality'}\n"
                            f"- Input movies: {len(movies)}\n"
                            f"- Requested limit: {limit}"
                        ),
                    ),
                ]

                if excluded:
                    excluded_lines = "\n".join(
                        f"- {e['title']}: {e['reason']}" for e in excluded[:5]
                    )
                    if len(excluded) > 5:
                        excluded_lines += f"\n- ... and {len(excluded) - 5} more excluded"
                    sections.append(
                        ReportSection(
                            heading="Excluded Movies",
                            content=excluded_lines,
                        )
                    )

                return AgentReport(
                    agent_type=self.agent_type,
                    agent_name=self.name,
                    status=ReportStatus.SUCCESS,
                    summary=f"Ranked {len(ranked_movies)} movies from {len(movies)} input",
                    sections=sections,
                    movies=ranked_movies[:limit],
                    stats={
                        "input_count": len(movies),
                        "ranked_count": len(ranked_movies),
                        "excluded_count": len(excluded),
                        "criteria": criteria,
                    },
                    execution_time_ms=timer.elapsed_ms,
                )

            except Exception as exc:
                logger.warning(
                    f"[RANKER] LLM ranking failed: {exc}, falling back to simple ranking"
                )
                return await self._simple_rank(movies_data, limit)

    async def _simple_rank(self, movies_data: list[Any], limit: int) -> AgentReport:
        """Simple ranking without LLM (fallback)."""
        with TimedExecution() as timer:
            movies = self._parse_input_movies(movies_data)

            # Sort by confidence and source count
            movies.sort(key=lambda m: (-m.confidence, -len(m.sources), m.title))

            return AgentReport(
                agent_type=self.agent_type,
                agent_name=self.name,
                status=ReportStatus.PARTIAL,
                summary=f"Simple ranking of {len(movies[:limit])} movies (no LLM enhancement)",
                movies=movies[:limit],
                stats={
                    "input_count": len(movies),
                    "ranked_count": min(len(movies), limit),
                    "method": "simple_fallback",
                },
                issues=["LLM not available, used simple confidence-based ranking"],
                execution_time_ms=timer.elapsed_ms,
            )

    async def _rank_with_llm(
        self, prompt: str, original_movies: list[MovieData]
    ) -> tuple[list[MovieData], list[dict[str, str]]]:
        """Use LLM to rank movies."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        response_text = data["choices"][0]["message"]["content"]
        result = json.loads(response_text)

        # Build lookup from original movies
        original_lookup = {m.title.lower().strip(): m for m in original_movies}

        # Parse ranked movies
        ranked: list[MovieData] = []
        for item in result.get("ranked_movies", []):
            title = item.get("title", "")
            key = title.lower().strip()

            # Find original or create new
            if key in original_lookup:
                movie = original_lookup[key]
                # Update with LLM data
                if item.get("overview"):
                    movie.overview = item["overview"]
                if item.get("confidence"):
                    movie.confidence = item["confidence"]
                if item.get("reasoning"):
                    movie.metadata["ranking_reason"] = item["reasoning"]
            else:
                movie = MovieData(
                    title=title,
                    year=item.get("year"),
                    overview=item.get("overview"),
                    confidence=item.get("confidence", 0.8),
                    sources=item.get("sources", []),
                    metadata={"ranking_reason": item.get("reasoning", "")},
                )

            ranked.append(movie)

        # Parse excluded movies
        excluded = result.get("excluded_movies", [])

        return ranked, excluded

    def _parse_input_movies(self, movies_data: list[Any]) -> list[MovieData]:
        """Parse input movies from various formats."""
        movies: list[MovieData] = []
        for item in movies_data:
            if isinstance(item, MovieData):
                movies.append(item)
            elif isinstance(item, dict):
                movies.append(MovieData.from_dict(item))
            elif hasattr(item, "to_dict"):
                movies.append(MovieData.from_dict(item.to_dict()))
        return movies

    def _get_parameters_schema(self) -> dict[str, Any]:
        """Get the JSON schema for rank_movies parameters."""
        return {
            "type": "object",
            "properties": {
                "movies": {
                    "type": "array",
                    "description": "List of movies to rank",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "year": {"type": ["integer", "null"]},
                            "overview": {"type": ["string", "null"]},
                            "confidence": {"type": "number"},
                            "sources": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title"],
                    },
                },
                "criteria": {
                    "type": "string",
                    "description": (
                        "Ranking/filtering criteria. Examples: "
                        "'Halloween horror movies', 'Oscar-worthy dramas', "
                        "'family-friendly animation'"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of movies to return",
                    "default": 20,
                },
                "add_overviews": {
                    "type": "boolean",
                    "description": "Whether to add plot overviews using LLM",
                    "default": True,
                },
            },
            "required": ["movies"],
        }


__all__ = ["SmartRankerAgent"]
