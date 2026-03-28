"""
Resolution source crawler.

Each Polymarket market specifies a resolution authority (AP, Reuters, BLS, etc.).
We parse resolution criteria and poll those sources directly.
This lets us trade BEFORE Polymarket officially resolves.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import aiohttp
from loguru import logger


@dataclass
class ResolutionSignal:
    source: str
    resolution_criteria: str
    found_evidence: bool
    evidence_text: str
    confidence: float     # 0.0–1.0
    likely_yes: bool | None   # None = cannot determine yet
    likelihood_ratio: float


RESOLUTION_SOURCES: dict[str, str] = {
    "AP": "https://apnews.com/search?q={query}&ss=topStories",
    "Reuters": "https://www.reuters.com/search/news?blob={query}",
    "BLS": "https://www.bls.gov/news.release/",
    "BEA": "https://www.bea.gov/news/releases",
    "FED": "https://www.federalreserve.gov/newsevents/pressreleases.htm",
    "FEC": "https://www.fec.gov/updates/",
    "SCOTUS": "https://www.supremecourt.gov/opinions/opinions.aspx",
    "CDC": "https://www.cdc.gov/media/releases/",
    "FDA": "https://www.fda.gov/news-events/press-announcements",
}


def extract_resolution_keywords(resolution_criteria: str) -> list[str]:
    """
    Parse resolution criteria text to extract key entities and conditions.

    Example:
    "Resolves YES if the Federal Reserve announces a rate cut at the March 2025 FOMC meeting"
    → ["Federal Reserve", "rate cut", "FOMC", "March 2025"]
    """
    # Remove common resolution boilerplate
    text = re.sub(r"resolves\s+(yes|no)\s+if", "", resolution_criteria, flags=re.IGNORECASE)
    text = re.sub(r"this\s+market\s+resolves", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[,;]", " ", text)

    # Extract multi-word proper nouns (caps sequences)
    proper_nouns = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", resolution_criteria)

    # Extract dates
    dates = re.findall(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        resolution_criteria,
    )

    # Extract quoted phrases
    quoted = re.findall(r'"([^"]+)"', resolution_criteria)

    keywords = list(set(proper_nouns + dates + quoted))
    return [k for k in keywords if len(k) > 3][:10]


def detect_resolution_in_text(
    text: str,
    resolution_criteria: str,
    keywords: list[str],
) -> tuple[bool, str, float]:
    """
    Detect if article text contains evidence of resolution.

    Returns: (found_evidence, matched_text, confidence)
    """
    text_lower = text.lower()
    criteria_lower = resolution_criteria.lower()

    # Look for YES-resolving language
    yes_patterns = [
        r"announced",
        r"confirmed",
        r"approved",
        r"signed",
        r"passed",
        r"agreed",
        r"declared",
        r"rate cut",
        r"rate decrease",
        r"lower\s+rates",
    ]

    no_patterns = [
        r"rejected",
        r"failed",
        r"no\s+rate\s+cut",
        r"rate\s+hike",
        r"held\s+rates",
        r"unchanged",
        r"no\s+change",
    ]

    # Check keyword overlap
    kw_matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    if kw_matches < 2:
        return False, "", 0.0

    # Determine direction from patterns
    yes_hits = sum(1 for p in yes_patterns if re.search(p, text_lower))
    no_hits = sum(1 for p in no_patterns if re.search(p, text_lower))

    if yes_hits == 0 and no_hits == 0:
        return False, "", 0.0

    # Grab some surrounding text for evidence
    for kw in keywords[:3]:
        idx = text_lower.find(kw.lower())
        if idx >= 0:
            snippet = text[max(0, idx - 50):idx + 150].strip()
            confidence = min(kw_matches / len(keywords), 1.0) * 0.8
            return True, snippet, confidence

    return False, "", 0.0


class ResolutionMonitor:
    """
    Monitors resolution sources for evidence that a market is about to resolve.
    """

    async def check_resolution(
        self,
        session: aiohttp.ClientSession,
        resolution_criteria: str,
        resolution_source: str,
        market_keywords: list[str],
    ) -> ResolutionSignal:
        """
        Check if a market's resolution condition has been met.
        """
        keywords = extract_resolution_keywords(resolution_criteria)
        all_keywords = list(set(keywords + market_keywords))

        # Try to fetch from RSS feeds of the resolution source
        found_evidence = False
        evidence_text = ""
        confidence = 0.0
        likely_yes: bool | None = None

        # Check common resolution sources via their RSS
        rss_urls = _get_resolution_rss(resolution_source)
        for rss_url in rss_urls:
            text = await _fetch_text(session, rss_url)
            if not text:
                continue

            found, snippet, conf = detect_resolution_in_text(
                text, resolution_criteria, all_keywords
            )
            if found and conf > confidence:
                found_evidence = True
                evidence_text = snippet
                confidence = conf

                # Determine YES/NO
                text_lower = text.lower()
                yes_signals = ["announced", "confirmed", "approved", "rate cut", "signed"]
                no_signals = ["rejected", "failed", "unchanged", "held rates"]
                y = sum(1 for s in yes_signals if s in text_lower)
                n = sum(1 for s in no_signals if s in text_lower)
                if y > n:
                    likely_yes = True
                elif n > y:
                    likely_yes = False

        # Compute LR — exponential scale to match other signals (Bug 5 fix)
        # lr = exp(confidence * 2.0) gives max ≈7.4 at confidence=1.0, capped to [0.25, 4.0]
        # Previous: linear 1 + confidence * 5.0 gave max 6.0 — breaks Bayesian calibration
        if not found_evidence:
            lr = 1.0
        elif likely_yes is True:
            lr = min(4.0, math.exp(confidence * 2.0))   # Strong YES evidence → big update
        elif likely_yes is False:
            lr = max(0.25, math.exp(-confidence * 2.0))
        else:
            lr = 1.0  # Found evidence but couldn't determine direction

        return ResolutionSignal(
            source=resolution_source,
            resolution_criteria=resolution_criteria,
            found_evidence=found_evidence,
            evidence_text=evidence_text,
            confidence=confidence,
            likely_yes=likely_yes,
            likelihood_ratio=lr,
        )


def _get_resolution_rss(source: str) -> list[str]:
    """Get RSS feeds for a resolution source."""
    mapping: dict[str, list[str]] = {
        "Reuters": [
            "https://feeds.reuters.com/reuters/worldNews",
            "https://feeds.reuters.com/Reuters/PoliticsNews",
        ],
        "AP": [
            "https://feeds.apnews.com/rss/apf-topnews",
        ],
        "BLS": [
            "https://www.bls.gov/feed/bls_latest.rss",
        ],
        "FED": [
            "https://www.federalreserve.gov/feeds/press_all.xml",
        ],
        "FDA": [
            "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-announcements/rss.xml",
        ],
    }
    return mapping.get(source, [])


async def _fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "polymarket-news-bot/0.1"},
        ) as resp:
            if resp.status != 200:
                return ""
            return await resp.text(errors="replace")
    except Exception:
        return ""
