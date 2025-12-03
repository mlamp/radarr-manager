"""Discovery prompt model - configuration for agentic discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class SourceType(str, Enum):
    """Type of discovery source."""

    SCRAPE = "scrape"
    WEB_SEARCH = "web_search"


@dataclass
class DiscoverySource:
    """A single discovery source (URL to scrape or query to search)."""

    type: SourceType
    parser: str | None = None  # Parser name for scrape sources
    url: str | None = None  # URL for scrape sources
    query: str | None = None  # Query for web_search sources
    priority: int = 1  # Lower = higher priority
    enabled: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.type, str):
            self.type = SourceType(self.type)

    def resolve_variables(self, variables: dict[str, Any]) -> DiscoverySource:
        """Return a new source with variables resolved."""
        resolved_url = self.url
        resolved_query = self.query

        if resolved_url:
            for key, value in variables.items():
                resolved_url = resolved_url.replace(f"{{{key}}}", str(value))

        if resolved_query:
            for key, value in variables.items():
                resolved_query = resolved_query.replace(f"{{{key}}}", str(value))

        return DiscoverySource(
            type=self.type,
            parser=self.parser,
            url=resolved_url,
            query=resolved_query,
            priority=self.priority,
            enabled=self.enabled,
        )


@dataclass
class LLMEnhancement:
    """Configuration for LLM enhancement pass."""

    enabled: bool = True
    prompt: str | None = None  # Custom prompt for enhancement
    add_descriptions: bool = True  # Add plot summaries
    validate_availability: bool = True  # Confirm theatrical availability


@dataclass
class DiscoveryPrompt:
    """
    Configuration for agentic movie discovery.

    Defines what to discover, where to look, and how to process results.
    """

    name: str
    description: str
    sources: list[DiscoverySource] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    llm_enhancement: LLMEnhancement = field(default_factory=LLMEnhancement)
    fallback_to_web_search: bool = True
    limit: int = 50

    @classmethod
    def from_yaml(cls, path: Path | str) -> DiscoveryPrompt:
        """Load a discovery prompt from a YAML file."""
        path = Path(path)
        with path.open("r") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_yaml_string(cls, yaml_string: str) -> DiscoveryPrompt:
        """Load a discovery prompt from a YAML string."""
        data = yaml.safe_load(yaml_string)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryPrompt:
        """Create a DiscoveryPrompt from a dictionary."""
        sources = []
        for src in data.get("sources", []):
            sources.append(
                DiscoverySource(
                    type=SourceType(src.get("type", "scrape")),
                    parser=src.get("parser"),
                    url=src.get("url"),
                    query=src.get("query"),
                    priority=src.get("priority", 1),
                    enabled=src.get("enabled", True),
                )
            )

        llm_data = data.get("llm_enhancement", {})
        if isinstance(llm_data, bool):
            llm_enhancement = LLMEnhancement(enabled=llm_data)
        else:
            llm_enhancement = LLMEnhancement(
                enabled=llm_data.get("enabled", True),
                prompt=llm_data.get("prompt"),
                add_descriptions=llm_data.get("add_descriptions", True),
                validate_availability=llm_data.get("validate_availability", True),
            )

        return cls(
            name=data.get("name", "custom"),
            description=data.get("description", "Custom discovery prompt"),
            sources=sources,
            variables=data.get("variables", {}),
            llm_enhancement=llm_enhancement,
            fallback_to_web_search=data.get("fallback_to_web_search", True),
            limit=data.get("limit", 50),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "sources": [
                {
                    "type": src.type.value,
                    "parser": src.parser,
                    "url": src.url,
                    "query": src.query,
                    "priority": src.priority,
                    "enabled": src.enabled,
                }
                for src in self.sources
            ],
            "variables": self.variables,
            "llm_enhancement": {
                "enabled": self.llm_enhancement.enabled,
                "prompt": self.llm_enhancement.prompt,
                "add_descriptions": self.llm_enhancement.add_descriptions,
                "validate_availability": self.llm_enhancement.validate_availability,
            },
            "fallback_to_web_search": self.fallback_to_web_search,
            "limit": self.limit,
        }

    def get_resolved_sources(self) -> list[DiscoverySource]:
        """Get sources with variables resolved, sorted by priority."""
        resolved = [src.resolve_variables(self.variables) for src in self.sources if src.enabled]
        return sorted(resolved, key=lambda s: s.priority)


__all__ = ["DiscoveryPrompt", "DiscoverySource", "SourceType", "LLMEnhancement"]
