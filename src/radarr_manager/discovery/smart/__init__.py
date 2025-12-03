"""Smart LLM Orchestrator - agents talking to agents with structured markdown communication."""

from radarr_manager.discovery.smart.agents import (
    SmartFetchAgent,
    SmartRankerAgent,
    SmartSearchAgent,
    SmartValidatorAgent,
)
from radarr_manager.discovery.smart.orchestrator import (
    SmartOrchestrator,
    SmartOrchestratorConfig,
)
from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    MovieData,
    ReportSection,
    ToolCall,
    ToolResult,
)

__all__ = [
    # Protocol
    "AgentReport",
    "MovieData",
    "ReportSection",
    "ToolCall",
    "ToolResult",
    # Orchestrator
    "SmartOrchestrator",
    "SmartOrchestratorConfig",
    # Agents
    "SmartFetchAgent",
    "SmartSearchAgent",
    "SmartValidatorAgent",
    "SmartRankerAgent",
]
