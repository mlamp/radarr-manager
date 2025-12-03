"""Discovery agents for movie discovery."""

from radarr_manager.discovery.agents.analysis import (
    AnalysisAgent,
    AnalysisRequest,
    AnalysisResult,
)
from radarr_manager.discovery.agents.base import Agent, AgentMessage, AgentResult
from radarr_manager.discovery.agents.fetch import FetchAgent, FetchRequest, FetchResult

__all__ = [
    "Agent",
    "AgentMessage",
    "AgentResult",
    "FetchAgent",
    "FetchRequest",
    "FetchResult",
    "AnalysisAgent",
    "AnalysisRequest",
    "AnalysisResult",
]
