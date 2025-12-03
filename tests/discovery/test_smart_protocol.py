"""Tests for the smart orchestrator protocol (agent communication format)."""

import json
import pytest

from radarr_manager.discovery.smart.protocol import (
    AgentReport,
    AgentType,
    MovieData,
    ReportSection,
    ReportStatus,
    ToolCall,
    ToolResult,
)


class TestMovieData:
    """Tests for MovieData dataclass."""

    def test_create_movie_data_minimal(self):
        """Test creating MovieData with minimal fields."""
        movie = MovieData(title="Test Movie")
        assert movie.title == "Test Movie"
        assert movie.year is None
        assert movie.overview is None
        assert movie.confidence == 0.8
        assert movie.sources == []
        assert movie.is_valid is True

    def test_create_movie_data_full(self):
        """Test creating MovieData with all fields."""
        movie = MovieData(
            title="Inception",
            year=2010,
            overview="A thief who steals corporate secrets...",
            confidence=0.95,
            sources=["rt_theaters", "imdb_moviemeter"],
            ratings={"rt_score": 87, "imdb_score": 8.8},
            metadata={"director": "Christopher Nolan"},
            is_valid=True,
            rejection_reason=None,
        )
        assert movie.title == "Inception"
        assert movie.year == 2010
        assert movie.confidence == 0.95
        assert len(movie.sources) == 2
        assert movie.ratings["rt_score"] == 87

    def test_movie_data_to_markdown_row(self):
        """Test markdown row generation."""
        movie = MovieData(
            title="Dune",
            year=2024,
            confidence=0.9,
            sources=["rt_theaters"],
            overview="A brief overview of the movie plot.",
        )
        row = movie.to_markdown_row()
        assert "| Dune |" in row
        assert "| 2024 |" in row
        assert "| 0.90 |" in row
        assert "rt_theaters" in row

    def test_movie_data_to_dict(self):
        """Test conversion to dictionary."""
        movie = MovieData(
            title="Test",
            year=2024,
            confidence=0.85,
            sources=["source1"],
        )
        data = movie.to_dict()
        assert data["title"] == "Test"
        assert data["year"] == 2024
        assert data["confidence"] == 0.85
        assert data["sources"] == ["source1"]

    def test_movie_data_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "title": "From Dict Movie",
            "year": 2023,
            "confidence": 0.75,
            "sources": ["web_search"],
        }
        movie = MovieData.from_dict(data)
        assert movie.title == "From Dict Movie"
        assert movie.year == 2023
        assert movie.confidence == 0.75

    def test_movie_data_roundtrip(self):
        """Test to_dict and from_dict roundtrip."""
        original = MovieData(
            title="Roundtrip Test",
            year=2025,
            overview="Testing roundtrip conversion",
            confidence=0.88,
            sources=["source1", "source2"],
            ratings={"rt": 90},
            metadata={"key": "value"},
        )
        data = original.to_dict()
        restored = MovieData.from_dict(data)
        assert restored.title == original.title
        assert restored.year == original.year
        assert restored.overview == original.overview
        assert restored.confidence == original.confidence
        assert restored.sources == original.sources


class TestAgentReport:
    """Tests for AgentReport dataclass."""

    def test_create_agent_report_minimal(self):
        """Test creating minimal AgentReport."""
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.SUCCESS,
            summary="Fetched 15 movies",
        )
        assert report.agent_type == AgentType.FETCH
        assert report.agent_name == "fetch_movies"
        assert report.status == ReportStatus.SUCCESS
        assert report.summary == "Fetched 15 movies"
        assert report.movies == []
        assert report.issues == []

    def test_create_agent_report_with_movies(self):
        """Test creating AgentReport with movies."""
        movies = [
            MovieData(title="Movie 1", year=2024),
            MovieData(title="Movie 2", year=2023),
        ]
        report = AgentReport(
            agent_type=AgentType.SEARCH,
            agent_name="search_movies",
            status=ReportStatus.SUCCESS,
            summary="Found 2 movies",
            movies=movies,
            stats={"query": "horror movies"},
        )
        assert len(report.movies) == 2
        assert report.movies[0].title == "Movie 1"
        assert report.stats["query"] == "horror movies"

    def test_agent_report_to_markdown(self):
        """Test markdown rendering."""
        movies = [
            MovieData(title="Test Movie", year=2024, confidence=0.9, sources=["rt"]),
        ]
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.SUCCESS,
            summary="Fetched 1 movie",
            movies=movies,
            stats={"source": "RT"},
            execution_time_ms=150.5,
        )
        markdown = report.to_markdown()

        # Check structure
        assert "## Agent Report: fetch_movies" in markdown
        assert "**Status**: success" in markdown
        assert "**Summary**: Fetched 1 movie" in markdown
        assert "### Movies Found" in markdown
        assert "| Test Movie |" in markdown
        assert "### Stats" in markdown
        assert "Execution time:" in markdown  # Time may vary slightly
        assert "### Data (JSON)" in markdown
        assert "```json" in markdown

    def test_agent_report_to_markdown_with_issues(self):
        """Test markdown rendering with issues."""
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.PARTIAL,
            summary="Fetched some movies",
            issues=["Connection timeout", "Some data missing"],
        )
        markdown = report.to_markdown()
        assert "### Issues" in markdown
        assert "- Connection timeout" in markdown
        assert "- Some data missing" in markdown

    def test_agent_report_to_markdown_with_sections(self):
        """Test markdown rendering with custom sections."""
        sections = [
            ReportSection(heading="Source Details", content="- URL: https://example.com"),
        ]
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.SUCCESS,
            summary="Success",
            sections=sections,
        )
        markdown = report.to_markdown()
        assert "### Source Details" in markdown
        assert "- URL: https://example.com" in markdown

    def test_agent_report_from_markdown(self):
        """Test parsing markdown back to AgentReport."""
        movies = [
            MovieData(title="Parsed Movie", year=2024, confidence=0.85),
        ]
        original = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.SUCCESS,
            summary="Fetched 1 movie",
            movies=movies,
            stats={"count": 1},
        )
        markdown = original.to_markdown()
        parsed = AgentReport.from_markdown(markdown)

        assert parsed.agent_name == "fetch_movies"
        assert parsed.status == ReportStatus.SUCCESS
        assert len(parsed.movies) == 1
        assert parsed.movies[0].title == "Parsed Movie"


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_create_tool_call(self):
        """Test creating ToolCall."""
        call = ToolCall(
            tool_name="fetch_movies",
            arguments={"url": "https://example.com", "parser": "generic"},
            call_id="call_123",
        )
        assert call.tool_name == "fetch_movies"
        assert call.arguments["url"] == "https://example.com"
        assert call.call_id == "call_123"

    def test_tool_call_to_dict(self):
        """Test ToolCall to_dict."""
        call = ToolCall(
            tool_name="search_movies",
            arguments={"query": "horror"},
            call_id="call_456",
        )
        data = call.to_dict()
        assert data["tool_name"] == "search_movies"
        assert data["arguments"]["query"] == "horror"
        assert data["call_id"] == "call_456"


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_create_tool_result_success(self):
        """Test creating successful ToolResult."""
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.SUCCESS,
            summary="Success",
        )
        result = ToolResult(
            call_id="call_123",
            tool_name="fetch_movies",
            report=report,
            success=True,
        )
        assert result.success is True
        assert result.error is None
        assert result.report.summary == "Success"

    def test_create_tool_result_failure(self):
        """Test creating failed ToolResult."""
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.FAILURE,
            summary="Failed",
        )
        result = ToolResult(
            call_id="call_456",
            tool_name="fetch_movies",
            report=report,
            success=False,
            error="Connection refused",
        )
        assert result.success is False
        assert result.error == "Connection refused"

    def test_tool_result_to_markdown_success(self):
        """Test markdown rendering for success."""
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.SUCCESS,
            summary="Fetched 10 movies",
        )
        result = ToolResult(
            call_id="call_789",
            tool_name="fetch_movies",
            report=report,
            success=True,
        )
        markdown = result.to_markdown()
        assert "## Agent Report: fetch_movies" in markdown
        assert "Fetched 10 movies" in markdown

    def test_tool_result_to_markdown_error(self):
        """Test markdown rendering for error."""
        report = AgentReport(
            agent_type=AgentType.FETCH,
            agent_name="fetch_movies",
            status=ReportStatus.FAILURE,
            summary="Failed",
        )
        result = ToolResult(
            call_id="call_error",
            tool_name="fetch_movies",
            report=report,
            success=False,
            error="Network error occurred",
        )
        markdown = result.to_markdown()
        assert "## Tool Error: fetch_movies" in markdown
        assert "Network error occurred" in markdown


class TestAgentType:
    """Tests for AgentType enum."""

    def test_agent_types(self):
        """Test all agent types exist."""
        assert AgentType.FETCH.value == "fetch"
        assert AgentType.SEARCH.value == "search"
        assert AgentType.VALIDATOR.value == "validator"
        assert AgentType.RANKER.value == "ranker"


class TestReportStatus:
    """Tests for ReportStatus enum."""

    def test_report_statuses(self):
        """Test all report statuses exist."""
        assert ReportStatus.SUCCESS.value == "success"
        assert ReportStatus.PARTIAL.value == "partial"
        assert ReportStatus.FAILURE.value == "failure"
