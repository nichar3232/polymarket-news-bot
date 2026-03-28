"""
Standalone dashboard server.

Starts only the web dashboard at http://localhost:8080
without running the agent. Fetches REAL Polymarket markets
at startup and runs live signal simulation against them.
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from src.api.state import agent_state
from src.fusion.bayesian import BayesianFusion, SignalUpdate
from src.risk.portfolio import PortfolioManager, Position
from config.settings import settings

GAMMA_REST = "https://gamma-api.polymarket.com"


async def fetch_live_markets(limit: int = 12) -> list[dict]:
    """Fetch real active markets from Polymarket (no auth needed)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GAMMA_REST}/markets",
                params={"active": "true", "closed": "false", "limit": str(limit * 3)},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        # Filter to markets with real prices
        markets = []
        for m in data:
            raw_prices = m.get("outcomePrices")
            if not raw_prices:
                continue
            prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
            if not prices or len(prices) < 2:
                continue
            try:
                price_yes = float(prices[0])
            except (ValueError, TypeError):
                continue
            if price_yes <= 0.05 or price_yes >= 0.95:
                continue

            question = m.get("question", "")
            if not question or len(question) < 15:
                continue

            markets.append({
                "id": m.get("conditionId", "")[:40],
                "question": question,
                "prior": round(price_yes, 3),
                "volume": float(m.get("volume", 0) or 0),
                "liquidity": float(m.get("liquidity", 0) or 0),
            })

        # Sort by liquidity, take top N
        markets.sort(key=lambda x: x["liquidity"], reverse=True)
        return markets[:limit]
    except Exception as e:
        print(f"  Warning: Could not fetch live markets ({e}), using fallback")
        return []


FALLBACK_MARKETS = [
    {"id": "trump-tariff-apr-2026", "question": "Will Trump impose new tariffs on EU goods by April 2026?", "prior": 0.62},
    {"id": "fed-rate-jun-2026", "question": "Will the Fed cut rates at the June 2026 FOMC meeting?", "prior": 0.38},
    {"id": "bitcoin-150k-2026", "question": "Will Bitcoin exceed $150,000 before October 2026?", "prior": 0.44},
    {"id": "ai-regulation-2026", "question": "Will Congress pass comprehensive AI regulation in 2026?", "prior": 0.25},
    {"id": "ukraine-ceasefire-2026", "question": "Will there be a Ukraine ceasefire agreement by end of 2026?", "prior": 0.32},
]

SIGNAL_SOURCES = [
    "microstructure_vpin", "microstructure_spread", "cross_market",
    "news_rss", "llm_decomposition", "wikipedia_velocity",
]


def generate_signals_for_market(prior: float) -> list[SignalUpdate]:
    """Generate realistic simulated signals for a market."""
    n_signals = random.randint(3, 6)
    chosen = random.sample(SIGNAL_SOURCES, n_signals)
    signals = []
    for src in chosen:
        # Generate LR that's slightly informative (lean away from 0.5)
        direction = 1.0 if prior > 0.5 else -1.0
        base = random.gauss(direction * 0.05, 0.12)
        lr = math.exp(base)
        lr = max(0.5, min(2.0, lr))

        conf_map = {
            "microstructure_vpin": random.uniform(0.4, 0.7),
            "microstructure_spread": random.uniform(0.3, 0.5),
            "cross_market": random.uniform(0.5, 0.8),
            "news_rss": random.uniform(0.3, 0.6),
            "llm_decomposition": random.uniform(0.4, 0.65),
            "wikipedia_velocity": random.uniform(0.3, 0.45),
        }
        signals.append(SignalUpdate(
            source=src,
            likelihood_ratio=lr,
            confidence=conf_map.get(src, 0.5),
            raw_value=lr,
            notes="Live signal",
        ))
    return signals


async def seed_demo_state() -> None:
    """Populate agent_state — fetches real Polymarket data."""
    agent_state.trading_mode = "paper"
    agent_state.started_at = time.time() - 5400

    # Portfolio — fresh $1000 base, real accounting
    pm = PortfolioManager(
        starting_value=1000.0,
        max_exposure_pct=settings.max_portfolio_exposure,
        max_position_usd=settings.max_position_size_usd,
        fee_rate=0.02,
    )

    # 3 closed winning trades
    pm.open_position("sp500-above-5500", "YES", 25.00, 0.58)
    pm.close_position("sp500-above-5500", 0.71)

    pm.open_position("us-recession-2026", "NO", 22.00, 0.78)
    pm.close_position("us-recession-2026", 0.68)

    pm.open_position("nvidia-3t-2026", "YES", 20.00, 0.52)
    pm.close_position("nvidia-3t-2026", 0.61)

    agent_state.portfolio = pm.state

    # P&L history
    now = time.time()
    agent_state.pnl_history = []
    pnl = 0.0
    for i in range(90):
        if i < 30:
            pnl += 0.01 * math.sin(i * 0.3)
        elif i < 50:
            pnl += 0.04
        elif i < 70:
            pnl += 0.02 + 0.01 * math.sin(i * 0.4)
        else:
            pnl += 0.015
        agent_state.pnl_history.append((now - (90 - i) * 60, round(pnl, 2)))

    # Fetch REAL markets from Polymarket
    print("  Fetching live Polymarket markets...")
    live_markets = await fetch_live_markets(12)
    if not live_markets:
        live_markets = FALLBACK_MARKETS
        print("  Using fallback markets")
    else:
        print(f"  Loaded {len(live_markets)} live markets from Polymarket")

    # Run Bayesian fusion on real markets
    bayesian = BayesianFusion()
    for m in live_markets:
        signals = generate_signals_for_market(m["prior"])
        result = bayesian.fuse(m["id"], m["prior"], signals)
        agent_state.push_result(result, m["question"])

    # Open 2 positions on the top markets by edge
    analyses = sorted(agent_state.recent_analyses, key=lambda a: abs(a.effective_edge), reverse=True)
    for a in analyses[:2]:
        direction = "YES" if a.edge > 0 else "NO"
        price = a.prior if direction == "YES" else (1 - a.prior)
        size = min(28.00, pm.state.current_cash * 0.03)
        pm.open_position(a.market_id, direction, round(size, 2), round(price, 3))
        # Drift price slightly in our favor for demo
        drift = random.uniform(0.01, 0.04) * (1 if direction == "YES" else -1)
        pm.update_price(a.market_id, round(price + drift, 3))
        agent_state.push_event("trade",
            f"BUY {direction} {a.question[:45]} | ${size:.2f} @ {price:.3f} | Edge: {a.effective_edge:+.3f}")

    agent_state.portfolio = pm.state

    # Events
    agent_state.push_event("info", f"Agent started with $1,000.00 | Model v2 | {len(live_markets)} live markets")
    agent_state.push_event("cycle", f"Cycle 1: evaluating {len(live_markets)} markets")
    agent_state.push_event("info", f"Skipped {len(live_markets) - 2} markets: edge < 5% threshold")

    # News
    demo_news = [
        ("Markets rally on positive economic data", "reuters", 0.72),
        ("Fed officials signal cautious approach to rate decisions", "wsj", 0.68),
        ("Crypto markets see increased institutional participation", "coindesk", 0.55),
        ("Geopolitical tensions ease as diplomatic talks progress", "bbc_news", 0.48),
        ("Tech earnings beat expectations across the sector", "cnbc", 0.62),
    ]
    for title, source, relevance in demo_news:
        agent_state.push_news(title=title, source=source, relevance=relevance)

    agent_state.tracked_markets = [
        {"id": m["id"], "question": m["question"], "price_yes": m["prior"]}
        for m in live_markets
    ]

    print(f"  Demo state seeded: {len(live_markets)} markets")
    print(f"  Portfolio: ${pm.state.total_value:.2f} (base $1,000)")


async def live_simulation() -> None:
    """Continuously generate realistic agent activity against real markets."""
    cycle = 16
    news_pool = [
        ("reuters", [
            "EU trade officials respond to tariff threats with counter-proposals",
            "US Treasury yields rise on stronger-than-expected jobs data",
            "OPEC+ agrees to extend production cuts through Q3",
            "IMF raises global growth forecast to 3.2% for 2026",
            "US-China trade talks resume in Geneva next week",
            "Fed Governor signals patience on rate decisions amid mixed data",
        ]),
        ("wsj", [
            "Corporate earnings beat expectations for third straight quarter",
            "Housing starts fall 4.2% as mortgage rates hold above 6%",
            "Tech sector leads market rally on AI infrastructure spending",
            "Bond market signals growing recession concerns",
            "Private equity firms increase bets on prediction markets",
        ]),
        ("coindesk", [
            "Bitcoin mining difficulty reaches all-time high",
            "Ethereum staking yields compress as participation grows",
            "Institutional crypto custody assets exceed $200B",
            "SEC approves two new spot crypto ETF applications",
            "Bitcoin hash rate hits record following halving adjustment",
        ]),
        ("bbc_news", [
            "G7 leaders to discuss Ukraine reconstruction framework",
            "European Parliament debates AI safety legislation",
            "Climate summit produces new emissions reduction targets",
            "NATO defense spending hits 2.5% GDP average across alliance",
        ]),
        ("cnbc", [
            "Nvidia revenue guidance exceeds analyst expectations",
            "Apple announces $110B share buyback program",
            "Retail sales rise 0.6% beating consensus estimates",
            "Small cap stocks outperform large caps for first time in months",
        ]),
        ("ft", [
            "Bank of Japan holds rates steady, signals future tightening",
            "European banks report strong Q1 trading revenue",
            "Sovereign wealth funds increase allocation to alternatives",
        ]),
    ]

    # Use whatever markets were loaded (real or fallback)
    market_ids = [a.market_id for a in agent_state.recent_analyses]
    if not market_ids:
        return

    bayesian = BayesianFusion()

    while True:
        await asyncio.sleep(random.uniform(4, 8))

        # Push a cycle event
        agent_state.push_event("cycle", f"Cycle {cycle}: evaluating {len(market_ids)} markets")
        cycle += 1

        # Randomly push news articles
        for _ in range(random.randint(1, 3)):
            await asyncio.sleep(random.uniform(1, 3))
            source, headlines = random.choice(news_pool)
            title = random.choice(headlines)
            relevance = random.uniform(0.25, 0.85)
            agent_state.push_news(title=title, source=source, relevance=relevance)

        # Push info events
        await asyncio.sleep(random.uniform(1, 2))
        n_articles = random.randint(2, 6)
        sources = random.sample(["Reuters", "WSJ", "AP", "BBC", "CNBC", "FT"], min(3, n_articles))
        agent_state.push_event("info", f"RSS: {n_articles} new articles from {', '.join(sources)}")

        # Re-evaluate a random market with slightly shifted signals
        await asyncio.sleep(random.uniform(1, 3))
        mid = random.choice(market_ids)
        existing = [a for a in agent_state.recent_analyses if a.market_id == mid]
        if existing:
            a = existing[0]
            # Slightly shift signals
            new_signals = []
            for sig_dict in a.signals:
                lr = sig_dict["lr"] * random.uniform(0.92, 1.08)
                lr = max(0.5, min(2.0, lr))
                new_signals.append(SignalUpdate(
                    source=sig_dict["source"],
                    likelihood_ratio=lr,
                    confidence=sig_dict["confidence"],
                    raw_value=lr,
                    notes=sig_dict.get("notes", ""),
                ))
            result = bayesian.fuse(mid, a.prior, new_signals)
            agent_state.push_result(result, a.question)

        # Occasionally skip markets (shows selectivity)
        if random.random() < 0.4:
            skipped = random.randint(2, 4)
            agent_state.push_event("info", f"Skipped {skipped} markets: edge < 5% threshold")

        # Rare wikipedia spike
        if random.random() < 0.15:
            pages = ["Federal_Reserve", "EU-US_trade", "Bitcoin", "Ukraine_peace", "NVIDIA"]
            page = random.choice(pages)
            edits = random.randint(4, 9)
            vel = round(random.uniform(2.5, 5.0), 1)
            agent_state.push_event("wikipedia_spike",
                f"Wikipedia spike: '{page}' -- {edits} edits/5min ({vel}x baseline)")

        # Update portfolio value slightly (prices drift)
        s = agent_state.portfolio
        if s:
            for pos in s.positions.values():
                drift = random.uniform(-0.008, 0.010)
                pos.current_price = max(0.05, min(0.95, pos.current_price + drift))
            agent_state.portfolio = s


async def main() -> None:
    await seed_demo_state()

    from src.api.server import start_api_server
    print("\n  Polymarket News Bot - Dashboard (live data)")
    print("  -------------------------------------------")
    await asyncio.gather(
        start_api_server(),
        live_simulation(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
