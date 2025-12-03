"""Smart agents that communicate via structured markdown reports."""

from radarr_manager.discovery.smart.agents.base import SmartAgent
from radarr_manager.discovery.smart.agents.fetch import SmartFetchAgent
from radarr_manager.discovery.smart.agents.ranker import SmartRankerAgent
from radarr_manager.discovery.smart.agents.search import SmartSearchAgent
from radarr_manager.discovery.smart.agents.validator import SmartValidatorAgent

__all__ = [
    "SmartAgent",
    "SmartFetchAgent",
    "SmartSearchAgent",
    "SmartValidatorAgent",
    "SmartRankerAgent",
]
