"""
Protocol for agent-to-agent communication using structured markdown.

The Smart Orchestrator and its agents communicate via well-structured markdown
that is both human-readable and machine-parseable. This allows the orchestrator
LLM to reason naturally while maintaining structured data flow.

Communication Flow:
┌─────────────────────────────────────────────────────────────────┐
│  Smart Orchestrator (Claude/GPT-4)                               │
│  - Receives user prompt                                          │
│  - Reasons about which agents to call                            │
│  - Interprets agent reports                                      │
│  - Adapts strategy based on results                              │
└─────────────────────────────────────────────────────────────────┘
                            │
                   Tool Calls (JSON)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  FetchAgent   │   │  SearchAgent  │   │ ValidatorAgent│
│               │   │               │   │               │
│  Returns:     │   │  Returns:     │   │  Returns:     │
│  AgentReport  │   │  AgentReport  │   │  AgentReport  │
│  (Markdown)   │   │  (Markdown)   │   │  (Markdown)   │
└───────────────┘   └───────────────┘   └───────────────┘
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentType(str, Enum):
    """Types of agents in the smart orchestrator system."""

    FETCH = "fetch"
    SEARCH = "search"
    VALIDATOR = "validator"
    RANKER = "ranker"


class ReportStatus(str, Enum):
    """Status of an agent report."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


@dataclass
class MovieData:
    """
    Standardized movie data structure.

    This is the core data format passed between agents.
    """

    title: str
    year: int | None = None
    overview: str | None = None
    confidence: float = 0.8
    sources: list[str] = field(default_factory=list)
    ratings: dict[str, Any] = field(default_factory=dict)  # rt_score, imdb_score, etc.
    metadata: dict[str, Any] = field(default_factory=dict)  # Extra agent-specific data
    is_valid: bool = True
    rejection_reason: str | None = None

    def to_markdown_row(self) -> str:
        """Convert to a markdown table row."""
        year_str = str(self.year) if self.year else "TBA"
        sources_str = ", ".join(self.sources) if self.sources else "unknown"
        overview_str = (
            self.overview[:50] + "..."
            if self.overview and len(self.overview) > 50
            else (self.overview or "")
        )
        conf = f"{self.confidence:.2f}"
        return f"| {self.title} | {year_str} | {conf} | {sources_str} | {overview_str} |"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "year": self.year,
            "overview": self.overview,
            "confidence": self.confidence,
            "sources": self.sources,
            "ratings": self.ratings,
            "metadata": self.metadata,
            "is_valid": self.is_valid,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MovieData:
        """Create from dictionary."""
        return cls(
            title=data.get("title", ""),
            year=data.get("year"),
            overview=data.get("overview"),
            confidence=data.get("confidence", 0.8),
            sources=data.get("sources", []),
            ratings=data.get("ratings", {}),
            metadata=data.get("metadata", {}),
            is_valid=data.get("is_valid", True),
            rejection_reason=data.get("rejection_reason"),
        )


@dataclass
class ReportSection:
    """A section within an agent report."""

    heading: str
    content: str  # Can be text, table, or list in markdown format


@dataclass
class AgentReport:
    """
    Structured report from an agent.

    The report is designed to be:
    1. Human-readable (markdown format)
    2. Machine-parseable (structured sections with JSON data block)
    3. Informative for the orchestrator LLM to reason about
    """

    agent_type: AgentType
    agent_name: str
    status: ReportStatus
    summary: str  # One-line summary for quick understanding
    sections: list[ReportSection] = field(default_factory=list)
    movies: list[MovieData] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    execution_time_ms: float = 0.0

    def to_markdown(self) -> str:
        """
        Render the report as structured markdown.

        Format:
        ```
        ## Agent Report: {agent_name}

        **Status**: {status}
        **Summary**: {summary}

        ### Source Details
        - Fetched from: {url}
        - Parse success: {success}

        ### Movies Found
        | Title | Year | Confidence | Sources | Overview |
        |-------|------|------------|---------|----------|
        | Movie 1 | 2024 | 0.90 | RT, IMDB | Plot summary... |
        ...

        ### Issues
        - Issue 1
        - Issue 2

        ### Stats
        - Execution time: 1.2s
        - Movies found: 15

        ### Data (JSON)
        ```json
        {"movies": [...], "stats": {...}}
        ```
        """
        lines: list[str] = []

        # Header
        lines.append(f"## Agent Report: {self.agent_name}")
        lines.append("")
        lines.append(f"**Status**: {self.status.value}")
        lines.append(f"**Summary**: {self.summary}")
        lines.append("")

        # Custom sections
        for section in self.sections:
            lines.append(f"### {section.heading}")
            lines.append(section.content)
            lines.append("")

        # Movies table (if any)
        if self.movies:
            lines.append("### Movies Found")
            lines.append("")
            lines.append("| Title | Year | Confidence | Sources | Overview |")
            lines.append("|-------|------|------------|---------|----------|")
            for movie in self.movies[:20]:  # Limit for readability
                lines.append(movie.to_markdown_row())
            if len(self.movies) > 20:
                lines.append(f"| ... | ... | ... | ... | ({len(self.movies) - 20} more movies) |")
            lines.append("")

        # Issues
        if self.issues:
            lines.append("### Issues")
            for issue in self.issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Stats
        lines.append("### Stats")
        lines.append(f"- Execution time: {self.execution_time_ms:.0f}ms")
        lines.append(f"- Movies count: {len(self.movies)}")
        for key, value in self.stats.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

        # JSON data block for machine parsing
        lines.append("### Data (JSON)")
        lines.append("```json")
        data = {
            "movies": [m.to_dict() for m in self.movies],
            "stats": self.stats,
            "status": self.status.value,
        }
        lines.append(json.dumps(data, indent=2, default=str))
        lines.append("```")

        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, markdown: str) -> AgentReport:
        """Parse a markdown report back into an AgentReport object."""
        # Extract JSON data block
        json_match = re.search(r"```json\s*\n(.+?)\n```", markdown, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON data block found in report")

        data = json.loads(json_match.group(1))

        # Extract header info
        status_match = re.search(r"\*\*Status\*\*:\s*(\w+)", markdown)
        summary_match = re.search(r"\*\*Summary\*\*:\s*(.+?)(?:\n|$)", markdown)
        agent_match = re.search(r"## Agent Report:\s*(.+?)(?:\n|$)", markdown)

        status_str = status_match.group(1) if status_match else "success"
        summary = summary_match.group(1).strip() if summary_match else ""
        agent_name = agent_match.group(1).strip() if agent_match else "unknown"

        # Determine agent type from name
        agent_type = AgentType.FETCH
        if "search" in agent_name.lower():
            agent_type = AgentType.SEARCH
        elif "validator" in agent_name.lower():
            agent_type = AgentType.VALIDATOR
        elif "ranker" in agent_name.lower():
            agent_type = AgentType.RANKER

        return cls(
            agent_type=agent_type,
            agent_name=agent_name,
            status=ReportStatus(status_str.lower()),
            summary=summary,
            movies=[MovieData.from_dict(m) for m in data.get("movies", [])],
            stats=data.get("stats", {}),
        )


@dataclass
class ToolCall:
    """
    A tool call from the orchestrator to an agent.

    Tool calls are how the orchestrator LLM invokes agents.
    """

    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }


@dataclass
class ToolResult:
    """
    Result of a tool call (agent execution).

    Contains both the structured data and the markdown report.
    """

    call_id: str
    tool_name: str
    report: AgentReport
    success: bool = True
    error: str | None = None

    def to_markdown(self) -> str:
        """Render as markdown for the orchestrator to read."""
        if not self.success:
            return f"## Tool Error: {self.tool_name}\n\n**Error**: {self.error}"
        return self.report.to_markdown()


__all__ = [
    "AgentType",
    "ReportStatus",
    "MovieData",
    "ReportSection",
    "AgentReport",
    "ToolCall",
    "ToolResult",
]
