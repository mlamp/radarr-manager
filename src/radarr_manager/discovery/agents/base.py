"""Base classes for discovery agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    """Status of an agent operation."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some results, but errors occurred
    FAILURE = "failure"


@dataclass
class AgentMessage:
    """Base message for agent communication."""

    agent_id: str = ""
    timestamp: float = field(default_factory=lambda: __import__("time").time())


@dataclass
class AgentResult(AgentMessage):
    """Result of an agent operation."""

    status: AgentStatus = AgentStatus.SUCCESS
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Agent[RequestT: AgentMessage, ResultT: AgentResult](ABC):
    """
    Base class for discovery agents.

    Agents are specialized workers that perform specific tasks:
    - FetchAgent: Fetches content from URLs via Crawl4AI
    - AnalysisAgent: Uses LLM to validate/rank/filter results

    Each agent:
    - Receives strongly-typed requests
    - Returns strongly-typed results
    - Operates independently (no shared state)
    """

    name: str = "base"

    def __init__(self, debug: bool = False) -> None:
        self._debug = debug

    @abstractmethod
    async def execute(self, request: RequestT) -> ResultT:
        """Execute the agent's task with the given request."""
        pass

    def _log(self, message: str) -> None:
        """Log a debug message if debugging is enabled."""
        if self._debug:
            import logging

            logging.getLogger(__name__).info(f"[{self.name.upper()}] {message}")


__all__ = ["Agent", "AgentMessage", "AgentResult", "AgentStatus"]
