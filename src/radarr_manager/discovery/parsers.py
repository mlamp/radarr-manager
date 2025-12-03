"""Parser registry for extracting movie titles from scraped content."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from radarr_manager.discovery.validation import clean_title, is_valid_title


@dataclass
class ParsedMovie:
    """A movie extracted from scraped content."""

    title: str
    source: str
    year: int | None = None
    url: str | None = None
    rank: int | None = None
    extra: dict = field(default_factory=dict)


class ContentParser(ABC):
    """Base class for content parsers."""

    name: ClassVar[str] = "base"

    @abstractmethod
    def parse(self, content: str, source_url: str) -> list[ParsedMovie]:
        """Parse content and extract movies."""
        pass

    def _clean_title(self, title: str) -> str:
        """Clean up a movie title. Uses shared validation module."""
        return clean_title(title)

    def _is_valid_title(self, title: str) -> bool:
        """Check if a string looks like a valid movie title. Uses shared validation module."""
        return is_valid_title(title)


class RTTheatersParser(ContentParser):
    """Parser for Rotten Tomatoes movies in theaters page."""

    name: ClassVar[str] = "rt_theaters"

    def parse(self, content: str, source_url: str) -> list[ParsedMovie]:
        movies: list[ParsedMovie] = []
        seen_titles: set[str] = set()

        # Pattern 1: Movie links with ratings and dates
        movie_link_pattern = re.compile(
            r"\[\s*(?:\d+%\s*)?(?:\d+%\s*)?"
            r"([A-Z][^[\]]{2,80}?)"
            r"\s+(?:Opened?|Opens)\s+"
            r"[A-Z][a-z]{2}\s+\d{1,2},\s+(\d{4})"
            r"\s*\]\s*\(https?://www\.rottentomatoes\.com/m/",
            re.IGNORECASE,
        )

        for match in movie_link_pattern.finditer(content):
            title = self._clean_title(match.group(1).strip())
            year = int(match.group(2))

            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(ParsedMovie(title=title, year=year, source=self.name, url=source_url))

        # Pattern 2: Certified fresh picks
        cert_fresh_pattern = re.compile(
            r"\[\s*\d+%\s+"
            r"([A-Z][^[\]]{2,60}?)"
            r"\s+Link to\s+"
            r"[^[\]]+\s*\]"
            r"\s*\(https?://www\.rottentomatoes\.com/m/",
        )

        for match in cert_fresh_pattern.finditer(content):
            title = self._clean_title(match.group(1).strip())
            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(ParsedMovie(title=title, source=self.name, url=source_url))

        # Pattern 3: Watchlist format
        watchlist_pattern = re.compile(
            r"\[\s*(?:\d+%\s*)?"
            r"([A-Z][^[\]]{2,60}?)"
            r"\s+(?:Opened?|Opens)\s+"
            r"[A-Z][a-z]{2}\s+\d{1,2},\s+(\d{4})"
            r"\s*\]\s*\([^)]+\)\s*Watchlist",
            re.IGNORECASE,
        )

        for match in watchlist_pattern.finditer(content):
            title = self._clean_title(match.group(1).strip())
            year = int(match.group(2))
            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(ParsedMovie(title=title, year=year, source=self.name, url=source_url))

        return movies


class RTHomeParser(ContentParser):
    """Parser for Rotten Tomatoes movies at home page."""

    name: ClassVar[str] = "rt_home"

    def parse(self, content: str, source_url: str) -> list[ParsedMovie]:
        # Reuse RT theaters parser logic (same format)
        parser = RTTheatersParser()
        movies = parser.parse(content, source_url)
        # Update source name
        for movie in movies:
            movie.source = self.name
        return movies


class IMDBMeterParser(ContentParser):
    """Parser for IMDB moviemeter chart page."""

    name: ClassVar[str] = "imdb_meter"

    def parse(self, content: str, source_url: str) -> list[ParsedMovie]:
        movies: list[ParsedMovie] = []
        seen_titles: set[str] = set()

        # Primary pattern: Markdown headers with IMDB links (chart page)
        # Format: ### [Title](https://www.imdb.com/title/ttXXX/?ref_=chtmvm_t_N)
        chart_pattern = re.compile(
            r"###\s*\[([^\]]{2,80})\]"
            r"\(https?://www\.imdb\.com/title/tt\d+/\?ref_=chtmvm_t_(\d+)\)",
        )

        for match in chart_pattern.finditer(content):
            title = self._clean_title(match.group(1).strip())
            rank = int(match.group(2))

            if rank <= 100 and self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(
                    ParsedMovie(
                        title=title,
                        source=self.name,
                        url=source_url,
                        rank=rank,
                    )
                )

        # Search page pattern: ### [N. Title](url)
        search_pattern = re.compile(
            r"###\s*\[(\d+)\.\s*([^\]]{2,80})\]" r"\(https?://www\.imdb\.com/title/tt\d+",
        )

        for match in search_pattern.finditer(content):
            rank = int(match.group(1))
            title = self._clean_title(match.group(2).strip())

            if rank <= 100 and self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(
                    ParsedMovie(
                        title=title,
                        source=self.name,
                        url=source_url,
                        rank=rank,
                    )
                )

        # Fallback: Simple markdown links
        if not movies:
            link_pattern = re.compile(r"\[([^\]]{3,80})\]\(https?://www\.imdb\.com/title/tt\d+")
            for match in link_pattern.finditer(content):
                title = self._clean_title(match.group(1).strip())
                if self._is_valid_title(title) and title.lower() not in seen_titles:
                    seen_titles.add(title.lower())
                    movies.append(ParsedMovie(title=title, source=self.name, url=source_url))

        return movies


class GenericParser(ContentParser):
    """Generic parser for unknown page formats."""

    name: ClassVar[str] = "generic"

    def parse(self, content: str, source_url: str) -> list[ParsedMovie]:
        movies: list[ParsedMovie] = []
        seen_titles: set[str] = set()

        # Look for common title (year) patterns
        for match in re.finditer(r"([A-Z][^(\n\[\]]{2,55}?)\s*\((\d{4})\)", content):
            title = self._clean_title(match.group(1).strip())
            year = int(match.group(2))

            if self._is_valid_title(title) and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                movies.append(ParsedMovie(title=title, year=year, source=self.name, url=source_url))

        return movies


# Parser registry
PARSER_REGISTRY: dict[str, type[ContentParser]] = {
    "rt_theaters": RTTheatersParser,
    "rt_home": RTHomeParser,
    "imdb_meter": IMDBMeterParser,
    "generic": GenericParser,
}


def get_parser(name: str) -> ContentParser:
    """Get a parser instance by name."""
    parser_class = PARSER_REGISTRY.get(name)
    if parser_class is None:
        # Fall back to generic parser
        return GenericParser()
    return parser_class()


def register_parser(name: str, parser_class: type[ContentParser]) -> None:
    """Register a custom parser."""
    PARSER_REGISTRY[name] = parser_class


__all__ = [
    "ParsedMovie",
    "ContentParser",
    "RTTheatersParser",
    "RTHomeParser",
    "IMDBMeterParser",
    "GenericParser",
    "get_parser",
    "register_parser",
    "PARSER_REGISTRY",
]
