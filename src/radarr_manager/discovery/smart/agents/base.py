"""Base class for smart agents that produce structured markdown reports."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    AgentType,
    ReportStatus,
)

logger = logging.getLogger(__name__)


class SmartAgent(ABC):
    """
    Base class for smart agents in the LLM orchestrator system.

    Smart agents:
    1. Receive structured input (tool arguments)
    2. Perform their specialized task
    3. Return a structured AgentReport (rendered as markdown)

    The markdown report format allows the orchestrator LLM to:
    - Quickly understand results via the summary
    - Reason about issues and adapt strategy
    - Access structured data via the JSON block
    """

    agent_type: AgentType
    name: str = "base"
    description: str = "Base agent"

    def __init__(self, debug: bool = False) -> None:
        self._debug = debug

    @abstractmethod
    async def execute(self, **kwargs: Any) -> AgentReport:
        """
        Execute the agent's task and return a structured report.

        Args:
            **kwargs: Tool arguments passed from the orchestrator

        Returns:
            AgentReport with results in both human-readable and machine-readable format
        """
        pass

    def _create_success_report(
        self,
        summary: str,
        **kwargs: Any,
    ) -> AgentReport:
        """Create a success report with the given parameters."""
        return AgentReport(
            agent_type=self.agent_type,
            agent_name=self.name,
            status=ReportStatus.SUCCESS,
            summary=summary,
            **kwargs,
        )

    def _create_failure_report(
        self,
        error: str,
        **kwargs: Any,
    ) -> AgentReport:
        """Create a failure report with the given error."""
        return AgentReport(
            agent_type=self.agent_type,
            agent_name=self.name,
            status=ReportStatus.FAILURE,
            summary=f"Failed: {error}",
            issues=[error],
            **kwargs,
        )

    def _create_partial_report(
        self,
        summary: str,
        issues: list[str],
        **kwargs: Any,
    ) -> AgentReport:
        """Create a partial success report with issues."""
        return AgentReport(
            agent_type=self.agent_type,
            agent_name=self.name,
            status=ReportStatus.PARTIAL,
            summary=summary,
            issues=issues,
            **kwargs,
        )

    def _log(self, message: str) -> None:
        """Log a debug message if debugging is enabled."""
        if self._debug:
            logger.info(f"[{self.name.upper()}] {message}")

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the tool definition for the orchestrator LLM.

        This defines how the orchestrator can call this agent.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._get_parameters_schema(),
            },
        }

    @abstractmethod
    def _get_parameters_schema(self) -> dict[str, Any]:
        """Get the JSON schema for this agent's parameters."""
        pass


class TimedExecution:
    """Context manager to time agent execution."""

    def __init__(self) -> None:
        self.start_time: float = 0
        self.end_time: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self) -> TimedExecution:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000


__all__ = ["SmartAgent", "TimedExecution"]
