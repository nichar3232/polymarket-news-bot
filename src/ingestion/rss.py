"""
Multi-source async RSS ingestion.

Monitors Reuters, AP, BBC, CNN, The Guardian, and domain-specific feeds.
Yields NewsItem events when new articles arrive.
"""
from __future__ import annotations

import asyncio
import calendar
import hashlib
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

import aiohttp
import feedparser
from loguru import logger

from src.ingestion.metrics import ingestion_metrics


RSS_FEEDS: list[tuple[str, str]] = [
    ("reuters_world",     "https://feeds.reuters.com/reuters/worldNews"),
    ("reuters_politics",  "https://feeds.reuters.com/Reuters/PoliticsNews"),
    ("reuters_business",  "https://feeds.reuters.com/reuters/businessNews"),
    ("ap_top_news",       "https://feeds.apnews.com/rss/apf-topnews"),
    ("bbc_world",         "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("bbc_business",      "http://feeds.bbci.co.uk/news/business/rss.xml"),
    ("cnn_top",           "http://rss.cnn.com/rss/edition.rss"),
    ("guardian_world",    "https://www.theguardian.com/world/rss"),
    ("guardian_politics", "https://www.theguardian.com/politics/rss"),
    ("guardian_business", "https://www.theguardian.com/business/rss"),
    ("npr_news",          "https://feeds.npr.org/1001/rss.xml"),
    ("ft_markets",        "https://www.ft.com/rss/home/uk"),
    ("politico",          "https://www.politico.com/rss/politicopicks.xml"),
    ("wsj_world",         "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("nyt_world",         "https://rss.nytimes.com/services/xml/rss/nyt/World.rss"),
]


@dataclass
class NewsItem:
    feed_name: str
    title: str
    summary: str
    url: str
    published: float        # Unix timestamp
    item_id: str = ""       # SHA256 of url

    def __post_init__(self) -> None:
        self.item_id = hashlib.sha256(self.url.encode()).hexdigest()[:16]

    @property
    def full_text(self) -> str:
        return f"{self.title}. {self.summary}"


class RSSMonitor:
    """
    Polls multiple RSS feeds on a configurable interval.
    Deduplicates by URL hash and emits only new articles.
    """

    def __init__(
        self,
        feeds: list[tuple[str, str]] = RSS_FEEDS,
        poll_interval: int = 60,
    ) -> None:
        self._feeds = feeds
        self._poll_interval = poll_interval
        self._seen: set[str] = set()

    async def _fetch_feed(
        self,
        session: aiohttp.ClientSession,
        name: str,
        url: str,
    ) -> list[NewsItem]:
        """Fetch and parse a single RSS feed."""
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "polymarket-news-bot/0.1.0"},
            ) as resp:
                text = await resp.text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"RSS fetch error [{name}]: {e}")
            return []

        try:
            feed = feedparser.parse(text)
        except Exception:
            return []

        items: list[NewsItem] = []
        for entry in feed.entries:
            url_str = entry.get("link", "")
            if not url_str:
                continue

            # Parse published date
            published = time.time()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = float(calendar.timegm(entry.published_parsed))
                except Exception:
                    pass

            items.append(NewsItem(
                feed_name=name,
                title=entry.get("title", "").strip(),
                summary=entry.get("summary", entry.get("description", "")).strip()[:500],
                url=url_str,
                published=published,
            ))

        return items

    async def poll_once(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        """Fetch all feeds, return only new items."""
        t0 = time.time()
        tasks = [
            self._fetch_feed(session, name, url)
            for name, url in self._feeds
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_items: list[NewsItem] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            for item in result:
                if item.item_id not in self._seen:
                    self._seen.add(item.item_id)
                    new_items.append(item)

        # Prevent unbounded growth
        if len(self._seen) > 50_000:
            self._seen = set(list(self._seen)[-25_000:])

        elapsed_ms = (time.time() - t0) * 1000
        ingestion_metrics.source("rss").record_fetch(elapsed_ms, items=len(new_items))

        return new_items

    async def stream(
        self, session: aiohttp.ClientSession | None = None,
    ) -> AsyncGenerator[list[NewsItem], None]:
        """
        Async generator — yields batches of new NewsItems on each poll.

        Args:
            session: Optional externally-managed ClientSession.  When provided
                     the caller owns the session lifecycle (no close on exit).
        Usage:
            async for batch in monitor.stream():
                process(batch)
        """
        owns_session = session is None
        if owns_session:
            session = aiohttp.ClientSession()
        try:
            while True:
                items = await self.poll_once(session)
                if items:
                    logger.info(f"RSS: {len(items)} new articles")
                    yield items
                await asyncio.sleep(self._poll_interval)
        finally:
            if owns_session:
                await session.close()


def keyword_relevance_score(item: NewsItem, keywords: list[str]) -> float:
    """
    Score how relevant a news article is to a set of market keywords.
    Returns 0.0–1.0. Weights title hits more heavily.
    """
    text_lower = item.full_text.lower()
    title_lower = item.title.lower()
    score = 0.0

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in title_lower:
            score += 0.4
        elif kw_lower in text_lower:
            score += 0.15

    return min(score, 1.0)
