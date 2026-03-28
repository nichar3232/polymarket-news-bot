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
from datetime import datetime
from dataclasses import dataclass, field
from typing import AsyncGenerator

import aiohttp
import feedparser
from loguru import logger

from src.ingestion.metrics import ingestion_metrics


RSS_FEEDS: list[tuple[str, str]] = [
    # Tier-1 global news
    ("bbc",               "https://feeds.bbci.co.uk/news/rss.xml"),
    ("aljazeera",         "https://www.aljazeera.com/xml/rss/all.xml"),
    ("abc_news",          "https://feeds.abcnews.com/abcnews/topstories"),
    ("pbs_newshour",      "https://www.pbs.org/newshour/feeds/rss/headlines"),
    ("axios",             "https://api.axios.com/feed/"),
    ("guardian_world",    "https://www.theguardian.com/world/rss"),
    ("guardian_politics", "https://www.theguardian.com/politics/rss"),
    ("guardian_business", "https://www.theguardian.com/business/rss"),
    ("guardian_tech",     "https://www.theguardian.com/technology/rss"),
    ("npr_news",          "https://feeds.npr.org/1001/rss.xml"),
    ("npr_politics",      "https://feeds.npr.org/1014/rss.xml"),
    # Politics
    ("politico",          "https://www.politico.com/rss/politicopicks.xml"),
    ("the_hill",          "https://thehill.com/rss/syndicator/19110/"),
    # Finance / markets
    ("wsj_world",         "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("ft",                "https://www.ft.com/rss/home"),
    ("bloomberg",         "https://feeds.bloomberg.com/markets/news.rss"),
    ("cnbc",              "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("marketwatch",       "https://feeds.marketwatch.com/marketwatch/topstories/"),
    # Tech
    ("techcrunch",        "https://techcrunch.com/feed/"),
]

NEWSAPI_TOP_HEADLINES = "https://newsapi.org/v2/top-headlines"


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
        newsapi_key: str = "",
        newsapi_page_size: int = 40,
    ) -> None:
        self._feeds = feeds
        self._poll_interval = poll_interval
        self._newsapi_key = newsapi_key
        self._newsapi_page_size = newsapi_page_size
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

    async def _fetch_newsapi(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        """Fetch supplemental headlines from NewsAPI when a key is provided."""
        if not self._newsapi_key:
            return []

        t0 = time.time()
        try:
            async with session.get(
                NEWSAPI_TOP_HEADLINES,
                params={
                    "language": "en",
                    "pageSize": str(self._newsapi_page_size),
                },
                headers={
                    "X-Api-Key": self._newsapi_key,
                    "User-Agent": "polymarket-news-bot/0.1.0",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    ingestion_metrics.source("newsapi").record_fetch((time.time() - t0) * 1000)
                    return []
                payload = await resp.json()
        except Exception as e:
            logger.debug(f"NewsAPI fetch error: {e}")
            ingestion_metrics.source("newsapi").record_fetch((time.time() - t0) * 1000)
            return []

        items: list[NewsItem] = []
        for article in payload.get("articles", []):
            url_str = (article.get("url") or "").strip()
            title = (article.get("title") or "").strip()
            if not url_str or not title:
                continue

            published = time.time()
            published_at = article.get("publishedAt")
            if isinstance(published_at, str) and published_at:
                try:
                    published = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    pass

            source_name = (
                article.get("source", {}).get("name")
                if isinstance(article.get("source"), dict)
                else None
            ) or "newsapi"

            summary = (
                (article.get("description") or article.get("content") or "")
                .strip()
                .replace("\r", " ")
                .replace("\n", " ")
            )[:500]

            items.append(NewsItem(
                feed_name=f"newsapi:{source_name[:24]}",
                title=title,
                summary=summary,
                url=url_str,
                published=published,
            ))

        ingestion_metrics.source("newsapi").record_fetch(
            (time.time() - t0) * 1000,
            items=len(items),
        )
        return items

    async def poll_once(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        """Fetch all feeds, return only new items."""
        t0 = time.time()
        tasks = [
            self._fetch_feed(session, name, url)
            for name, url in self._feeds
        ]
        if self._newsapi_key:
            tasks.append(self._fetch_newsapi(session))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_items: list[NewsItem] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            for item in result:
                if item.item_id not in self._seen:
                    self._seen.add(item.item_id)
                    new_items.append(item)

        # Prevent unbounded growth — sets are unordered, so slice-on-list is arbitrary (Bug 11 fix)
        # Simply drop half the entries when limit hit; dedup correctness doesn't require ordering
        if len(self._seen) > 50_000:
            items_list = list(self._seen)
            self._seen = set(items_list[len(items_list) // 2:])

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
