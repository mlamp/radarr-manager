"""Factory for building scraper providers."""

from __future__ import annotations

from radarr_manager.scrapers.base import ScraperError, ScraperProvider


# Default API URLs for each provider
DEFAULT_URLS = {
    "crawl4ai": "http://localhost:11235",
    "firecrawl": "http://localhost:3002",
}


def build_scraper(
    *,
    provider: str = "crawl4ai",
    api_url: str | None = None,
    api_key: str | None = None,
    debug: bool = False,
) -> ScraperProvider:
    """
    Build a scraper provider instance.

    Args:
        provider: The scraper provider to use ("crawl4ai" or "firecrawl")
        api_url: Base URL for the scraper API (defaults based on provider)
        api_key: Optional API key for authentication
        debug: Enable debug logging

    Returns:
        Configured ScraperProvider instance

    Raises:
        ScraperError: If the provider is not supported
    """
    provider = provider.lower()

    if provider == "crawl4ai":
        from radarr_manager.scrapers.crawl4ai import Crawl4AIScraper

        return Crawl4AIScraper(
            api_url=api_url or DEFAULT_URLS["crawl4ai"],
            api_key=api_key,
            debug=debug,
        )

    if provider == "firecrawl":
        from radarr_manager.scrapers.firecrawl import FirecrawlScraper

        return FirecrawlScraper(
            api_url=api_url or DEFAULT_URLS["firecrawl"],
            api_key=api_key,
            debug=debug,
        )

    raise ScraperError(
        f"Unsupported scraper provider: {provider}. "
        "Valid options: crawl4ai, firecrawl"
    )


__all__ = ["build_scraper"]
