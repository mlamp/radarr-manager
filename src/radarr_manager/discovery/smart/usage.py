"""LLM token + cost telemetry for smart-agentic discovery runs.

A single ``UsageCollector`` is created per discovery run and threaded through
the orchestrator and any agent that calls an LLM. Each call site records one
``LLMCall``; the collector aggregates totals and produces a cost estimate.

Cost numbers are best-effort: the price table is hardcoded as of
``PRICING_AS_OF`` and will drift. Treat ``estimated_cost_usd_estimated`` as a
ballpark for trend analysis, not for billing.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

PRICING_AS_OF = "2026-05-21"

# Per-model price in USD per 1000 tokens, (input, output).
# Source: OpenAI public pricing as of PRICING_AS_OF.
MODEL_PRICES_USD_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-2024-11-20": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o-mini-2024-07-18": (0.00015, 0.0006),
}

ApiKind = Literal["chat_completions", "responses"]


@dataclass(frozen=True)
class LLMCall:
    """A single LLM API call's accounting record."""

    component: str  # "orchestrator", "search_agent", "ranker_agent"
    model: str
    prompt_tokens: int
    completion_tokens: int
    api: ApiKind

    @classmethod
    def from_chat_completions(cls, *, component: str, model: str, data: dict[str, Any]) -> LLMCall:
        usage = data.get("usage") or {}
        return cls(
            component=component,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            api="chat_completions",
        )

    @classmethod
    def from_responses(cls, *, component: str, model: str, data: dict[str, Any]) -> LLMCall:
        usage = data.get("usage") or {}
        # Responses API uses input_tokens/output_tokens.
        # Fall back to prompt_tokens/completion_tokens for older shape.
        prompt = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        completion = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        return cls(
            component=component,
            model=model,
            prompt_tokens=int(prompt),
            completion_tokens=int(completion),
            api="responses",
        )


@dataclass
class UsageCollector:
    """Per-run accumulator for LLM usage. Not thread-safe; single asyncio loop."""

    calls: list[LLMCall] = field(default_factory=list)

    def record(self, call: LLMCall) -> None:
        self.calls.append(call)

    def total_tokens(self) -> dict[str, int]:
        prompt = sum(c.prompt_tokens for c in self.calls)
        completion = sum(c.completion_tokens for c in self.calls)
        return {
            "prompt": prompt,
            "completion": completion,
            "total": prompt + completion,
        }

    def per_model_tokens(self) -> dict[str, dict[str, int]]:
        per: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt": 0, "completion": 0, "calls": 0}
        )
        for c in self.calls:
            per[c.model]["prompt"] += c.prompt_tokens
            per[c.model]["completion"] += c.completion_tokens
            per[c.model]["calls"] += 1
        return dict(per)

    def estimated_cost_usd(self) -> float:
        unknown_models: set[str] = set()
        total = 0.0
        for c in self.calls:
            price = MODEL_PRICES_USD_PER_1K.get(c.model)
            if price is None:
                unknown_models.add(c.model)
                continue
            input_price, output_price = price
            total += (c.prompt_tokens / 1000.0) * input_price
            total += (c.completion_tokens / 1000.0) * output_price
        for model in unknown_models:
            logger.warning(
                "No pricing entry for model %r (priced at $0 in this estimate); "
                "update MODEL_PRICES_USD_PER_1K in discovery/smart/usage.py.",
                model,
            )
        return round(total, 6)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "calls": len(self.calls),
            "tokens": self.total_tokens(),
            "per_model": self.per_model_tokens(),
            "cost_usd_estimated": self.estimated_cost_usd(),
            "pricing_as_of": PRICING_AS_OF,
        }


__all__ = [
    "ApiKind",
    "LLMCall",
    "MODEL_PRICES_USD_PER_1K",
    "PRICING_AS_OF",
    "UsageCollector",
]
