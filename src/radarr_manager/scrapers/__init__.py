"""Web scraping providers for reliable movie discovery."""

from radarr_manager.scrapers.base import ScrapedMovie, ScraperProvider
from radarr_manager.scrapers.factory import build_scraper

__all__ = ["ScraperProvider", "ScrapedMovie", "build_scraper"]
