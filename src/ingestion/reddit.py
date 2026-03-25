"""
Reddit PRAW async wrapper.

Monitors r/PredictionMarkets, r/worldnews, r/politics, r/Economics
for relevant posts and comments.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

import aiohttp
from loguru import logger


SUBREDDITS = [
    "PredictionMarkets",
    "worldnews",
    "politics",
    "Economics",
    "geopolitics",
    "CredibleDefense",
]

REDDIT_OAUTH_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_BASE = "https://oauth.reddit.com"
REDDIT_PUBLIC_BASE = "https://www.reddit.com"


@dataclass
class RedditPost:
    subreddit: str
    title: str
    selftext: str
    url: str
    score: int
    num_comments: int
    created_utc: float
    post_id: str
    author: str
    flair: str = ""

    @property
    def full_text(self) -> str:
        return f"{self.title}. {self.selftext}"


class RedditClient:
    """
    Lightweight Reddit client using the public JSON API.
    Works without OAuth for read-only access (rate limited but sufficient).
    Falls back to PRAW credentials if provided.
    """

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        user_agent: str = "polymarket-news-bot/0.1.0",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_agent = user_agent
        self._access_token: str = ""
        self._token_expires: float = 0.0
        self._seen_ids: set[str] = set()

    async def _get_token(self, session: aiohttp.ClientSession) -> str:
        """Obtain OAuth token via client credentials flow."""
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        try:
            async with session.post(
                REDDIT_OAUTH_URL,
                auth=aiohttp.BasicAuth(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self._user_agent},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                self._access_token = data["access_token"]
                self._token_expires = time.time() + data.get("expires_in", 3600)
                return self._access_token
        except Exception as e:
            logger.warning(f"Reddit OAuth failed: {e}")
            return ""

    async def _fetch_subreddit_new(
        self,
        session: aiohttp.ClientSession,
        subreddit: str,
        limit: int = 25,
    ) -> list[RedditPost]:
        """Fetch newest posts from a subreddit."""
        # Try public API first (no auth needed, rate limited)
        try:
            async with session.get(
                f"{REDDIT_PUBLIC_BASE}/r/{subreddit}/new.json",
                params={"limit": limit},
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 429:
                    logger.debug(f"Reddit rate limited on r/{subreddit}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.debug(f"Reddit fetch error for r/{subreddit}: {e}")
            return []

        posts: list[RedditPost] = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            posts.append(RedditPost(
                subreddit=subreddit,
                title=d.get("title", ""),
                selftext=d.get("selftext", "")[:1000],
                url=d.get("url", ""),
                score=d.get("score", 0),
                num_comments=d.get("num_comments", 0),
                created_utc=float(d.get("created_utc", time.time())),
                post_id=d.get("id", ""),
                author=d.get("author", ""),
                flair=d.get("link_flair_text", "") or "",
            ))
        return posts

    async def fetch_all_subreddits(
        self,
        session: aiohttp.ClientSession,
        subreddits: list[str] | None = None,
    ) -> list[RedditPost]:
        """Fetch new posts from all monitored subreddits."""
        subs = subreddits or SUBREDDITS
        tasks = [self._fetch_subreddit_new(session, sub) for sub in subs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_posts: list[RedditPost] = []
        for result in results:
            if isinstance(result, list):
                for post in result:
                    if post.post_id and post.post_id not in self._seen_ids:
                        self._seen_ids.add(post.post_id)
                        all_posts.append(post)

        return all_posts

    async def run(
        self,
        callback: Callable,
        poll_interval: int = 300,
    ) -> None:
        """Continuously monitor subreddits and invoke callback with new posts."""
        async with aiohttp.ClientSession() as session:
            while True:
                posts = await self.fetch_all_subreddits(session)
                if posts:
                    logger.info(f"Reddit: {len(posts)} new posts")
                    await callback(posts)
                await asyncio.sleep(poll_interval)


def reddit_sentiment_score(post: RedditPost, keywords: list[str]) -> float:
    """
    Compute a rudimentary sentiment + relevance score for a Reddit post.
    Returns -1.0 (strongly negative) to +1.0 (strongly positive).

    This is intentionally simple — Reddit sentiment is a weak signal.
    The Bayesian engine weights it accordingly.
    """
    text = post.full_text.lower()
    relevant = any(kw.lower() in text for kw in keywords)
    if not relevant:
        return 0.0

    positive_words = {
        "win", "winning", "likely", "bullish", "confirm", "approve",
        "pass", "positive", "strong", "support", "leads", "ahead",
    }
    negative_words = {
        "lose", "losing", "unlikely", "bearish", "reject", "fail",
        "negative", "weak", "oppose", "behind", "collapse", "crisis",
    }

    words = text.split()
    pos = sum(1 for w in words if w in positive_words)
    neg = sum(1 for w in words if w in negative_words)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total
