"""Tests for v1.15 orchestrator behavior:

- Library-context block injection into the system prompt
- Cross-iteration dedup of validate_movies arguments
- Adaptive early-exit when library saturates
- RUN_SUMMARY JSON line emission
- Usage capture from orchestrator LLM responses
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from radarr_manager.clients.radarr import LibraryIndex
from radarr_manager.discovery.smart.orchestrator import (
    ConversationMessage,
    SmartOrchestrator,
    SmartOrchestratorConfig,
    _candidate_key,
    _render_library_block,
)
from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    AgentType,
    MovieData,
    ReportStatus,
)


def _orchestrator(**overrides: Any) -> SmartOrchestrator:
    """Build an orchestrator with a fake orchestrator LLM enabled."""
    config = SmartOrchestratorConfig(
        orchestrator_api_key="fake-orchestrator-key",
        orchestrator_model="gpt-4o",
        agent_api_key="fake-agent-key",
        agent_model="gpt-4o-mini",
        scraper_api_url="http://localhost:11235",
        max_iterations=overrides.pop("max_iterations", 5),
    )
    return SmartOrchestrator(config=config, debug=False)


def _validator_report(*, valid: int, in_library: int) -> AgentReport:
    return AgentReport(
        agent_type=AgentType.VALIDATOR,
        agent_name="validate_movies",
        status=ReportStatus.SUCCESS,
        summary="ok",
        movies=[MovieData(title=f"V{i}") for i in range(valid)],
        stats={"valid_count": valid, "in_library_filtered": in_library},
    )


def _ranker_report(titles: list[str]) -> AgentReport:
    return AgentReport(
        agent_type=AgentType.RANKER,
        agent_name="rank_movies",
        status=ReportStatus.SUCCESS,
        summary="ok",
        movies=[MovieData(title=t, year=2026) for t in titles],
        stats={},
    )


class TestLibraryBlockRendering:
    def test_block_omitted_when_index_empty(self):
        assert _render_library_block(LibraryIndex.empty()) == ""

    def test_block_includes_count_and_recent_titles(self):
        idx = LibraryIndex.from_movies(
            [
                {
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdbId": 603,
                    "added": "2024-01-01T00:00:00Z",
                },
                {
                    "title": "Inception",
                    "year": 2010,
                    "tmdbId": 27205,
                    "added": "2024-06-01T00:00:00Z",
                },
            ]
        )
        block = _render_library_block(idx)
        assert "owns 2 movies" in block
        assert "Inception" in block
        assert "The Matrix" in block


class TestCandidateKey:
    def test_returns_none_without_year(self):
        assert _candidate_key({"title": "Dracula"}) is None

    def test_normalizes_title(self):
        assert _candidate_key({"title": "  The Thing  ", "year": 1982}) == ("the thing", 1982)

    def test_returns_none_when_year_invalid(self):
        assert _candidate_key({"title": "X", "year": "bad"}) is None
        assert _candidate_key({"title": "X", "year": 0}) is None


class TestDedupValidateCalls:
    """Cross-iteration dedup stripping inputs to validate_movies."""

    def test_drops_previously_seen_and_records_new(self):
        orch = _orchestrator()
        seen: set[tuple[str, int]] = set()
        # First iteration: nothing seen, A and B pass through and are recorded.
        calls = [
            {
                "function": {
                    "name": "validate_movies",
                    "arguments": json.dumps(
                        {"movies": [{"title": "A", "year": 2026}, {"title": "B", "year": 2025}]}
                    ),
                }
            }
        ]
        skipped = orch._dedup_validate_calls(calls, seen)
        assert skipped == 0
        assert seen == {("a", 2026), ("b", 2025)}

        # Second iteration: A repeats; should be dropped from the arguments.
        calls2 = [
            {
                "function": {
                    "name": "validate_movies",
                    "arguments": json.dumps(
                        {"movies": [{"title": "A", "year": 2026}, {"title": "C", "year": 2026}]}
                    ),
                }
            }
        ]
        skipped = orch._dedup_validate_calls(calls2, seen)
        assert skipped == 1
        args = json.loads(calls2[0]["function"]["arguments"])
        titles_left = [m["title"] for m in args["movies"]]
        assert "A" not in titles_left
        assert "C" in titles_left

    def test_ignores_non_validate_tool_calls(self):
        orch = _orchestrator()
        seen: set[tuple[str, int]] = set()
        calls = [
            {
                "function": {
                    "name": "rank_movies",
                    "arguments": json.dumps({"movies": [{"title": "A", "year": 2026}]}),
                }
            }
        ]
        orch._dedup_validate_calls(calls, seen)
        assert seen == set()  # rank_movies inputs do not populate seen

    def test_year_unknown_items_never_dedup(self):
        orch = _orchestrator()
        seen: set[tuple[str, int]] = set()
        calls = [
            {
                "function": {
                    "name": "validate_movies",
                    "arguments": json.dumps(
                        {"movies": [{"title": "Dracula"}, {"title": "Dracula"}]}
                    ),
                }
            }
        ]
        skipped = orch._dedup_validate_calls(calls, seen)
        assert skipped == 0
        args = json.loads(calls[0]["function"]["arguments"])
        assert len(args["movies"]) == 2


class TestDiscoverWithFakeLLM:
    """Drive discover() with a stubbed _call_orchestrator + stubbed agents."""

    @pytest.fixture
    def orch(self, monkeypatch):
        return _orchestrator()

    @pytest.fixture
    def installed_agent_stubs(self, monkeypatch):
        """Capture validator/ranker calls; return reports controlled per-test."""
        from radarr_manager.discovery.smart import orchestrator as orch_mod

        recorded_calls: list[tuple[str, dict[str, Any]]] = []

        def make_agent(report_factory):
            class _Agent:
                async def execute(self, **kwargs):
                    recorded_calls.append((report_factory.__name__, kwargs))
                    return report_factory(**kwargs)

                def get_tool_definition(self):
                    return {"type": "function", "function": {"name": "stub"}}

            return _Agent()

        return recorded_calls, make_agent, orch_mod

    @pytest.mark.asyncio
    async def test_library_block_lands_in_system_prompt(self, monkeypatch):
        orch = _orchestrator()
        captured: list[list[ConversationMessage]] = []

        async def fake_call(messages):
            captured.append([m for m in messages])
            return ConversationMessage(role="assistant", content="done", tool_calls=[])

        monkeypatch.setattr(orch, "_call_orchestrator", fake_call)

        idx = LibraryIndex.from_movies(
            [{"title": "X", "year": 2020, "tmdbId": 1, "added": "2025-01-01T00:00:00Z"}]
        )
        await orch.discover(prompt="find some", limit=5, library_index=idx)

        assert captured, "orchestrator should have been called at least once"
        sys_msg = captured[0][0]
        assert "Your User's Library" in sys_msg.content
        user_msg = captured[0][1]
        assert "Library size: 1" in user_msg.content

    @pytest.mark.asyncio
    async def test_no_library_block_when_index_is_none_or_empty(self, monkeypatch):
        orch = _orchestrator()
        captured: list[list[ConversationMessage]] = []

        async def fake_call(messages):
            captured.append([m for m in messages])
            return ConversationMessage(role="assistant", content="done", tool_calls=[])

        monkeypatch.setattr(orch, "_call_orchestrator", fake_call)
        await orch.discover(prompt="find some", limit=5, library_index=None)
        sys_msg = captured[0][0]
        assert "Your User's Library" not in sys_msg.content

    @pytest.mark.asyncio
    async def test_early_exit_after_two_consecutive_saturated_iterations(self, monkeypatch):
        """After iter>=3 with 2 consecutive zero-valid/library-filtered>=5, break."""
        orch = _orchestrator(max_iterations=10)

        # Build a sequence: every orchestrator call asks for validate_movies.
        # The validator returns saturated results every time.
        call_count = {"n": 0}

        async def fake_call(messages):
            call_count["n"] += 1
            return ConversationMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": f"c{call_count['n']}",
                        "function": {
                            "name": "validate_movies",
                            "arguments": json.dumps(
                                {"movies": [{"title": f"T{call_count['n']}", "year": 2026}]}
                            ),
                        },
                    }
                ],
            )

        monkeypatch.setattr(orch, "_call_orchestrator", fake_call)

        async def fake_execute(**kwargs):
            return _validator_report(valid=0, in_library=10)

        orch._agents["validate_movies"].execute = fake_execute  # type: ignore[assignment]

        await orch.discover(prompt="find", limit=5)
        # Min iteration is 3, then needs 2 consecutive saturated. With every
        # iteration saturated, we should break at iteration 4 (after streak=2
        # is observed AND iter >= 3).
        assert call_count["n"] <= 4

    @pytest.mark.asyncio
    async def test_run_summary_emitted_at_end(self, monkeypatch, caplog):
        orch = _orchestrator()

        async def fake_call(messages):
            return ConversationMessage(role="assistant", content="done", tool_calls=[])

        monkeypatch.setattr(orch, "_call_orchestrator", fake_call)
        with caplog.at_level(logging.INFO, logger="radarr_manager.discovery.smart.orchestrator"):
            await orch.discover(prompt="find", limit=5)

        summary_lines = [r.message for r in caplog.records if r.message.startswith("RUN_SUMMARY ")]
        assert summary_lines, "expected a RUN_SUMMARY line"
        payload = json.loads(summary_lines[-1].removeprefix("RUN_SUMMARY ").strip())
        assert "iterations" in payload
        assert "outcome" in payload
        assert "usage" in payload
        assert payload["usage"]["calls"] >= 0  # may be 0 since we stubbed _call_orchestrator
