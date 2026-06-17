"""Base scraper interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from news_aggregator.models import RawArticle


class BaseScraper(ABC):
    """All scrapers must implement this interface."""

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    async def scrape(self) -> list[RawArticle]:
        """Fetch and return new articles since the last poll."""
        ...
