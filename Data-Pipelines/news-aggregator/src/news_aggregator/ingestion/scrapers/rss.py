"""RSS feed scraper — polls feeds every N seconds and returns new articles."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from news_aggregator.config import get_settings
from news_aggregator.ingestion.scrapers.base import BaseScraper
from news_aggregator.logging import get_logger
from news_aggregator.models import RawArticle

settings = get_settings()
logger = get_logger(__name__)

SAMPLE_FEEDS: list[dict[str, str]] = [
    {"url": "https://feeds.bbci.co.uk/news/rss.xml", "source": "BBC News"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "source": "NYT"},
    {"url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "source": "WSJ"},
    {"url": "https://www.theguardian.com/world/rss", "source": "The Guardian"},
    {"url": "https://feeds.reuters.com/reuters/topNews", "source": "Reuters"},
]


def _parse_date(entry: feedparser.FeedParserDict) -> datetime:
    for attr in ("published", "updated"):
        val = entry.get(attr)
        if val:
            try:
                return parsedate_to_datetime(val).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _extract_body(entry: feedparser.FeedParserDict) -> str:
    for key in ("content", "summary"):
        val = entry.get(key)
        if isinstance(val, list) and val:
            val = val[0].get("value", "")
        if val:
            soup = BeautifulSoup(str(val), "lxml")
            return soup.get_text(separator=" ", strip=True)[:5000]
    return ""


class RSSFeedScraper(BaseScraper):
    """Scraper for a single RSS feed URL."""

    def __init__(self, feed_url: str, source: str) -> None:
        self._url = feed_url
        self._source = source
        self._seen_urls: set[str] = set()

    @property
    def source_name(self) -> str:
        return self._source

    async def scrape(self) -> list[RawArticle]:
        timeout = aiohttp.ClientTimeout(total=settings.scraper_request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._url) as response:
                    content = await response.read()
        except Exception:
            logger.exception("rss_fetch_failed", url=self._url, source=self._source)
            return []

        feed = feedparser.parse(content)
        articles = []
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url or url in self._seen_urls:
                continue
            self._seen_urls.add(url)

            body = _extract_body(entry)
            if not body:
                continue

            articles.append(
                RawArticle(
                    url=url,
                    source=self._source,
                    title=entry.get("title", ""),
                    body=body,
                    published_at=_parse_date(entry),
                    raw_tags=[t.get("term", "") for t in entry.get("tags", [])],
                )
            )

        logger.info("rss_scraped", source=self._source, new_articles=len(articles))
        return articles
