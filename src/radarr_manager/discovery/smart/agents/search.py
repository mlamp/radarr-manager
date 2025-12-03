"""Smart Search Agent - performs web search for movies using LLM."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
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


class SmartSearchAgent(SmartAgent):
    """
    Smart agent that searches the web for movies using LLM with web search.

    Capabilities:
    - Uses OpenAI with web search tool for real-time movie data
    - Can search for specific genres, time periods, or criteria
    - Returns structured report with discovered movies

    Example tool call from orchestrator:
    ```json
    {
        "name": "search_movies",
        "arguments": {
            "query": "trending horror movies October 2024",
            "criteria": "Focus on supernatural and slasher films for Halloween",
            "max_results": 15
        }
    }
    ```
    """

    agent_type = AgentType.SEARCH
    name = "search_movies"
    description = (
        "Search the web for movies matching specific criteria. "
        "Uses real-time web search to find current releases, trending movies, "
        "or movies matching specific genres, themes, or requirements."
    )

    SYSTEM_PROMPT = """\
You are a movie research assistant. Search the web and report findings \
in structured markdown.

## Response Format

Your response should be a readable report with embedded structured data:

```
## Search Results: "{query}"

{1-2 sentence summary of what you found}

### Movies Found

| # | Title | Year | Confidence | Overview |
|---|-------|------|------------|----------|
| 1 | Exact Title | 2024 | 0.95 | Brief 1-line plot |
| 2 | Another Movie | 2024 | 0.90 | Brief plot summary |
...

### Notes
- Any relevant context (awards, critical reception, etc.)
- Caveats about the search results

### Data
```json
{"movies": [{"title": "Exact Title", "year": 2024, "overview": "Plot", ...}]}
```
```

## Rules
- Use EXACT official movie titles (no suffixes like "(2024)" or "(remake)")
- Year: integer or null if unknown
- Confidence: 0.0-1.0 based on relevance to search criteria
- Include 5-20 movies matching the search
- The JSON block at the end MUST be valid and parseable"""

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
        Search for movies matching the given criteria.

        Args:
            query: Search query (e.g., "trending horror movies October 2024")
            criteria: Additional criteria for filtering (e.g., "supernatural themes")
            max_results: Maximum number of movies to return (default: 20)
            region: Region for localized results (default: "US")

        Returns:
            AgentReport with search results
        """
        query = kwargs.get("query", "")
        criteria = kwargs.get("criteria", "")
        max_results = kwargs.get("max_results", 20)
        region = kwargs.get("region", "US")

        if not query:
            return self._create_failure_report("No search query provided")

        if not self._api_key:
            return self._create_failure_report("No API key configured for search agent")

        self._log(f"Searching: {query}")

        with TimedExecution() as timer:
            try:
                # Build the search prompt
                timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
                criteria_line = f"Additional criteria: {criteria}\n" if criteria else ""
                user_prompt = (
                    f"Search query: {query}\n"
                    f"{criteria_line}"
                    f"Date: {timestamp}\n"
                    f"Region: {region}\n"
                    f"Find up to {max_results} movies matching this search."
                )

                # Call OpenAI with web search - returns movies + raw markdown
                movies, raw_markdown = await self._search_with_llm(user_prompt)
                self._log(f"Found {len(movies)} movies")

                # Build report sections
                sections = [
                    ReportSection(
                        heading="Search Details",
                        content=(
                            f"- Query: {query}\n"
                            f"- Criteria: {criteria or 'None'}\n"
                            f"- Region: {region}\n"
                            f"- Max results: {max_results}"
                        ),
                    ),
                ]

                # Include search notes/context from the LLM if available
                notes = self._extract_notes(raw_markdown)
                if notes:
                    sections.append(
                        ReportSection(
                            heading="Search Notes",
                            content=notes,
                        )
                    )

                # Limit results
                movies = movies[:max_results]

                return AgentReport(
                    agent_type=self.agent_type,
                    agent_name=self.name,
                    status=ReportStatus.SUCCESS,
                    summary=f"Found {len(movies)} movies matching '{query}'",
                    sections=sections,
                    movies=movies,
                    stats={
                        "query": query,
                        "results_count": len(movies),
                    },
                    execution_time_ms=timer.elapsed_ms,
                )

            except Exception as exc:
                logger.warning(f"[SEARCH] Failed: {exc}")
                return AgentReport(
                    agent_type=self.agent_type,
                    agent_name=self.name,
                    status=ReportStatus.FAILURE,
                    summary=f"Search failed: {str(exc)[:100]}",
                    issues=[str(exc)],
                    stats={"error": str(exc)},
                    execution_time_ms=timer.elapsed_ms,
                )

    async def _search_with_llm(self, prompt: str) -> tuple[list[MovieData], str]:
        """
        Call OpenAI with web search to find movies.

        Returns:
            Tuple of (movies list, raw markdown response for context)
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Use OpenAI Responses API with web search
        payload = {
            "model": self._model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self.SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                },
            ],
            "tools": [{"type": "web_search"}],
            "temperature": 0.3,
            "max_output_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Extract the full markdown response
        raw_markdown = self._extract_full_response(data)

        # Extract JSON block from the markdown
        json_text = self._extract_json_block(raw_markdown)
        if not json_text:
            logger.warning("[SEARCH] No JSON block found in markdown response")
            logger.warning(f"[SEARCH] Raw response: {raw_markdown[:500]}")
            return [], raw_markdown

        try:
            movies_data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"[SEARCH] Failed to parse JSON block: {e}")
            logger.warning(f"[SEARCH] JSON text: {json_text[:500]}")
            return [], raw_markdown

        # Handle various response formats
        if isinstance(movies_data, list):
            movies_list = movies_data
        elif isinstance(movies_data, dict):
            movies_list = movies_data.get("movies", [])
        else:
            movies_list = []

        # Convert to MovieData
        movies: list[MovieData] = []
        for item in movies_list:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            movies.append(
                MovieData(
                    title=item.get("title", ""),
                    year=item.get("year"),
                    overview=item.get("overview"),
                    confidence=item.get("confidence", 0.8),
                    sources=item.get("sources", ["web_search"]),
                )
            )

        return movies, raw_markdown

    def _extract_full_response(self, data: dict[str, Any]) -> str:
        """Extract the full text response from OpenAI Responses API."""
        # Try output_text first (Responses API v2)
        if data.get("output_text"):
            return data["output_text"]

        # Try output array (Responses API)
        output = data.get("output", [])
        for item in output:
            # Handle message type outputs
            if item.get("type") == "message":
                contents = item.get("content", [])
                for content in contents:
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        if text:
                            return text
            # Also try direct content array
            contents = item.get("content", [])
            for content in contents:
                text = content.get("text", "")
                if text:
                    return text

        return ""

    def _extract_json_block(self, markdown: str) -> str:
        """Extract JSON code block from markdown response."""
        # Look for ```json ... ``` blocks
        json_match = re.search(r"```json\s*\n(.+?)\n```", markdown, re.DOTALL)
        if json_match:
            return self._clean_json_text(json_match.group(1))

        # Fallback: try to find raw JSON object/array
        # Look for {"movies": ...} pattern
        movies_match = re.search(r'\{"movies"\s*:\s*\[.+?\]\}', markdown, re.DOTALL)
        if movies_match:
            return movies_match.group(0)

        return ""

    def _clean_json_text(self, text: str) -> str:
        """Clean up JSON text from LLM response."""
        text = text.strip()
        # Remove citation markers (OpenAI web search adds these)
        text = re.sub(r"【[^】]*】", "", text)
        text = re.sub(r"\[citation[^\]]*\]", "", text, flags=re.IGNORECASE)
        return text

    def _extract_notes(self, markdown: str) -> str:
        """Extract the Notes section from markdown response."""
        # Look for ### Notes section
        notes_match = re.search(
            r"###\s*Notes\s*\n(.*?)(?=\n###|\n```|\Z)",
            markdown,
            re.DOTALL | re.IGNORECASE,
        )
        if notes_match:
            notes = notes_match.group(1).strip()
            # Clean up citation markers
            notes = re.sub(r"【[^】]*】", "", notes)
            notes = re.sub(r"\[citation[^\]]*\]", "", notes, flags=re.IGNORECASE)
            return notes
        return ""

    def _get_parameters_schema(self) -> dict[str, Any]:
        """Get the JSON schema for search_movies parameters."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query for finding movies. Examples: "
                        "'trending horror movies 2024', 'Oscar nominated films', "
                        "'upcoming Marvel movies'"
                    ),
                },
                "criteria": {
                    "type": "string",
                    "description": (
                        "Additional filtering criteria. Examples: "
                        "'supernatural themes', 'starring Oscar winners', "
                        "'RT score above 80%'"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of movies to return",
                    "default": 20,
                },
                "region": {
                    "type": "string",
                    "description": "Region for localized results (e.g., 'US', 'UK')",
                    "default": "US",
                },
            },
            "required": ["query"],
        }


__all__ = ["SmartSearchAgent"]
