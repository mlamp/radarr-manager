"""Tests for the UsageCollector / LLMCall accounting in smart-agentic runs."""

from __future__ import annotations

import logging

import pytest

from radarr_manager.discovery.smart.usage import (
    MODEL_PRICES_USD_PER_1K,
    PRICING_AS_OF,
    LLMCall,
    UsageCollector,
)


class TestLLMCallFactories:
    """LLMCall.from_chat_completions and from_responses parse OpenAI usage shapes."""

    def test_from_chat_completions_extracts_prompt_and_completion(self):
        data = {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        call = LLMCall.from_chat_completions(component="orchestrator", model="gpt-4o", data=data)
        assert call.prompt_tokens == 100
        assert call.completion_tokens == 50
        assert call.api == "chat_completions"
        assert call.component == "orchestrator"

    def test_from_responses_uses_input_output_token_fields(self):
        data = {
            "output_text": "hi",
            "usage": {"input_tokens": 200, "output_tokens": 75},
        }
        call = LLMCall.from_responses(component="search_agent", model="gpt-4o-mini", data=data)
        assert call.prompt_tokens == 200
        assert call.completion_tokens == 75
        assert call.api == "responses"

    def test_missing_usage_block_yields_zero_counts(self):
        call = LLMCall.from_chat_completions(component="orchestrator", model="gpt-4o", data={})
        assert call.prompt_tokens == 0
        assert call.completion_tokens == 0

    def test_responses_falls_back_to_chat_completion_field_names(self):
        data = {"usage": {"prompt_tokens": 10, "completion_tokens": 4}}
        call = LLMCall.from_responses(component="search_agent", model="gpt-4o-mini", data=data)
        assert call.prompt_tokens == 10
        assert call.completion_tokens == 4


class TestUsageCollectorTotals:
    """Aggregation across multiple calls."""

    def test_total_tokens_sums_across_calls(self):
        c = UsageCollector()
        c.record(LLMCall("orchestrator", "gpt-4o", 100, 50, "chat_completions"))
        c.record(LLMCall("search_agent", "gpt-4o-mini", 200, 75, "responses"))
        totals = c.total_tokens()
        assert totals == {"prompt": 300, "completion": 125, "total": 425}

    def test_per_model_breakdown(self):
        c = UsageCollector()
        c.record(LLMCall("orchestrator", "gpt-4o", 100, 50, "chat_completions"))
        c.record(LLMCall("orchestrator", "gpt-4o", 200, 100, "chat_completions"))
        c.record(LLMCall("search_agent", "gpt-4o-mini", 50, 25, "responses"))
        per = c.per_model_tokens()
        assert per["gpt-4o"] == {"prompt": 300, "completion": 150, "calls": 2}
        assert per["gpt-4o-mini"] == {"prompt": 50, "completion": 25, "calls": 1}


class TestEstimatedCost:
    """estimated_cost_usd multiplies tokens by the pricing table."""

    def test_known_model_priced(self):
        c = UsageCollector()
        c.record(LLMCall("orchestrator", "gpt-4o", 1000, 1000, "chat_completions"))
        # gpt-4o = ($0.0025 input, $0.01 output) per 1K
        expected = (1000 / 1000) * 0.0025 + (1000 / 1000) * 0.01
        assert c.estimated_cost_usd() == pytest.approx(expected)

    def test_unknown_model_priced_at_zero_with_warning(self, caplog):
        c = UsageCollector()
        c.record(LLMCall("search_agent", "future-model-9000", 1000, 1000, "chat_completions"))
        with caplog.at_level(logging.WARNING):
            assert c.estimated_cost_usd() == 0.0
        assert any("future-model-9000" in r.message for r in caplog.records)

    def test_summary_dict_has_expected_keys(self):
        c = UsageCollector()
        c.record(LLMCall("orchestrator", "gpt-4o", 1000, 500, "chat_completions"))
        s = c.to_summary_dict()
        assert s["calls"] == 1
        assert s["tokens"]["total"] == 1500
        assert s["pricing_as_of"] == PRICING_AS_OF
        assert s["cost_usd_estimated"] > 0


def test_pricing_table_covers_default_models():
    """Make sure the models we configure by default have a pricing row."""
    for model in ("gpt-4o", "gpt-4o-mini"):
        assert model in MODEL_PRICES_USD_PER_1K
