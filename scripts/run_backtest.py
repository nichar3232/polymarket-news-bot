"""
Historical backtest engine.

Uses Polymarket's public trade history to backtest signal performance.
Evaluates: how often did our Bayesian posterior beat the market?
"""
from __future__ import annotations

import asyncio
import sys
import os
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import random

import aiohttp
import pandas as pd
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from src.fusion.bayesian import BayesianFusion, SignalUpdate
from src.risk.kelly import compute_kelly


console = Console()
POLYMARKET_HIST = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"


@dataclass
class BacktestTrade:
    market_id: str
    question: str
    prior_price: float
    posterior_prob: float
    edge: float
    direction: str
    outcome: bool | None    # True = YES resolved, False = NO resolved
    pnl_pct: float = 0.0
    position_size: float = 0.0


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)

    @property
    def n_trades(self) -> int:
        return len([t for t in self.trades if t.outcome is not None])

    @property
    def n_correct(self) -> int:
        return len([
            t for t in self.trades
            if t.outcome is not None and (
                (t.direction == "YES" and t.outcome) or
                (t.direction == "NO" and not t.outcome)
            )
        ])

    @property
    def accuracy(self) -> float:
        return self.n_correct / self.n_trades if self.n_trades > 0 else 0.0

    @property
    def total_pnl_pct(self) -> float:
        return sum(t.pnl_pct for t in self.trades if t.outcome is not None)

    @property
    def avg_edge(self) -> float:
        if not self.trades:
            return 0.0
        return sum(abs(t.edge) for t in self.trades) / len(self.trades)

    def calibration_summary(self) -> dict[str, float]:
        """Group predictions by bucket and compute calibration."""
        buckets: dict[str, list[tuple[float, bool]]] = {}
        for t in self.trades:
            if t.outcome is None:
                continue
            prob = t.posterior_prob
            bucket = f"{int(prob * 10) * 10}-{int(prob * 10) * 10 + 10}%"
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append((prob, t.outcome))

        return {
            bucket: sum(1 for _, o in items if o) / len(items)
            for bucket, items in buckets.items()
        }


async def fetch_resolved_markets(
    session: aiohttp.ClientSession,
    limit: int = 100,
) -> list[dict]:
    """Fetch recently resolved Polymarket markets."""
    try:
        async with session.get(
            f"{GAMMA_BASE}/markets",
            params={"closed": "true", "limit": limit, "order": "end_date_max"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch resolved markets: {e}")
        return []


def simulate_signal_for_market(
    market: dict,
    prior_price: float,
) -> list[SignalUpdate]:
    """
    Simulate what signals we would have had for a historical market.
    In a real backtest, these would come from GDELT/RSS archives.
    Here we use the final market price movement as a proxy.
    """
    # Simulate signals based on prior
    # In reality: replay GDELT archives, historical orderbook data
    signals = []

    # Simulated microstructure
    fake_vpin = random.uniform(0.2, 0.7)
    fake_ofi = random.uniform(-0.5, 0.5)
    signals.append(SignalUpdate(
        source="microstructure_vpin",
        likelihood_ratio=math.exp(fake_ofi * fake_vpin * 2),
        confidence=0.6,
        raw_value=fake_vpin,
        notes="Simulated (backtest)",
    ))

    return signals


async def run_backtest(n_markets: int = 50) -> BacktestResult:
    """Run backtest over historical resolved markets."""
    result = BacktestResult()
    bayesian = BayesianFusion()

    console.print(f"[cyan]Fetching {n_markets} resolved markets from Polymarket...[/cyan]")

    async with aiohttp.ClientSession() as session:
        markets = await fetch_resolved_markets(session, limit=n_markets)

    console.print(f"[green]Got {len(markets)} markets[/green]")

    for market in markets:
        try:
            tokens = market.get("tokens", [])
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no_token = next((t for t in tokens if t.get("outcome") == "No"), None)

            if not yes_token or not no_token:
                continue

            # Get price at some historical point (simplified: use midpoint of price history)
            # In a real backtest, replay tick-by-tick
            prior_price = float(yes_token.get("price", 0.5))
            if prior_price <= 0 or prior_price >= 1:
                continue

            # Did it resolve YES?
            outcome_str = market.get("resolution", market.get("winner", ""))
            if "yes" in outcome_str.lower():
                outcome = True
            elif "no" in outcome_str.lower():
                outcome = False
            else:
                continue   # Skip unresolved

            # Run Bayesian fusion with simulated signals
            signals = simulate_signal_for_market(market, prior_price)
            fusion_result = bayesian.fuse(
                market_id=market.get("conditionId", ""),
                prior_prob=prior_price,
                signals=signals,
            )

            if fusion_result.trade_direction == "NONE":
                continue

            kelly = compute_kelly(
                posterior_prob=fusion_result.posterior_prob,
                market_price_yes=prior_price,
                portfolio_value=1000.0,
                kelly_fraction=0.25,
                max_position_pct=0.05,
                max_position_usd=50.0,
            )

            if not kelly:
                continue

            # Compute P&L
            direction = fusion_result.trade_direction
            if direction == "YES":
                if outcome:
                    pnl_pct = (1 - prior_price) / prior_price * 0.98  # after fee
                else:
                    pnl_pct = -1.0
            else:
                if not outcome:
                    pnl_pct = prior_price / (1 - prior_price) * 0.98  # after fee
                else:
                    pnl_pct = -1.0

            result.trades.append(BacktestTrade(
                market_id=market.get("conditionId", ""),
                question=market.get("question", "")[:60],
                prior_price=prior_price,
                posterior_prob=fusion_result.posterior_prob,
                edge=fusion_result.edge,
                direction=direction,
                outcome=outcome,
                pnl_pct=pnl_pct * kelly.fractional_kelly,
                position_size=kelly.position_size_usd,
            ))

        except Exception as e:
            logger.debug(f"Backtest error for market: {e}")
            continue

    return result


def print_backtest_results(result: BacktestResult) -> None:
    console.print("\n")
    console.print(Panel(
        f"[bold]Total trades:[/bold] {result.n_trades}\n"
        f"[bold]Correct direction:[/bold] {result.n_correct} ({result.accuracy:.1%})\n"
        f"[bold]Total P&L:[/bold] {result.total_pnl_pct:+.2f}%\n"
        f"[bold]Average edge:[/bold] {result.avg_edge:.3f}",
        title="[cyan]Backtest Results[/cyan]",
        border_style="cyan",
    ))

    table = Table(title="Trade Log", box=box.ROUNDED)
    table.add_column("Question", width=40)
    table.add_column("Prior", width=7)
    table.add_column("Post", width=7)
    table.add_column("Edge", width=7)
    table.add_column("Trade", width=5)
    table.add_column("Outcome", width=8)
    table.add_column("P&L", width=8)

    for t in result.trades[:20]:
        if t.outcome is None:
            continue
        direction_correct = (t.direction == "YES" and t.outcome) or (t.direction == "NO" and not t.outcome)
        outcome_color = "green" if direction_correct else "red"
        pnl_color = "green" if t.pnl_pct > 0 else "red"
        table.add_row(
            t.question[:40],
            f"{t.prior_price:.3f}",
            f"{t.posterior_prob:.3f}",
            f"{t.edge:+.3f}",
            t.direction,
            Text("YES" if t.outcome else "NO", style=outcome_color),
            Text(f"{t.pnl_pct:+.3f}", style=pnl_color),
        )

    console.print(table)


def main() -> None:
    console.print("[bold cyan]Running Polymarket backtest...[/bold cyan]")
    result = asyncio.run(run_backtest(n_markets=50))
    print_backtest_results(result)


if __name__ == "__main__":
    main()
