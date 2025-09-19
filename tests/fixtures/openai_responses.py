"""Fixture data for OpenAI API responses."""

from typing import Any

VALID_JSON_RESPONSE = {
    "suggestions": [
        {
            "title": "Dune: Part Two",
            "release_date": "2024-02-29",
            "overview": "Epic sci-fi sequel following Paul Atreides",
            "franchise": "Dune",
            "confidence": 0.95,
            "sources": ["variety.com", "boxofficemojo.com"],
            "metadata": {
                "budget": "190M",
                "genre": "Science Fiction"
            }
        },
        {
            "title": "Deadpool & Wolverine",
            "release_date": "2024-07-26",
            "overview": "MCU crossover superhero action comedy",
            "franchise": "Marvel",
            "confidence": 0.88,
            "sources": ["hollywoodreporter.com", "deadline.com"],
            "metadata": {
                "rating": "R",
                "runtime": "127 min"
            }
        }
    ]
}

EMPTY_SUGGESTIONS_RESPONSE = {
    "suggestions": []
}

MALFORMED_JSON_RESPONSE = """
{
    "suggestions": [
        {
            "title": "Movie Title"
            // Missing comma and other fields
        }
    ]
"""

RESPONSE_WITH_INVALID_DATES = {
    "suggestions": [
        {
            "title": "Bad Date Movie",
            "release_date": "invalid-date",
            "overview": "Movie with invalid date",
            "confidence": 0.5,
            "sources": ["test.com"]
        }
    ]
}

RESPONSE_WITH_MISSING_FIELDS = {
    "suggestions": [
        {
            "title": "Minimal Movie",
            # Missing optional fields
        }
    ]
}

# Mock OpenAI Response structures
class MockOpenAIContent:
    """Mock OpenAI response content."""

    def __init__(self, text: str):
        self.text = text


class MockOpenAIOutputItem:
    """Mock OpenAI response output item."""

    def __init__(self, content_text: str):
        self.content = [MockOpenAIContent(content_text)]


class MockOpenAIResponse:
    """Mock OpenAI response object."""

    def __init__(self, output_text: str | None = None, output_content: str | None = None):
        if output_text:
            self.output_text = output_text
        elif output_content:
            self.output = [MockOpenAIOutputItem(output_content)]
        else:
            self.output = []


# Valid response variations for testing JSON extraction
VALID_JSON_RESPONSE_TEXT = """
{
    "suggestions": [
        {
            "title": "Test Movie",
            "release_date": "2024-06-15",
            "overview": "A test movie",
            "confidence": 0.8,
            "sources": ["test.com"]
        }
    ]
}
"""

JSON_WITH_MARKDOWN_WRAPPER = """
```json
{
    "suggestions": [
        {
            "title": "Wrapped Movie",
            "release_date": "2024-07-01",
            "overview": "Movie wrapped in markdown",
            "confidence": 0.75,
            "sources": ["wrapped.com"]
        }
    ]
}
```
"""

JSON_WITH_EXTRA_TEXT = """
Here are the movie suggestions based on current box office trends:

{
    "suggestions": [
        {
            "title": "Extracted Movie",
            "release_date": "2024-08-15",
            "overview": "Movie extracted from text",
            "confidence": 0.85,
            "sources": ["extracted.com"]
        }
    ]
}

These movies represent the top trending releases.
"""

NON_JSON_RESPONSE = """
I cannot provide movie suggestions at this time.
Please try again later.
"""