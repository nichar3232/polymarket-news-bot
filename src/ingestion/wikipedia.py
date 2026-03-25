"""
Wikipedia Recent Changes edit-velocity signal.

Wikipedia edits spike MINUTES before news goes mainstream.
Free API, zero latency, no authentication required.

We monitor edit frequency for market-relevant pages and compute
a velocity score that feeds into the Bayesian engine.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

import aiohttp
from loguru import logger


WIKIPEDIA_RECENT_CHANGES = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_ARTICLE_CHANGES = "https://en.wikipedia.org/w/api.php"


@dataclass
class WikiEdit:
    page_title: str
    timestamp: float
    user: str
    edit_size: int    # bytes changed (positive = addition)
    comment: str
    is_bot: bool = False


@dataclass
class WikiVelocitySignal:
    page_title: str
    edits_last_5min: int
    edits_last_15min: int
    edits_last_60min: int
    velocity_score: float       # 0.0 = baseline, 1.0+ = extreme spike
    is_spiking: bool
    net_size_change: int        # bytes added in window


class WikipediaEditMonitor:
    """
    Monitors Wikipedia Recent Changes for edit spikes on market-relevant pages.

    How it works:
    - Fetches Recent Changes API every 2 minutes
    - Tracks edit frequency per page in a rolling time window
    - Computes velocity score: current_rate / baseline_rate
    - Emits WikiVelocitySignal when velocity exceeds threshold
    """

    SPIKE_THRESHOLD = 3.0    # 3x baseline = spike
    BASELINE_WINDOW = 3600   # 1 hour for baseline
    SIGNAL_WINDOW = 300      # 5-minute spike window

    def __init__(self, pages_of_interest: list[str] | None = None) -> None:
        # {page_title: deque of (timestamp, edit_size)}
        self._edit_history: dict[str, deque[tuple[float, int]]] = {}
        self._pages_of_interest = set(pages_of_interest or [])

    def register_page(self, page_title: str) -> None:
        self._pages_of_interest.add(page_title)
        if page_title not in self._edit_history:
            self._edit_history[page_title] = deque(maxlen=500)

    def register_keywords(self, keywords: list[str]) -> None:
        """Register pages based on keyword list (simplified matching)."""
        for kw in keywords:
            # Capitalize to match Wikipedia titles
            self.register_page(kw.title().replace(" ", "_"))
            self.register_page(kw.title())

    async def _fetch_recent_changes(
        self,
        session: aiohttp.ClientSession,
        minutes_back: int = 5,
    ) -> list[WikiEdit]:
        """Fetch Wikipedia recent changes via API."""
        since = (datetime.now(timezone.utc) - timedelta(minutes=minutes_back)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        params = {
            "action": "query",
            "list": "recentchanges",
            "rcstart": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rcend": since,
            "rcprop": "title|timestamp|user|comment|sizes|flags",
            "rctype": "edit|new",
            "rclimit": "500",
            "format": "json",
        }

        try:
            async with session.get(
                WIKIPEDIA_RECENT_CHANGES,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"User-Agent": "polymarket-news-bot/0.1 (research)"},
            ) as resp:
                data = await resp.json()

            edits: list[WikiEdit] = []
            for rc in data.get("query", {}).get("recentchanges", []):
                ts_str = rc.get("timestamp", "")
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").timestamp()
                except ValueError:
                    ts = time.time()

                old_size = rc.get("oldlen", 0)
                new_size = rc.get("newlen", 0)
                edits.append(WikiEdit(
                    page_title=rc.get("title", ""),
                    timestamp=ts,
                    user=rc.get("user", ""),
                    edit_size=new_size - old_size,
                    comment=rc.get("comment", ""),
                    is_bot="bot" in rc.get("flags", []),
                ))
            return edits
        except Exception as e:
            logger.debug(f"Wikipedia RC fetch error: {e}")
            return []

    async def _fetch_page_edits(
        self,
        session: aiohttp.ClientSession,
        page_title: str,
        limit: int = 50,
    ) -> list[WikiEdit]:
        """Fetch recent edits for a specific page."""
        params = {
            "action": "query",
            "prop": "revisions",
            "titles": page_title,
            "rvprop": "timestamp|user|comment|size",
            "rvlimit": str(limit),
            "format": "json",
        }
        try:
            async with session.get(
                WIKIPEDIA_ARTICLE_CHANGES,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"User-Agent": "polymarket-news-bot/0.1 (research)"},
            ) as resp:
                data = await resp.json()

            edits: list[WikiEdit] = []
            pages = data.get("query", {}).get("pages", {})
            for page_data in pages.values():
                for rev in page_data.get("revisions", []):
                    ts_str = rev.get("timestamp", "")
                    try:
                        ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").timestamp()
                    except ValueError:
                        ts = time.time()

                    edits.append(WikiEdit(
                        page_title=page_title,
                        timestamp=ts,
                        user=rev.get("user", ""),
                        edit_size=rev.get("size", 0),
                        comment=rev.get("comment", ""),
                        is_bot=False,
                    ))
            return edits
        except Exception as e:
            logger.debug(f"Wikipedia page fetch error for '{page_title}': {e}")
            return []

    def _record_edits(self, edits: list[WikiEdit]) -> None:
        for edit in edits:
            if edit.is_bot:
                continue
            page = edit.page_title
            if page not in self._edit_history:
                self._edit_history[page] = deque(maxlen=500)
            self._edit_history[page].append((edit.timestamp, edit.edit_size))

    def compute_velocity(self, page_title: str) -> WikiVelocitySignal:
        """Compute edit velocity signal for a page."""
        history = self._edit_history.get(page_title, deque())
        now = time.time()

        edits_5m = [(ts, sz) for ts, sz in history if now - ts <= 300]
        edits_15m = [(ts, sz) for ts, sz in history if now - ts <= 900]
        edits_60m = [(ts, sz) for ts, sz in history if now - ts <= 3600]

        count_5m = len(edits_5m)
        count_15m = len(edits_15m)
        count_60m = len(edits_60m)

        # Baseline: average 5-min rate over last hour
        baseline_rate = count_60m / 12.0 if count_60m else 0.1
        current_rate = count_5m

        velocity_score = current_rate / baseline_rate if baseline_rate > 0 else 0.0
        is_spiking = velocity_score >= self.SPIKE_THRESHOLD and count_5m >= 3

        net_size = sum(sz for _, sz in edits_5m)

        return WikiVelocitySignal(
            page_title=page_title,
            edits_last_5min=count_5m,
            edits_last_15min=count_15m,
            edits_last_60min=count_60m,
            velocity_score=velocity_score,
            is_spiking=is_spiking,
            net_size_change=net_size,
        )

    def velocity_to_likelihood_ratio(self, signal: WikiVelocitySignal) -> float:
        """
        Convert velocity signal to Bayesian likelihood ratio.

        A spike means something is happening — but doesn't tell us direction.
        We combine with tone from other sources (RSS, GDELT) for direction.
        Here we output a value > 1 if spiking (boosts our confidence in any
        strong directional signal we have), or 1.0 if quiet.
        """
        if not signal.is_spiking:
            return 1.0
        # Cap at 1.5 — spike alone is uncertain, directional signal needed
        return min(1.0 + (signal.velocity_score - self.SPIKE_THRESHOLD) * 0.1, 1.5)

    async def run(
        self,
        callback: Callable,
        poll_interval: int = 120,
    ) -> None:
        """
        Continuously monitor Wikipedia edits.
        Calls callback(page_title, signal) when velocity threshold exceeded.
        """
        async with aiohttp.ClientSession() as session:
            # Initial load for tracked pages
            for page in list(self._pages_of_interest):
                edits = await self._fetch_page_edits(session, page, limit=100)
                self._record_edits(edits)
            logger.info(f"Wikipedia monitor initialized, tracking {len(self._pages_of_interest)} pages")

            while True:
                # Fetch global recent changes
                global_edits = await self._fetch_recent_changes(session, minutes_back=3)
                self._record_edits(global_edits)

                # Targeted page fetches for our markets
                for page in list(self._pages_of_interest):
                    edits = await self._fetch_page_edits(session, page, limit=20)
                    self._record_edits(edits)

                    signal = self.compute_velocity(page)
                    if signal.is_spiking:
                        logger.info(
                            f"Wikipedia spike: '{page}' — {signal.edits_last_5min} edits/5min "
                            f"(velocity={signal.velocity_score:.1f}x)"
                        )
                        await callback(page, signal)

                await asyncio.sleep(poll_interval)
