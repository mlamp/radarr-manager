"""Tests for OpenAI provider functionality."""

import pytest
import json
from unittest.mock import AsyncMock, patch
from datetime import datetime

from radarr_manager.providers.openai import OpenAIProvider
from radarr_manager.providers.base import ProviderError
from radarr_manager.models import MovieSuggestion
from tests.fixtures.openai_responses import (
    VALID_JSON_RESPONSE,
    EMPTY_SUGGESTIONS_RESPONSE,
    MALFORMED_JSON_RESPONSE,
    RESPONSE_WITH_INVALID_DATES,
    RESPONSE_WITH_MISSING_FIELDS,
    MockOpenAIResponse,
    VALID_JSON_RESPONSE_TEXT,
    JSON_WITH_MARKDOWN_WRAPPER,
    JSON_WITH_EXTRA_TEXT,
    NON_JSON_RESPONSE,
)


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    mock_client = AsyncMock()
    mock_client.responses = AsyncMock()
    return mock_client


@pytest.fixture
def openai_provider(mock_openai_client):
    """Create an OpenAI provider with mocked client."""
    return OpenAIProvider(
        api_key="test-api-key",
        model="gpt-4o-mini",
        region="US",
        cache_ttl_hours=6,
        client=mock_openai_client,
    )


class TestOpenAIProviderInitialization:
    """Test OpenAI provider initialization."""

    def test_initialization_with_api_key(self):
        """Test successful initialization with API key."""
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4o",
            region="EU",
            cache_ttl_hours=12,
        )

        assert provider.name == "openai"
        assert provider._model == "gpt-4o"
        assert provider._region == "EU"
        assert provider._cache_ttl_hours == 12

    def test_initialization_without_api_key(self):
        """Test initialization fails without API key."""
        with pytest.raises(ProviderError, match="OPENAI_API_KEY is required"):
            OpenAIProvider(
                api_key="",
                model="gpt-4o-mini",
                region="US",
                cache_ttl_hours=6,
            )

    def test_initialization_with_defaults(self):
        """Test initialization with default values."""
        provider = OpenAIProvider(
            api_key="test-key",
            model=None,
            region=None,
            cache_ttl_hours=6,
        )

        assert provider._model == "gpt-4o-mini"
        assert provider._region is None

    def test_initialization_with_custom_client(self, mock_openai_client):
        """Test initialization with custom client."""
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4o-mini",
            region="US",
            cache_ttl_hours=6,
            client=mock_openai_client,
        )

        assert provider._client == mock_openai_client


class TestOpenAIProviderDiscover:
    """Test OpenAI provider discover functionality."""

    @pytest.mark.asyncio
    async def test_discover_successful_response(self, openai_provider, mock_openai_client):
        """Test successful movie discovery."""
        # Mock successful OpenAI API response
        mock_response = MockOpenAIResponse(output_text=json.dumps(VALID_JSON_RESPONSE))
        mock_openai_client.responses.create.return_value = mock_response

        suggestions = await openai_provider.discover(limit=2, region="US")

        assert len(suggestions) == 2
        assert isinstance(suggestions[0], MovieSuggestion)
        assert suggestions[0].title == "Dune: Part Two"
        assert suggestions[0].confidence == 0.95
        assert suggestions[0].franchise == "Dune"
        assert suggestions[1].title == "Deadpool & Wolverine"

        # Verify OpenAI API was called correctly
        mock_openai_client.responses.create.assert_called_once()
        call_args = mock_openai_client.responses.create.call_args

        assert call_args.kwargs["model"] == "gpt-4o-mini"
        assert call_args.kwargs["temperature"] == 0.3
        assert call_args.kwargs["tools"] == [{"type": "web_search"}]

        # Check system prompt
        input_messages = call_args.kwargs["input"]
        assert len(input_messages) == 2
        assert input_messages[0]["role"] == "system"
        assert "film research assistant" in input_messages[0]["content"][0]["text"]

        # Check user prompt
        assert input_messages[1]["role"] == "user"
        user_prompt = input_messages[1]["content"][0]["text"]
        assert "at most 2 movies" in user_prompt
        assert "region US" in user_prompt

    @pytest.mark.asyncio
    async def test_discover_with_region_override(self, openai_provider, mock_openai_client):
        """Test discovery with region override."""
        mock_response = MockOpenAIResponse(output_text=json.dumps(EMPTY_SUGGESTIONS_RESPONSE))
        mock_openai_client.responses.create.return_value = mock_response

        await openai_provider.discover(limit=3, region="EU")

        # Verify the prompt includes the overridden region
        call_args = mock_openai_client.responses.create.call_args
        user_prompt = call_args.kwargs["input"][1]["content"][0]["text"]
        assert "region EU" in user_prompt

    @pytest.mark.asyncio
    async def test_discover_uses_provider_region_as_default(self, mock_openai_client):
        """Test discovery uses provider's configured region when none specified."""
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4o-mini",
            region="CA",
            cache_ttl_hours=6,
            client=mock_openai_client,
        )

        mock_response = MockOpenAIResponse(output_text=json.dumps(EMPTY_SUGGESTIONS_RESPONSE))
        mock_openai_client.responses.create.return_value = mock_response

        await provider.discover(limit=1)

        call_args = mock_openai_client.responses.create.call_args
        user_prompt = call_args.kwargs["input"][1]["content"][0]["text"]
        assert "region CA" in user_prompt

    @pytest.mark.asyncio
    async def test_discover_defaults_to_us_region(self, mock_openai_client):
        """Test discovery defaults to US when no region configured."""
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4o-mini",
            region=None,
            cache_ttl_hours=6,
            client=mock_openai_client,
        )

        mock_response = MockOpenAIResponse(output_text=json.dumps(EMPTY_SUGGESTIONS_RESPONSE))
        mock_openai_client.responses.create.return_value = mock_response

        await provider.discover(limit=1)

        call_args = mock_openai_client.responses.create.call_args
        user_prompt = call_args.kwargs["input"][1]["content"][0]["text"]
        assert "region US" in user_prompt

    @pytest.mark.asyncio
    async def test_discover_empty_suggestions(self, openai_provider, mock_openai_client):
        """Test discovery with empty suggestions."""
        mock_response = MockOpenAIResponse(output_text=json.dumps(EMPTY_SUGGESTIONS_RESPONSE))
        mock_openai_client.responses.create.return_value = mock_response

        suggestions = await openai_provider.discover(limit=5)

        assert len(suggestions) == 0

    @pytest.mark.asyncio
    async def test_discover_limits_results(self, openai_provider, mock_openai_client):
        """Test discovery respects limit parameter."""
        # Create response with more suggestions than requested
        large_response = {
            "suggestions": [
                {"title": f"Movie {i}", "confidence": 0.5, "sources": ["test.com"]}
                for i in range(10)
            ]
        }
        mock_response = MockOpenAIResponse(output_text=json.dumps(large_response))
        mock_openai_client.responses.create.return_value = mock_response

        suggestions = await openai_provider.discover(limit=3)

        assert len(suggestions) == 3
        assert suggestions[0].title == "Movie 0"
        assert suggestions[2].title == "Movie 2"

    @pytest.mark.asyncio
    async def test_discover_openai_api_error(self, openai_provider, mock_openai_client):
        """Test discovery handles OpenAI API errors."""
        mock_openai_client.responses.create.side_effect = Exception("API Error")

        with pytest.raises(ProviderError, match="OpenAI request failed: API Error"):
            await openai_provider.discover(limit=1)

    @pytest.mark.asyncio
    async def test_discover_invalid_suggestion_data(self, openai_provider, mock_openai_client):
        """Test discovery handles invalid suggestion data."""
        # Response with invalid data that can't be validated by Pydantic
        invalid_response = {
            "suggestions": [
                {
                    "title": "Test Movie",
                    "confidence": "invalid-confidence",  # Should be float
                    "sources": "not-a-list",  # Should be list
                }
            ]
        }
        mock_response = MockOpenAIResponse(output_text=json.dumps(invalid_response))
        mock_openai_client.responses.create.return_value = mock_response

        with pytest.raises(ProviderError, match="Invalid suggestion payload"):
            await openai_provider.discover(limit=1)

    @pytest.mark.asyncio
    async def test_discover_includes_timestamp_in_prompt(self, openai_provider, mock_openai_client):
        """Test that discovery prompt includes current timestamp."""
        mock_response = MockOpenAIResponse(output_text=json.dumps(EMPTY_SUGGESTIONS_RESPONSE))
        mock_openai_client.responses.create.return_value = mock_response

        with patch('radarr_manager.providers.openai.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2024-09-19 16:30 UTC"

            await openai_provider.discover(limit=1)

            call_args = mock_openai_client.responses.create.call_args
            user_prompt = call_args.kwargs["input"][1]["content"][0]["text"]
            assert "2024-09-19 16:30 UTC" in user_prompt


class TestOpenAIJSONExtraction:
    """Test JSON extraction from OpenAI responses."""

    def test_extract_json_from_output_text(self, openai_provider):
        """Test JSON extraction from response.output_text."""
        response = MockOpenAIResponse(output_text=VALID_JSON_RESPONSE_TEXT)

        result = openai_provider._extract_json(response)

        assert "suggestions" in result
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["title"] == "Test Movie"

    def test_extract_json_from_output_content(self, openai_provider):
        """Test JSON extraction from response.output[].content[].text."""
        response = MockOpenAIResponse(output_content=VALID_JSON_RESPONSE_TEXT)

        result = openai_provider._extract_json(response)

        assert "suggestions" in result
        assert result["suggestions"][0]["title"] == "Test Movie"

    def test_extract_json_with_markdown_wrapper(self, openai_provider):
        """Test JSON extraction when wrapped in markdown code blocks."""
        response = MockOpenAIResponse(output_content=JSON_WITH_MARKDOWN_WRAPPER)

        result = openai_provider._extract_json(response)

        assert result["suggestions"][0]["title"] == "Wrapped Movie"

    def test_extract_json_with_extra_text(self, openai_provider):
        """Test JSON extraction from text with extra content."""
        response = MockOpenAIResponse(output_content=JSON_WITH_EXTRA_TEXT)

        result = openai_provider._extract_json(response)

        assert result["suggestions"][0]["title"] == "Extracted Movie"

    def test_extract_json_malformed_json(self, openai_provider):
        """Test JSON extraction fails with malformed JSON."""
        response = MockOpenAIResponse(output_content=MALFORMED_JSON_RESPONSE)

        with pytest.raises(ProviderError, match="Failed to parse OpenAI JSON payload"):
            openai_provider._extract_json(response)

    def test_extract_json_non_json_response(self, openai_provider):
        """Test JSON extraction fails with non-JSON response."""
        response = MockOpenAIResponse(output_content=NON_JSON_RESPONSE)

        with pytest.raises(ProviderError, match="Failed to parse OpenAI JSON payload"):
            openai_provider._extract_json(response)

    def test_extract_json_no_output(self, openai_provider):
        """Test JSON extraction fails when no output present."""
        response = MockOpenAIResponse()  # No output_text or output

        with pytest.raises(ProviderError, match="OpenAI response did not include output content"):
            openai_provider._extract_json(response)

    def test_extract_json_empty_output_content(self, openai_provider):
        """Test JSON extraction fails with empty output content."""
        response = MockOpenAIResponse(output_content="")

        with pytest.raises(ProviderError, match="Unable to parse structured response from OpenAI"):
            openai_provider._extract_json(response)


class TestOpenAIBuildPrompt:
    """Test prompt building functionality."""

    def test_build_prompt_includes_all_parameters(self, openai_provider):
        """Test that build_prompt includes all required parameters."""
        with patch('radarr_manager.providers.openai.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2024-09-19 16:30 UTC"

            prompt = openai_provider._build_prompt(limit=5, region="EU")

            assert "film research assistant" in prompt
            assert "web_search" in prompt
            assert "at most 5 movies" in prompt
            assert "region EU" in prompt
            assert "2024-09-19 16:30 UTC" in prompt

    def test_build_prompt_different_parameters(self, openai_provider):
        """Test prompt building with different parameters."""
        with patch('radarr_manager.providers.openai.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2024-12-25 12:00 UTC"

            prompt = openai_provider._build_prompt(limit=10, region="CA")

            assert "at most 10 movies" in prompt
            assert "region CA" in prompt
            assert "2024-12-25 12:00 UTC" in prompt


@pytest.mark.integration
class TestOpenAIProviderIntegration:
    """Integration tests for OpenAI provider that require live API access."""

    @pytest.mark.asyncio
    async def test_real_openai_discovery(self):
        """Test discovery with real OpenAI API if configured."""
        import os

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set, skipping integration test")

        provider = OpenAIProvider(
            api_key=api_key,
            model="gpt-4o-mini",
            region="US",
            cache_ttl_hours=1,
        )

        suggestions = await provider.discover(limit=2)

        # Basic validation of live API response
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 2

        if suggestions:
            suggestion = suggestions[0]
            assert isinstance(suggestion, MovieSuggestion)
            assert suggestion.title
            assert 0.0 <= suggestion.confidence <= 1.0
            assert isinstance(suggestion.sources, list)