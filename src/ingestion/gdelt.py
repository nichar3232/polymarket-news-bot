"""
GDELT GKG 2.0 ingestion.

GDELT processes 100+ global news sources every 15 minutes.
We download the batch CSV, parse event codes, tone scores, and match to markets.

No authentication required. Completely free.
"""
from __future__ import annotations

import asyncio
import csv
import io
import math
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import aiohttp
from loguru import logger


GDELT_MASTER_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_GKG_BASE = "http://data.gdeltproject.org/gdeltv2/"


@dataclass
class GDELTEvent:
    """Parsed GDELT GKG event."""
    date: str
    source_url: str
    source_name: str
    themes: list[str]
    locations: list[str]
    persons: list[str]
    organizations: list[str]
    tone: float               # Goldstein scale: -100 (negative) to +100 (positive)
    pos_score: float
    neg_score: float
    polarity: float
    activity_ref_density: float
    word_count: int


async def fetch_latest_gdelt_gkg(session: aiohttp.ClientSession) -> list[GDELTEvent]:
    """Download and parse the latest GDELT GKG 2.0 batch file."""
    try:
        # Step 1: Get last update manifest
        async with session.get(GDELT_MASTER_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            text = await resp.text()

        # Parse manifest — find .gkg.csv.zip line
        gkg_url = None
        for line in text.strip().splitlines():
            parts = line.strip().split(" ")
            if len(parts) >= 3 and ".gkg.csv.zip" in parts[2]:
                gkg_url = parts[2].strip()
                break

        if not gkg_url:
            logger.warning("Could not find GKG URL in GDELT manifest")
            return []

        logger.info(f"Downloading GDELT GKG: {gkg_url}")

        # Step 2: Download and decompress
        async with session.get(gkg_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            resp.raise_for_status()
            raw_bytes = await resp.read()

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            csv_filename = [n for n in zf.namelist() if n.endswith(".csv")][0]
            csv_bytes = zf.read(csv_filename)

        events = _parse_gkg_csv(csv_bytes.decode("utf-8", errors="replace"))
        logger.info(f"Parsed {len(events)} GDELT GKG events")
        return events

    except Exception as e:
        logger.error(f"GDELT fetch failed: {e}")
        return []


def _parse_gkg_csv(csv_text: str) -> list[GDELTEvent]:
    """Parse GDELT GKG 2.0 CSV format."""
    events: list[GDELTEvent] = []
    reader = csv.reader(io.StringIO(csv_text), delimiter="\t")

    for row in reader:
        if len(row) < 27:
            continue
        try:
            # GKG 2.0 columns:
            # 0: GKGRECORDID, 1: DATE, 2: SourceCollectionIdentifier,
            # 3: SourceCommonName, 4: DocumentIdentifier (URL),
            # 7: V2Themes, 9: V2Locations, 11: V2Persons, 13: V2Organizations,
            # 15: V2Tone (tone,pos,neg,polarity,actrefdensity,...)
            date_str = row[1]
            source_name = row[3]
            source_url = row[4]

            # Themes: semicolon-separated
            themes_raw = row[7] if len(row) > 7 else ""
            themes = [t.split(",")[0] for t in themes_raw.split(";") if t]

            # Locations: semicolon-separated, each is # delimited
            locs_raw = row[9] if len(row) > 9 else ""
            locations = [loc.split("#")[1] for loc in locs_raw.split(";")
                         if loc and len(loc.split("#")) > 1]

            # Persons
            persons_raw = row[11] if len(row) > 11 else ""
            persons = [p.split(",")[0] for p in persons_raw.split(";") if p]

            # Organizations
            orgs_raw = row[13] if len(row) > 13 else ""
            organizations = [o.split(",")[0] for o in orgs_raw.split(";") if o]

            # Tone: comma-separated floats
            tone_raw = row[15] if len(row) > 15 else ""
            tone_parts = tone_raw.split(",")
            tone = float(tone_parts[0]) if tone_parts else 0.0
            pos_score = float(tone_parts[1]) if len(tone_parts) > 1 else 0.0
            neg_score = float(tone_parts[2]) if len(tone_parts) > 2 else 0.0
            polarity = float(tone_parts[3]) if len(tone_parts) > 3 else 0.0
            act_ref_density = float(tone_parts[4]) if len(tone_parts) > 4 else 0.0
            word_count = int(tone_parts[6]) if len(tone_parts) > 6 else 0

            events.append(GDELTEvent(
                date=date_str,
                source_url=source_url,
                source_name=source_name,
                themes=themes[:20],        # cap to avoid huge lists
                locations=locations[:10],
                persons=persons[:10],
                organizations=organizations[:10],
                tone=tone,
                pos_score=pos_score,
                neg_score=neg_score,
                polarity=polarity,
                activity_ref_density=act_ref_density,
                word_count=word_count,
            ))
        except (ValueError, IndexError):
            continue

    return events


def score_gdelt_relevance(event: GDELTEvent, keywords: list[str]) -> float:
    """
    Score how relevant a GDELT event is to a market.
    Returns 0.0-1.0 relevance score.
    """
    keywords_lower = [k.lower() for k in keywords]
    score = 0.0

    # Check persons
    for person in event.persons:
        for kw in keywords_lower:
            if kw in person.lower():
                score += 0.3
                break

    # Check organizations
    for org in event.organizations:
        for kw in keywords_lower:
            if kw in org.lower():
                score += 0.25
                break

    # Check locations
    for loc in event.locations:
        for kw in keywords_lower:
            if kw in loc.lower():
                score += 0.2
                break

    # Check themes
    for theme in event.themes:
        for kw in keywords_lower:
            if kw in theme.lower():
                score += 0.15
                break

    # Check source URL as a last resort
    for kw in keywords_lower:
        if kw in event.source_url.lower():
            score += 0.1

    return min(score, 1.0)


def gdelt_tone_to_likelihood_ratio(
    tone: float,
    relevance: float,
    baseline_tone: float = 0.0,
) -> float:
    """
    Convert GDELT tone score to a Bayesian likelihood ratio.

    Positive tone → L > 1 (evidence for YES)
    Negative tone → L < 1 (evidence for NO)

    Scale: ±20 tone is meaningful, ±50 is extreme.
    """
    if relevance < 0.1:
        return 1.0  # irrelevant — no update

    tone_delta = tone - baseline_tone
    # Map [-50, +50] to [-1.5, +1.5] for LR exponent
    normalized = max(-1.5, min(1.5, tone_delta / 33.3))
    # LR = e^(normalized * relevance * 2)
    lr = math.exp(normalized * relevance * 2)
    return lr


class GDELTMonitor:
    """Polls GDELT every 15 minutes and emits relevant events."""

    def __init__(self, keywords_by_market: dict[str, list[str]]) -> None:
        self._keywords = keywords_by_market
        self._seen_urls: set[str] = set()

    async def run(self, callback: Callable) -> None:
        """Continuously fetch GDELT and invoke callback with new relevant events."""
        async with aiohttp.ClientSession() as session:
            while True:
                events = await fetch_latest_gdelt_gkg(session)
                for event in events:
                    if event.source_url in self._seen_urls:
                        continue
                    self._seen_urls.add(event.source_url)

                    for market_id, keywords in self._keywords.items():
                        relevance = score_gdelt_relevance(event, keywords)
                        if relevance > 0.1:
                            await callback(market_id, event, relevance)

                # Clean up old seen URLs to prevent unbounded memory growth
                # Bug 11 fix: sets are unordered so list(set)[-N:] is arbitrary — just trim by half
                if len(self._seen_urls) > 10_000:
                    urls_list = list(self._seen_urls)
                    self._seen_urls = set(urls_list[len(urls_list) // 2:])

                logger.info("GDELT cycle complete. Sleeping 15 minutes.")
                await asyncio.sleep(15 * 60)
