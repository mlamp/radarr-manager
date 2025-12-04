"""
Smart LLM Orchestrator - the reasoning brain that coordinates agents.

The orchestrator is an LLM (Claude/GPT-4) that:
1. Receives user prompts and understands intent
2. Decides which agents to call and in what order
3. Interprets agent reports and adapts strategy
4. Reasons about failures and retries intelligently
5. Returns final curated results

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                    Smart Orchestrator                            │
│                  (Claude 3.5 / GPT-4o)                          │
│                                                                  │
│  1. Parse user prompt → Understand intent                        │
│  2. Plan strategy → Which agents to call?                        │
│  3. Execute agents → Tool calls                                  │
│  4. Interpret results → Read markdown reports                    │
│  5. Adapt strategy → Handle failures, gaps                       │
│  6. Return final results                                         │
└─────────────────────────────────────────────────────────────────┘
                            │
                   Tool Calls (JSON)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  fetch_movies │   │ search_movies │   │validate_movies│
│  (FetchAgent) │   │ (SearchAgent) │   │(ValidatorAgent│
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
   AgentReport         AgentReport         AgentReport
   (Markdown)          (Markdown)          (Markdown)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from radarr_manager.discovery.smart.agents import (
    SmartFetchAgent,
    SmartRankerAgent,
    SmartSearchAgent,
    SmartValidatorAgent,
)
from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    MovieData,
    ToolResult,
)
from radarr_manager.models.movie import MovieSuggestion

logger = logging.getLogger(__name__)


@dataclass
class SmartOrchestratorConfig:
    """Configuration for the smart orchestrator."""

    # LLM for orchestration
    orchestrator_api_key: str | None = None
    orchestrator_model: str = "gpt-4o"  # Smart model for reasoning
    orchestrator_provider: str = "openai"  # "openai" or "anthropic"

    # Agent LLM (cheaper, for agent tasks)
    agent_api_key: str | None = None
    agent_model: str = "gpt-4o-mini"  # Cheaper model for agents

    # Scraper
    scraper_api_url: str = "http://localhost:11235"
    scraper_api_key: str | None = None

    # Limits
    max_iterations: int = 5  # Max reasoning loops
    max_movies: int = 50

    @property
    def has_orchestrator_llm(self) -> bool:
        return bool(self.orchestrator_api_key)


@dataclass
class ConversationMessage:
    """A message in the orchestrator's conversation."""

    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None  # Tool name for tool results


ORCHESTRATOR_SYSTEM_PROMPT = """\
You are a smart movie discovery orchestrator. Your job is to help users find \
HIGH-QUALITY, MAINSTREAM movies by coordinating specialized agents.

**Current date context will be provided in the user message.**

## Available Tools

1. **fetch_movies** - Fetch movie lists from IMDB (most reliable source)
   - url: FULL URL to fetch
   - parser: Parser to use (imdb_moviemeter is best)
   - max_movies: Maximum movies to return

   **IMPORTANT URLs:**
   - IMDB Top 10 Most Popular: https://www.imdb.com/search/title/?title_type=feature&moviemeter=,10
   - IMDB Top 50 Most Popular: https://www.imdb.com/search/title/?title_type=feature&moviemeter=,50
   - IMDB Top 100 Most Popular: https://www.imdb.com/search/title/?title_type=feature&moviemeter=,100

2. **search_movies** - Search the web for movies (supplements fetch)
   - query: Search query (be specific about quality criteria)
   - criteria: Additional filtering (ratings, box office, awards)
   - max_results: Maximum results
   - region: Region for results (default: US)

3. **validate_movies** - Validate and filter movie lists
   - movies: List of movies to validate
   - deduplicate: Merge duplicates (default: true)
   - min_confidence: Minimum confidence threshold
   - filter_tv_shows: Remove TV show patterns

4. **rank_movies** - Rank movies by specific criteria
   - movies: List of movies to rank
   - criteria: Ranking criteria (include quality requirements)
   - limit: Max movies to return
   - add_overviews: Add plot summaries

## CRITICAL Quality Guidelines

When searching for "blockbuster" or mainstream movies, ALWAYS require:
- **Wide theatrical release** (not limited, festival, or streaming-only)
- **High IMDB ratings** (7.0+ for mainstream appeal)
- **Significant box office** or major studio backing
- **NOT**: K-pop concerts, anime compilations, re-releases, documentaries, foreign films \
with limited US distribution (unless specifically requested)

## Your Process (ALWAYS follow this order)

1. **ALWAYS start with fetch_movies from IMDB** - This is the most reliable source:
   - fetch_movies(url="https://www.imdb.com/search/title/?title_type=feature&moviemeter=,50", \
parser="imdb_moviemeter", max_movies=30)

2. **Then use search_movies** for additional context:
   - "top box office movies [current month year]"
   - "highest rated movies in theaters [year]"

3. **Validate** - Remove duplicates and invalid entries

4. **Rank with quality criteria**:
   - "mainstream wide release only, IMDB 7.0+, exclude concerts/anime/documentaries"

## Example Flow

**User: "Find 10 blockbuster movies"**
1. fetch_movies(url="https://www.imdb.com/search/title/?title_type=feature&moviemeter=,50", \
parser="imdb_moviemeter", max_movies=30)
2. search_movies(query="top box office movies December 2025", criteria="wide release")
3. validate_movies(movies=combined, deduplicate=true)
4. rank_movies(movies=validated, criteria="mainstream blockbusters, IMDB 7+, \
exclude anime/concerts/documentaries/re-releases", limit=10)
"""


class SmartOrchestrator:
    """
    LLM-powered orchestrator that coordinates smart agents.

    The orchestrator uses a reasoning LLM to:
    - Understand user intent
    - Decide which agents to call
    - Interpret agent reports
    - Adapt strategy based on results
    - Return curated movie suggestions
    """

    def __init__(
        self,
        config: SmartOrchestratorConfig,
        debug: bool = False,
    ) -> None:
        self._config = config
        self._debug = debug

        # Initialize agents
        self._agents: dict[str, Any] = {
            "fetch_movies": SmartFetchAgent(
                api_url=config.scraper_api_url,
                api_key=config.scraper_api_key,
                debug=debug,
            ),
            "search_movies": SmartSearchAgent(
                api_key=config.agent_api_key,
                model=config.agent_model,
                debug=debug,
            ),
            "validate_movies": SmartValidatorAgent(
                debug=debug,
            ),
            "rank_movies": SmartRankerAgent(
                api_key=config.agent_api_key,
                model=config.agent_model,
                debug=debug,
            ),
        }

        # Build tool definitions for the orchestrator
        self._tools = [agent.get_tool_definition() for agent in self._agents.values()]

    async def discover(
        self,
        prompt: str,
        limit: int = 10,
        region: str = "US",
    ) -> list[MovieSuggestion]:
        """
        Discover movies based on a natural language prompt.

        Args:
            prompt: User's discovery request (e.g., "Find 10 horror movies for Halloween")
            limit: Maximum number of movies to return
            region: Region for localized results

        Returns:
            List of MovieSuggestion objects
        """
        if not self._config.has_orchestrator_llm:
            # Fallback to deterministic mode
            return await self._deterministic_discover(prompt, limit, region)

        self._log(f"Smart discovery: '{prompt}' (limit={limit}, region={region})")

        # Get current date for context
        today = date.today()
        date_str = today.strftime("%B %d, %Y")  # e.g., "December 04, 2025"

        # Build initial conversation
        messages: list[ConversationMessage] = [
            ConversationMessage(role="system", content=ORCHESTRATOR_SYSTEM_PROMPT),
            ConversationMessage(
                role="user",
                content=(
                    f"**Today's date: {date_str}**\n\n"
                    f"User request: {prompt}\n\n"
                    f"Limit: {limit} movies\nRegion: {region}"
                ),
            ),
        ]

        # Run the reasoning loop
        final_movies: list[MovieData] = []
        iterations = 0

        while iterations < self._config.max_iterations:
            iterations += 1
            self._log(f"Iteration {iterations}")

            # Call the orchestrator LLM
            response = await self._call_orchestrator(messages)

            # Check if we have tool calls
            if response.tool_calls:
                tool_names = [tc.get("function", {}).get("name") for tc in response.tool_calls]
                self._log(f"Tool calls: {tool_names}")

                # Execute tool calls
                tool_results = await self._execute_tool_calls(response.tool_calls)

                # Add assistant message with tool calls
                messages.append(response)

                # Add tool results
                for result in tool_results:
                    messages.append(
                        ConversationMessage(
                            role="tool",
                            content=result.to_markdown(),
                            tool_call_id=result.call_id,
                            name=result.tool_name,
                        )
                    )

                    # Track movies from rank_movies (final output)
                    if result.tool_name == "rank_movies" and result.success:
                        final_movies = result.report.movies

            else:
                # No more tool calls - orchestrator is done
                self._log("Orchestrator finished reasoning")
                break

        # Convert to MovieSuggestion
        suggestions = self._movies_to_suggestions(final_movies)

        self._log(f"Returning {len(suggestions)} movie suggestions")
        return suggestions[:limit]

    async def _deterministic_discover(
        self,
        prompt: str,
        limit: int,
        region: str,
    ) -> list[MovieSuggestion]:
        """Fallback discovery without LLM orchestrator."""
        self._log("Using deterministic discovery (no orchestrator LLM)")

        all_movies: list[MovieData] = []

        # Fetch from RT theaters
        try:
            fetch_agent = self._agents["fetch_movies"]
            result = await fetch_agent.execute(
                url="https://www.rottentomatoes.com/browse/movies_in_theaters",
                parser="rt_theaters",
                max_movies=50,
            )
            all_movies.extend(result.movies)
        except Exception as exc:
            self._log(f"RT fetch failed: {exc}")

        # Fetch from IMDB
        try:
            result = await fetch_agent.execute(
                url="https://www.imdb.com/chart/moviemeter/",
                parser="imdb_moviemeter",
                max_movies=50,
            )
            all_movies.extend(result.movies)
        except Exception as exc:
            self._log(f"IMDB fetch failed: {exc}")

        # If we have agent LLM, also search
        if self._config.agent_api_key:
            try:
                search_agent = self._agents["search_movies"]
                result = await search_agent.execute(
                    query=prompt,
                    max_results=20,
                    region=region,
                )
                all_movies.extend(result.movies)
            except Exception as exc:
                self._log(f"Search failed: {exc}")

        # Validate
        validator = self._agents["validate_movies"]
        validated = await validator.execute(
            movies=[m.to_dict() for m in all_movies],
            deduplicate=True,
        )

        # Rank
        ranker = self._agents["rank_movies"]
        ranked = await ranker.execute(
            movies=[m.to_dict() for m in validated.movies],
            criteria=prompt,
            limit=limit,
        )

        return self._movies_to_suggestions(ranked.movies)

    async def _call_orchestrator(
        self,
        messages: list[ConversationMessage],
    ) -> ConversationMessage:
        """Call the orchestrator LLM."""
        headers = {
            "Authorization": f"Bearer {self._config.orchestrator_api_key}",
            "Content-Type": "application/json",
        }

        # Convert messages to API format
        api_messages = []
        for msg in messages:
            api_msg: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                api_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                api_msg["tool_call_id"] = msg.tool_call_id
            if msg.name:
                api_msg["name"] = msg.name
            api_messages.append(api_msg)

        payload = {
            "model": self._config.orchestrator_model,
            "messages": api_messages,
            "tools": self._tools,
            "tool_choice": "auto",
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        message = data["choices"][0]["message"]

        return ConversationMessage(
            role=message.get("role", "assistant"),
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls", []),
        )

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[ToolResult]:
        """Execute tool calls and return results."""
        results: list[ToolResult] = []

        for tc in tool_calls:
            call_id = tc.get("id", "")
            function = tc.get("function", {})
            tool_name = function.get("name", "")
            arguments_str = function.get("arguments", "{}")

            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {}

            self._log(f"Executing {tool_name} with {arguments}")

            if tool_name not in self._agents:
                results.append(
                    ToolResult(
                        call_id=call_id,
                        tool_name=tool_name,
                        report=AgentReport(
                            agent_type="unknown",
                            agent_name=tool_name,
                            status="failure",
                            summary=f"Unknown tool: {tool_name}",
                        ),
                        success=False,
                        error=f"Unknown tool: {tool_name}",
                    )
                )
                continue

            try:
                agent = self._agents[tool_name]
                report = await agent.execute(**arguments)

                # Check status - handle both enum and string
                status_value = (
                    report.status.value if hasattr(report.status, "value") else str(report.status)
                )
                results.append(
                    ToolResult(
                        call_id=call_id,
                        tool_name=tool_name,
                        report=report,
                        success=status_value != "failure",
                    )
                )
            except Exception as exc:
                logger.warning(f"Tool {tool_name} failed: {exc}")
                results.append(
                    ToolResult(
                        call_id=call_id,
                        tool_name=tool_name,
                        report=AgentReport(
                            agent_type="unknown",
                            agent_name=tool_name,
                            status="failure",
                            summary=f"Execution failed: {str(exc)[:100]}",
                        ),
                        success=False,
                        error=str(exc),
                    )
                )

        return results

    def _movies_to_suggestions(self, movies: list[MovieData]) -> list[MovieSuggestion]:
        """Convert MovieData to MovieSuggestion."""
        from datetime import date

        suggestions: list[MovieSuggestion] = []

        for movie in movies:
            release_date = date(movie.year, 1, 1) if movie.year else None

            suggestions.append(
                MovieSuggestion(
                    title=movie.title,
                    release_date=release_date,
                    overview=movie.overview,
                    confidence=movie.confidence,
                    sources=movie.sources,
                    metadata=movie.metadata,
                )
            )

        return suggestions

    def _log(self, message: str) -> None:
        """Log a debug message if debugging is enabled."""
        if self._debug:
            logger.info(f"[SMART-ORCHESTRATOR] {message}")


__all__ = ["SmartOrchestrator", "SmartOrchestratorConfig"]
