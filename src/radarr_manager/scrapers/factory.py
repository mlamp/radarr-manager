"""Factory for building scraper providers."""

from __future__ import annotations

from radarr_manager.scrapers.base import ScraperError, ScraperProvider
from radarr_manager.scrapers.firecrawl import FirecrawlScraper


def build_scraper(
    *,
    provider: str = "firecrawl",
    api_url: str | None = None,
    api_key: str | None = None,
    debug: bool = False,
) -> ScraperProvider:
    """
    Build a scraper provider instance.

    Args:
        provider: The scraper provider to use ("firecrawl")
        api_url: Base URL for the scraper API
        api_key: Optional API key for authentication
        debug: Enable debug logging

    Returns:
        Configured ScraperProvider instance

    Raises:
        ScraperError: If the provider is not supported
    """
    if provider == "firecrawl":
        return FirecrawlScraper(
            api_url=api_url or "http://localhost:3002",
            api_key=api_key,
            debug=debug,
        )
    else:
        raise ScraperError(f"Unsupported scraper provider: {provider}")


__all__ = ["build_scraper"]
