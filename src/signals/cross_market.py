"""
Cross-market arbitrage engine.

Compares Polymarket prices against Kalshi, Metaculus, and Manifold.
When multiple independent platforms agree against Polymarket, that's real alpha.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import aiohttp
from loguru import logger


KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"
METACULUS_BASE = "https://www.metaculus.com/api2"
MANIFOLD_BASE = "https://api.manifold.markets/v0"


@dataclass
class CrossMarketSignal:
    polymarket_price: float
    kalshi_price: float | None
    metaculus_prob: float | None
    manifold_prob: float | None
    disagreement_magnitude: float   # 0.0–1.0
    consensus_direction: float      # +1 = alternatives say YES > PM, -1 = NO > PM, 0 = mixed
    n_sources_agree: int            # how many alternative sources agree
    likelihood_ratio: float
    notes: str = ""


class CrossMarketAnalyzer:
    """
    Fetches prices from Kalshi, Metaculus, and Manifold for the same event.
    Computes disagreement signal and generates Bayesian likelihood ratio.
    """

    POLYMARKET_FEE = 0.02
    MIN_DIVERGENCE = 0.08

    async def fetch_kalshi_markets(
        self,
        session: aiohttp.ClientSession,
        search_term: str,
    ) -> list[dict]:
        """Search Kalshi for markets matching a search term (public API)."""
        try:
            async with session.get(
                f"{KALSHI_BASE}/markets",
                params={"search": search_term, "status": "open", "limit": 10},
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("markets", [])
        except Exception as e:
            logger.debug(f"Kalshi fetch error: {e}")
            return []

    async def fetch_kalshi_price(
        self,
        session: aiohttp.ClientSession,
        market_ticker: str,
    ) -> float | None:
        """Fetch yes price for a specific Kalshi market ticker."""
        try:
            async with session.get(
                f"{KALSHI_BASE}/markets/{market_ticker}",
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                market = data.get("market", {})
                yes_bid = market.get("yes_bid", 0)
                yes_ask = market.get("yes_ask", 0)
                if yes_bid and yes_ask:
                    return (yes_bid + yes_ask) / 200.0  # convert cents to [0,1]
                return None
        except Exception as e:
            logger.debug(f"Kalshi price fetch error: {e}")
            return None

    async def fetch_metaculus_probability(
        self,
        session: aiohttp.ClientSession,
        question_id: int,
    ) -> float | None:
        """Fetch community forecast from Metaculus."""
        try:
            async with session.get(
                f"{METACULUS_BASE}/questions/{question_id}/",
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                # Community prediction
                community = data.get("community_prediction", {})
                return community.get("full", {}).get("q2")
        except Exception as e:
            logger.debug(f"Metaculus fetch error: {e}")
            return None

    async def search_metaculus(
        self,
        session: aiohttp.ClientSession,
        search_term: str,
        limit: int = 5,
    ) -> list[dict]:
        """Search Metaculus for relevant questions."""
        try:
            async with session.get(
                f"{METACULUS_BASE}/questions/",
                params={
                    "search": search_term,
                    "status": "open",
                    "type": "forecast",
                    "limit": limit,
                    "order_by": "-activity",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("results", [])
        except Exception as e:
            logger.debug(f"Metaculus search error: {e}")
            return []

    async def fetch_manifold_probability(
        self,
        session: aiohttp.ClientSession,
        market_slug: str,
    ) -> float | None:
        """Fetch Manifold market probability by slug."""
        try:
            async with session.get(
                f"{MANIFOLD_BASE}/slug/{market_slug}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("probability")
        except Exception as e:
            logger.debug(f"Manifold fetch error: {e}")
            return None

    async def search_manifold(
        self,
        session: aiohttp.ClientSession,
        search_term: str,
        limit: int = 5,
    ) -> list[dict]:
        """Search Manifold for relevant markets."""
        try:
            async with session.get(
                f"{MANIFOLD_BASE}/search-markets",
                params={"term": search_term, "limit": limit, "filter": "open"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.debug(f"Manifold search error: {e}")
            return []

    def compute_signal(
        self,
        polymarket_price: float,
        kalshi_price: float | None = None,
        metaculus_prob: float | None = None,
        manifold_prob: float | None = None,
    ) -> CrossMarketSignal:
        """
        Compute cross-market signal from available alternative prices.

        Algorithm:
        - For each available alternative, compute delta vs Polymarket
        - If multiple alternatives agree in direction → consensus
        - Magnitude = weighted average of deltas
        - LR derived from consensus strength
        """
        deltas: list[float] = []

        if kalshi_price is not None:
            deltas.append(kalshi_price - polymarket_price)
        if metaculus_prob is not None:
            deltas.append(metaculus_prob - polymarket_price)
        if manifold_prob is not None:
            deltas.append(manifold_prob - polymarket_price)

        if not deltas:
            return CrossMarketSignal(
                polymarket_price=polymarket_price,
                kalshi_price=kalshi_price,
                metaculus_prob=metaculus_prob,
                manifold_prob=manifold_prob,
                disagreement_magnitude=0.0,
                consensus_direction=0,
                n_sources_agree=0,
                likelihood_ratio=1.0,
                notes="No alternative data available",
            )

        # Direction: positive = alternatives say YES is more likely than PM
        n_positive = sum(1 for d in deltas if d > self.MIN_DIVERGENCE)
        n_negative = sum(1 for d in deltas if d < -self.MIN_DIVERGENCE)

        if n_positive > n_negative:
            consensus_direction = 1
            n_agree = n_positive
        elif n_negative > n_positive:
            consensus_direction = -1
            n_agree = n_negative
        else:
            consensus_direction = 0
            n_agree = 0

        magnitude = abs(sum(d for d in deltas) / len(deltas))

        # Strong signal requires at least 2 sources agreeing
        if n_agree >= 2 and magnitude > self.MIN_DIVERGENCE:
            lr = _cross_market_lr(magnitude, n_agree, consensus_direction)
        elif n_agree == 1 and magnitude > self.MIN_DIVERGENCE * 2:
            # Single strong source — weaker signal
            lr = _cross_market_lr(magnitude * 0.5, 1, consensus_direction)
        else:
            lr = 1.0

        notes = _format_notes(
            polymarket_price, kalshi_price, metaculus_prob, manifold_prob, deltas
        )

        return CrossMarketSignal(
            polymarket_price=polymarket_price,
            kalshi_price=kalshi_price,
            metaculus_prob=metaculus_prob,
            manifold_prob=manifold_prob,
            disagreement_magnitude=magnitude,
            consensus_direction=consensus_direction,
            n_sources_agree=n_agree,
            likelihood_ratio=lr,
            notes=notes,
        )


def _cross_market_lr(magnitude: float, n_sources: int, direction: int) -> float:
    """
    Compute likelihood ratio from cross-market divergence.

    magnitude: 0.0–1.0 (typical: 0.05–0.25)
    n_sources: 1–3
    direction: +1 or -1

    Formula:
    LR = exp(direction * magnitude * n_sources_multiplier * k)
    k = 1.5 (was 3.0 — previous calibration massively overweighted small divergences)
    """
    source_multiplier = {1: 0.5, 2: 0.85, 3: 1.1}.get(n_sources, 0.85)
    k = 1.5
    exponent = direction * magnitude * source_multiplier * k
    # Cap: cross-market arb signal should not dominate
    return max(0.5, min(2.5, math.exp(exponent)))


def _format_notes(
    pm: float,
    kalshi: float | None,
    metaculus: float | None,
    manifold: float | None,
    deltas: list[float],
) -> str:
    parts = [f"PM={pm:.3f}"]
    if kalshi is not None:
        parts.append(f"Kalshi={kalshi:.3f}")
    if metaculus is not None:
        parts.append(f"Metaculus={metaculus:.3f}")
    if manifold is not None:
        parts.append(f"Manifold={manifold:.3f}")
    avg_delta = sum(deltas) / len(deltas) if deltas else 0
    parts.append(f"AvgDelta={avg_delta:+.3f}")
    return " | ".join(parts)
