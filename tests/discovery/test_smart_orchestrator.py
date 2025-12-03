"""Tests for the SmartOrchestrator."""

import json
import pytest
import respx
from httpx import Response

from radarr_manager.discovery.smart.orchestrator import (
    SmartOrchestrator,
    SmartOrchestratorConfig,
)


class TestSmartOrchestratorConfig:
    """Tests for SmartOrchestratorConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = SmartOrchestratorConfig()
        assert config.orchestrator_model == "gpt-4o"
        assert config.agent_model == "gpt-4o-mini"
        assert config.max_iterations == 5
        assert config.has_orchestrator_llm is False

    def test_config_with_api_key(self):
        """Test configuration with API key."""
        config = SmartOrchestratorConfig(orchestrator_api_key="test-key")
        assert config.has_orchestrator_llm is True


class TestSmartOrchestratorDeterministic:
    """Tests for SmartOrchestrator in deterministic mode (no orchestrator LLM)."""

    @pytest.fixture
    def orchestrator_no_llm(self):
        """Create orchestrator without orchestrator LLM."""
        config = SmartOrchestratorConfig(
            orchestrator_api_key=None,  # No orchestrator LLM
            agent_api_key="test-agent-key",
            agent_model="gpt-4o-mini",
            scraper_api_url="http://localhost:11235",
        )
        return SmartOrchestrator(config=config, debug=True)

    @pytest.mark.asyncio
    @respx.mock
    async def test_deterministic_discover(self, orchestrator_no_llm):
        """Test discovery in deterministic mode."""
        # Mock Crawl4AI for RT theaters
        respx.post("http://localhost:11235/crawl").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "results": [{"markdown": "# Movies\n1. Test Movie (2024)"}],
                },
            )
        )

        # Mock OpenAI for search agent
        respx.post("https://api.openai.com/v1/responses").mock(
            return_value=Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "text": json.dumps({
                                        "movies": [
                                            {"title": "Search Movie", "year": 2024},
                                        ]
                                    })
                                }
                            ]
                        }
                    ]
                },
            )
        )

        # Mock OpenAI for ranker agent
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({
                                    "ranked_movies": [
                                        {"title": "Search Movie", "year": 2024, "confidence": 0.9},
                                    ],
                                    "excluded_movies": [],
                                })
                            }
                        }
                    ]
                },
            )
        )

        suggestions = await orchestrator_no_llm.discover(
            prompt="Find trending movies",
            limit=5,
            region="US",
        )

        # Should return some suggestions
        assert isinstance(suggestions, list)


class TestSmartOrchestratorWithLLM:
    """Tests for SmartOrchestrator with orchestrator LLM."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mock API key."""
        config = SmartOrchestratorConfig(
            orchestrator_api_key="test-orchestrator-key",
            orchestrator_model="gpt-4o",
            agent_api_key="test-agent-key",
            agent_model="gpt-4o-mini",
            scraper_api_url="http://localhost:11235",
            max_iterations=3,
        )
        return SmartOrchestrator(config=config, debug=True)

    @pytest.mark.asyncio
    @respx.mock
    async def test_orchestrator_single_iteration(self, orchestrator):
        """Test orchestrator with single tool call iteration."""
        # First call: orchestrator decides to fetch movies
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=[
                # First response: tool call
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "function": {
                                                "name": "validate_movies",
                                                "arguments": json.dumps({
                                                    "movies": [
                                                        {"title": "Test Movie", "year": 2024}
                                                    ]
                                                }),
                                            },
                                        },
                                        {
                                            "id": "call_2",
                                            "function": {
                                                "name": "rank_movies",
                                                "arguments": json.dumps({
                                                    "movies": [
                                                        {"title": "Test Movie", "year": 2024}
                                                    ],
                                                    "limit": 5,
                                                }),
                                            },
                                        },
                                    ],
                                }
                            }
                        ]
                    },
                ),
                # Ranker uses chat completions
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({
                                        "ranked_movies": [
                                            {"title": "Test Movie", "year": 2024, "confidence": 0.9}
                                        ],
                                        "excluded_movies": [],
                                    })
                                }
                            }
                        ]
                    },
                ),
                # Second orchestrator response: done
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "Found 1 movie matching your criteria.",
                                    "tool_calls": [],
                                }
                            }
                        ]
                    },
                ),
            ]
        )

        suggestions = await orchestrator.discover(
            prompt="Find movies",
            limit=5,
            region="US",
        )

        assert len(suggestions) == 1
        assert suggestions[0].title == "Test Movie"

    @pytest.mark.asyncio
    @respx.mock
    async def test_orchestrator_max_iterations(self, orchestrator):
        """Test that orchestrator respects max iterations."""
        # Mock orchestrator to always return tool calls (infinite loop)
        def mock_orchestrator_response(*args, **kwargs):
            return Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_loop",
                                        "function": {
                                            "name": "validate_movies",
                                            "arguments": json.dumps({
                                                "movies": [{"title": "Loop Movie"}]
                                            }),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        respx.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=mock_orchestrator_response
        )

        # Should not hang - will stop after max_iterations
        suggestions = await orchestrator.discover(
            prompt="Test max iterations",
            limit=5,
        )

        # Should complete without error (empty or minimal results)
        assert isinstance(suggestions, list)


class TestSmartOrchestratorTools:
    """Tests for tool execution in SmartOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mock API key."""
        config = SmartOrchestratorConfig(
            orchestrator_api_key="test-key",
            agent_api_key="test-agent-key",
        )
        return SmartOrchestrator(config=config, debug=True)

    def test_agents_initialized(self, orchestrator):
        """Test that all agents are initialized."""
        assert "fetch_movies" in orchestrator._agents
        assert "search_movies" in orchestrator._agents
        assert "validate_movies" in orchestrator._agents
        assert "rank_movies" in orchestrator._agents

    def test_tools_generated(self, orchestrator):
        """Test that tool definitions are generated."""
        assert len(orchestrator._tools) == 4
        tool_names = [t["function"]["name"] for t in orchestrator._tools]
        assert "fetch_movies" in tool_names
        assert "search_movies" in tool_names
        assert "validate_movies" in tool_names
        assert "rank_movies" in tool_names
