"""Tests for smart agents."""

import json
import pytest
import respx
from httpx import Response

from radarr_manager.discovery.smart.agents import (
    SmartFetchAgent,
    SmartSearchAgent,
    SmartValidatorAgent,
    SmartRankerAgent,
)
from radarr_manager.discovery.smart.protocol import (
    AgentType,
    MovieData,
    ReportStatus,
)


class TestSmartValidatorAgent:
    """Tests for SmartValidatorAgent - no external dependencies."""

    @pytest.fixture
    def validator(self):
        """Create a validator agent."""
        return SmartValidatorAgent(debug=True)

    @pytest.mark.asyncio
    async def test_validate_empty_list(self, validator):
        """Test validation of empty movie list."""
        report = await validator.execute(movies=[])
        assert report.status == ReportStatus.FAILURE
        assert "No movies provided" in report.summary

    @pytest.mark.asyncio
    async def test_validate_valid_movies(self, validator):
        """Test validation of valid movies."""
        movies = [
            {"title": "Inception", "year": 2010, "confidence": 0.9},
            {"title": "The Matrix", "year": 1999, "confidence": 0.85},
        ]
        report = await validator.execute(movies=movies)
        assert report.status == ReportStatus.SUCCESS
        assert len(report.movies) == 2
        assert report.stats["valid_count"] == 2
        assert report.stats["rejected_count"] == 0

    @pytest.mark.asyncio
    async def test_validate_filters_duplicates(self, validator):
        """Test that duplicates are merged."""
        movies = [
            {"title": "Inception", "year": 2010, "sources": ["rt"]},
            {"title": "Inception", "year": 2010, "sources": ["imdb"]},
        ]
        report = await validator.execute(movies=movies, deduplicate=True)
        assert len(report.movies) == 1
        # Sources should be merged
        assert len(report.movies[0].sources) >= 2
        assert report.stats["duplicates_merged"] >= 1

    @pytest.mark.asyncio
    async def test_validate_filters_invalid_titles(self, validator):
        """Test that invalid titles are filtered."""
        movies = [
            {"title": "Good Movie", "year": 2024},
            {"title": "95%", "year": 2024},  # Contains percentage
            {"title": "2024", "year": 2024},  # Year only
        ]
        report = await validator.execute(movies=movies, filter_tv_shows=True)
        # Only valid movie should remain
        assert len(report.movies) == 1
        assert report.movies[0].title == "Good Movie"

    @pytest.mark.asyncio
    async def test_validate_filters_collections(self, validator):
        """Test that collections are filtered."""
        movies = [
            {"title": "Inception", "year": 2010},
            {"title": "Marvel Complete Collection", "year": 2023},
            {"title": "Star Wars Trilogy Box Set", "year": 2020},
        ]
        report = await validator.execute(movies=movies, filter_collections=True)
        assert len(report.movies) == 1
        assert report.movies[0].title == "Inception"

    @pytest.mark.asyncio
    async def test_validate_min_confidence(self, validator):
        """Test minimum confidence filtering."""
        movies = [
            {"title": "High Confidence", "confidence": 0.9},
            {"title": "Low Confidence", "confidence": 0.3},
        ]
        report = await validator.execute(movies=movies, min_confidence=0.5)
        assert len(report.movies) == 1
        assert report.movies[0].title == "High Confidence"

    @pytest.mark.asyncio
    async def test_validate_report_structure(self, validator):
        """Test report has proper structure."""
        movies = [{"title": "Test Movie", "year": 2024}]
        report = await validator.execute(movies=movies)

        assert report.agent_type == AgentType.VALIDATOR
        assert report.agent_name == "validate_movies"
        assert "Validated" in report.summary
        assert report.execution_time_ms >= 0  # May be 0 if very fast
        assert "total_input" in report.stats

    def test_get_tool_definition(self, validator):
        """Test tool definition schema."""
        tool_def = validator.get_tool_definition()
        assert tool_def["type"] == "function"
        assert tool_def["function"]["name"] == "validate_movies"
        assert "movies" in tool_def["function"]["parameters"]["properties"]
        assert "deduplicate" in tool_def["function"]["parameters"]["properties"]


class TestSmartFetchAgent:
    """Tests for SmartFetchAgent - requires mocking HTTP."""

    @pytest.fixture
    def fetch_agent(self):
        """Create a fetch agent."""
        return SmartFetchAgent(
            api_url="http://localhost:11235",
            debug=True,
        )

    @pytest.mark.asyncio
    async def test_fetch_no_url(self, fetch_agent):
        """Test fetch without URL."""
        report = await fetch_agent.execute(url="", parser="generic")
        assert report.status == ReportStatus.FAILURE
        assert "No URL provided" in report.summary

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_success(self, fetch_agent):
        """Test successful fetch with mocked Crawl4AI."""
        # Mock Crawl4AI response
        mock_markdown = """
        # Movies in Theaters

        1. **Dune: Part Two** (2024)
        2. **Deadpool & Wolverine** (2024)
        """
        respx.post("http://localhost:11235/crawl").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "results": [{"markdown": mock_markdown}],
                },
            )
        )

        report = await fetch_agent.execute(
            url="https://example.com/movies",
            parser="generic",
            max_movies=10,
        )

        assert report.status == ReportStatus.SUCCESS
        assert report.agent_type == AgentType.FETCH
        assert "content_size_bytes" in report.stats

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_failure(self, fetch_agent):
        """Test fetch failure handling."""
        respx.post("http://localhost:11235/crawl").mock(
            return_value=Response(500, json={"error": "Server error"})
        )

        report = await fetch_agent.execute(
            url="https://example.com/movies",
            parser="generic",
        )

        assert report.status == ReportStatus.FAILURE
        assert len(report.issues) > 0

    def test_get_tool_definition(self, fetch_agent):
        """Test tool definition schema."""
        tool_def = fetch_agent.get_tool_definition()
        assert tool_def["function"]["name"] == "fetch_movies"
        assert "url" in tool_def["function"]["parameters"]["properties"]
        assert "parser" in tool_def["function"]["parameters"]["properties"]


class TestSmartSearchAgent:
    """Tests for SmartSearchAgent - requires mocking OpenAI."""

    @pytest.fixture
    def search_agent(self):
        """Create a search agent with mock API key."""
        return SmartSearchAgent(
            api_key="test-key",
            model="gpt-4o-mini",
            debug=True,
        )

    @pytest.fixture
    def search_agent_no_key(self):
        """Create a search agent without API key."""
        return SmartSearchAgent(debug=True)

    @pytest.mark.asyncio
    async def test_search_no_query(self, search_agent):
        """Test search without query."""
        report = await search_agent.execute(query="")
        assert report.status == ReportStatus.FAILURE
        assert "No search query" in report.summary

    @pytest.mark.asyncio
    async def test_search_no_api_key(self, search_agent_no_key):
        """Test search without API key."""
        report = await search_agent_no_key.execute(query="horror movies")
        assert report.status == ReportStatus.FAILURE
        assert "No API key" in report.summary

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_success(self, search_agent):
        """Test successful search with mocked OpenAI."""
        mock_response = {
            "output": [
                {
                    "content": [
                        {
                            "text": json.dumps({
                                "movies": [
                                    {"title": "Nosferatu", "year": 2024, "confidence": 0.9},
                                    {"title": "Smile 2", "year": 2024, "confidence": 0.85},
                                ]
                            })
                        }
                    ]
                }
            ]
        }
        respx.post("https://api.openai.com/v1/responses").mock(
            return_value=Response(200, json=mock_response)
        )

        report = await search_agent.execute(
            query="horror movies 2024",
            max_results=10,
        )

        assert report.status == ReportStatus.SUCCESS
        assert len(report.movies) == 2
        assert report.movies[0].title == "Nosferatu"

    def test_get_tool_definition(self, search_agent):
        """Test tool definition schema."""
        tool_def = search_agent.get_tool_definition()
        assert tool_def["function"]["name"] == "search_movies"
        assert "query" in tool_def["function"]["parameters"]["properties"]
        assert "criteria" in tool_def["function"]["parameters"]["properties"]


class TestSmartRankerAgent:
    """Tests for SmartRankerAgent."""

    @pytest.fixture
    def ranker_agent(self):
        """Create a ranker agent with mock API key."""
        return SmartRankerAgent(
            api_key="test-key",
            model="gpt-4o-mini",
            debug=True,
        )

    @pytest.fixture
    def ranker_no_key(self):
        """Create a ranker agent without API key."""
        return SmartRankerAgent(debug=True)

    @pytest.mark.asyncio
    async def test_rank_no_movies(self, ranker_agent):
        """Test ranking without movies."""
        report = await ranker_agent.execute(movies=[])
        assert report.status == ReportStatus.FAILURE
        assert "No movies provided" in report.summary

    @pytest.mark.asyncio
    async def test_simple_rank_fallback(self, ranker_no_key):
        """Test simple ranking without LLM."""
        movies = [
            {"title": "Low Conf", "confidence": 0.5, "sources": ["rt"]},
            {"title": "High Conf", "confidence": 0.9, "sources": ["rt", "imdb"]},
            {"title": "Med Conf", "confidence": 0.7, "sources": ["imdb"]},
        ]
        report = await ranker_no_key.execute(movies=movies, limit=10)

        assert report.status == ReportStatus.PARTIAL  # Fallback mode
        assert len(report.movies) == 3
        # Should be sorted by confidence descending
        assert report.movies[0].title == "High Conf"
        assert report.movies[1].title == "Med Conf"
        assert report.movies[2].title == "Low Conf"

    @pytest.mark.asyncio
    @respx.mock
    async def test_rank_with_llm(self, ranker_agent):
        """Test ranking with LLM."""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "ranked_movies": [
                                {"title": "Best Movie", "year": 2024, "confidence": 0.95, "overview": "Great film"},
                                {"title": "Good Movie", "year": 2024, "confidence": 0.8},
                            ],
                            "excluded_movies": [
                                {"title": "Bad Movie", "reason": "Doesn't fit criteria"},
                            ],
                        })
                    }
                }
            ]
        }
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(200, json=mock_response)
        )

        movies = [
            {"title": "Best Movie", "year": 2024},
            {"title": "Good Movie", "year": 2024},
            {"title": "Bad Movie", "year": 2024},
        ]
        report = await ranker_agent.execute(
            movies=movies,
            criteria="Best movies for 2024",
            limit=5,
        )

        assert report.status == ReportStatus.SUCCESS
        assert len(report.movies) == 2
        assert report.movies[0].confidence == 0.95
        assert report.stats["excluded_count"] == 1

    def test_get_tool_definition(self, ranker_agent):
        """Test tool definition schema."""
        tool_def = ranker_agent.get_tool_definition()
        assert tool_def["function"]["name"] == "rank_movies"
        assert "movies" in tool_def["function"]["parameters"]["properties"]
        assert "criteria" in tool_def["function"]["parameters"]["properties"]
        assert "limit" in tool_def["function"]["parameters"]["properties"]
