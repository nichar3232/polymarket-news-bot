"""
Standalone dashboard server.

Starts only the web dashboard at http://localhost:8080
without running the agent. Useful for testing the UI or
showing the dashboard to judges without needing API keys.

Seeds the state with the same historical demo data as demo_event.py
so the UI has something to display.
"""
from __future__ import annotations

import asyncio
import math
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.state import agent_state
from src.fusion.bayesian import BayesianFusion, SignalUpdate
from src.risk.portfolio import PortfolioManager, Position


def seed_demo_state() -> None:
    """Populate agent_state with realistic demo data."""
    agent_state.trading_mode = "paper"
    agent_state.started_at = time.time() - 3600   # pretend we started an hour ago

    # Portfolio
    pm = PortfolioManager(starting_value=1000.0)
    # Simulate a few closed + open positions
    pm.state.closed_pnl = 14.20
    pm.state.total_trades = 7
    pm.state.winning_trades = 5
    pm.state.total_fees_paid = 2.10
    pm.state.current_cash = 880.0
    pm.state.positions = {
        "fed-rate-march-2024": Position(
            market_id="fed-rate-march-2024",
            direction="NO",
            size_usd=50.0,
            entry_price=0.82,
            current_price=0.88,
        ),
        "ukraine-ceasefire-2025": Position(
            market_id="ukraine-ceasefire-2025",
            direction="NO",
            size_usd=35.0,
            entry_price=0.55,
            current_price=0.58,
        ),
    }
    agent_state.portfolio = pm.state

    # Seed P&L history (simulated curve)
    now = time.time()
    agent_state.pnl_history = [
        (now - (60 - i) * 60, round(i * 0.25 - 2 + math.sin(i * 0.5) * 0.8, 2))
        for i in range(60)
    ]

    # Markets analysis
    bayesian = BayesianFusion()

    demo_markets = [
        {
            "id": "fed-rate-march-2024",
            "question": "Will the Fed cut rates at the March 2024 FOMC meeting?",
            "prior": 0.18,
            "signals": [
                SignalUpdate("news_rss", 0.42, 0.80, -0.65, "Reuters: CPI miss +0.4%, above forecast"),
                SignalUpdate("microstructure_vpin", 0.55, 0.70, 0.52, "VPIN=0.52, OFI=-0.38, bearish"),
                SignalUpdate("cross_market", 0.38, 0.85, 0.06, "Kalshi=0.12, Metaculus=0.10, Manifold=0.15"),
                SignalUpdate("llm_decomposition", 0.72, 0.75, 0.15, "P(YES)=0.15, CI=[0.08,0.25]"),
                SignalUpdate("wikipedia_velocity", 1.20, 0.60, 4.2, "4.2x edit spike on Federal_Reserve"),
            ],
        },
        {
            "id": "ukraine-ceasefire-2025",
            "question": "Will there be a Ukraine ceasefire agreement in 2025?",
            "prior": 0.42,
            "signals": [
                SignalUpdate("news_rss", 0.95, 0.70, -0.3, "AP: Talks stalled, no breakthrough imminent"),
                SignalUpdate("cross_market", 0.85, 0.65, 0.04, "Metaculus=0.38 (vs PM=0.42)"),
                SignalUpdate("llm_decomposition", 1.05, 0.60, 0.44, "P(YES)=0.44, CI=[0.30,0.58]"),
            ],
        },
        {
            "id": "sp500-6000-2025",
            "question": "Will S&P 500 close above 6000 at end of 2025?",
            "prior": 0.55,
            "signals": [
                SignalUpdate("news_rss", 1.15, 0.65, 0.4, "WSJ: Strong earnings season continues"),
                SignalUpdate("cross_market", 1.20, 0.70, 0.05, "Kalshi=0.61 (vs PM=0.55)"),
                SignalUpdate("reddit_social", 1.08, 0.35, 0.3, "r/Economics bullish sentiment +0.3"),
                SignalUpdate("llm_decomposition", 1.10, 0.65, 0.62, "P(YES)=0.62, CI=[0.45,0.75]"),
            ],
        },
        {
            "id": "ai-regulation-2025",
            "question": "Will the US pass major AI regulation legislation in 2025?",
            "prior": 0.22,
            "signals": [
                SignalUpdate("news_rss", 0.88, 0.55, -0.2, "Politico: AI bill faces Senate opposition"),
                SignalUpdate("llm_decomposition", 0.75, 0.70, 0.17, "P(YES)=0.17, low base rate"),
                SignalUpdate("microstructure_vpin", 1.05, 0.40, 0.32, "VPIN=0.32 neutral"),
            ],
        },
        {
            "id": "bitcoin-100k-2025",
            "question": "Will Bitcoin exceed $100,000 before June 2025?",
            "prior": 0.68,
            "signals": [
                SignalUpdate("news_rss", 1.20, 0.72, 0.45, "CoinDesk: Institutional demand rising"),
                SignalUpdate("cross_market", 1.35, 0.80, 0.07, "Kalshi=0.74, Manifold=0.71"),
                SignalUpdate("microstructure_vpin", 1.45, 0.75, 0.62, "VPIN=0.62, OFI=+0.48 YES pressure"),
                SignalUpdate("llm_decomposition", 1.15, 0.68, 0.76, "P(YES)=0.76, CI=[0.58,0.89]"),
            ],
        },
    ]

    for m in demo_markets:
        result = bayesian.fuse(m["id"], m["prior"], m["signals"])
        agent_state.push_result(result, m["question"])

    # Events
    demo_events = [
        ("trade", "BUY NO fed-rate-march-2024 | $50.00 @ 0.822 | Edge: -0.137 | Kelly: $50.00 (capped)"),
        ("trade", "BUY NO ukraine-ceasefire-2025 | $35.00 @ 0.552 | Edge: -0.024"),
        ("wikipedia_spike", "Wikipedia spike: 'Federal_Reserve' — 8 edits/5min (4.2x baseline)"),
        ("cycle", "Cycle 12: evaluating 5 markets"),
        ("info", "RSS: 3 new articles from Reuters, AP"),
        ("cycle", "Cycle 11: evaluating 5 markets"),
        ("trade", "BUY YES bitcoin-100k-2025 | $45.00 @ 0.681 | Edge: +0.052"),
        ("info", "Wikipedia spike: 'Bitcoin' — 5 edits/5min (3.8x baseline)"),
        ("cycle", "Cycle 10: evaluating 5 markets"),
    ]

    for kind, msg in demo_events:
        agent_state.push_event(kind, msg)

    agent_state.tracked_markets = [
        {"id": m["id"], "question": m["question"], "price_yes": m["prior"]}
        for m in demo_markets
    ]

    print(f"  Demo state seeded: {len(demo_markets)} markets, {len(demo_events)} events")


async def main() -> None:
    seed_demo_state()

    from src.api.server import start_api_server
    print("\n  Polymarket News Bot — Dashboard (demo mode)")
    print("  ──────────────────────────────────────────")
    await start_api_server()


if __name__ == "__main__":
    asyncio.run(main())
