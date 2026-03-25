"""
Shared agent state — single source of truth for both the agent and the web API.

The agent writes to this module; the API reads from it and broadcasts
updates to connected WebSocket clients. All accesses happen in the same
asyncio event loop, so no locking is required.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.fusion.bayesian import BayesianResult
    from src.risk.portfolio import PortfolioState


@dataclass
class MarketAnalysis:
    market_id: str
    question: str
    prior: float
    posterior: float
    edge: float
    effective_edge: float
    trade_direction: str
    ci_lower: float
    ci_upper: float
    signal_count: int
    signals: list[dict]
    timestamp: float = field(default_factory=time.time)


@dataclass
class EventLog:
    timestamp: float
    kind: str      # "trade" | "cycle" | "wikipedia_spike" | "error" | "info"
    message: str


class AgentState:
    """
    Live agent state shared between the trading agent and the web dashboard.
    """

    MAX_EVENTS = 500
    MAX_RESULTS = 100

    def __init__(self) -> None:
        self.trading_mode: str = "paper"
        self.portfolio: PortfolioState | None = None
        self.tracked_markets: list[dict] = []
        self.recent_analyses: list[MarketAnalysis] = []
        self.events: list[EventLog] = []
        self.pnl_history: list[tuple[float, float]] = []   # (timestamp, pnl_pct)
        self.started_at: float = time.time()

        # WebSocket subscribers — set of asyncio.Queue instances, one per connection
        self._subscribers: set[asyncio.Queue[dict]] = set()

    # -----------------------------------------------------------------------
    # Write methods (called by agent)
    # -----------------------------------------------------------------------

    def push_result(self, result: "BayesianResult", question: str = "") -> None:
        analysis = MarketAnalysis(
            market_id=result.market_id,
            question=question or result.market_id,
            prior=result.prior_prob,
            posterior=result.posterior_prob,
            edge=result.edge,
            effective_edge=result.effective_edge,
            trade_direction=result.trade_direction,
            ci_lower=result.confidence_interval[0],
            ci_upper=result.confidence_interval[1],
            signal_count=result.signal_count,
            signals=[
                {
                    "source": s.source,
                    "lr": round(s.likelihood_ratio, 4),
                    "eff_lr": round(s.effective_lr, 4),
                    "confidence": round(s.confidence, 2),
                    "notes": s.notes,
                }
                for s in result.signals
            ],
        )

        # Replace existing analysis for same market
        self.recent_analyses = [a for a in self.recent_analyses if a.market_id != result.market_id]
        self.recent_analyses.append(analysis)
        if len(self.recent_analyses) > self.MAX_RESULTS:
            self.recent_analyses = self.recent_analyses[-self.MAX_RESULTS:]

        self._broadcast({"type": "analysis", "data": self._analysis_to_dict(analysis)})

    def push_event(self, kind: str, message: str) -> None:
        event = EventLog(timestamp=time.time(), kind=kind, message=message)
        self.events.append(event)
        if len(self.events) > self.MAX_EVENTS:
            self.events = self.events[-self.MAX_EVENTS:]
        self._broadcast({"type": "event", "data": {"kind": kind, "message": message, "ts": event.timestamp}})

    @property
    def portfolio_snapshot(self) -> dict:
        if self.portfolio is None:
            return {}
        s = self.portfolio
        snap = {
            "total_value": round(s.total_value, 2),
            "starting_value": round(s.starting_value, 2),
            "cash": round(s.current_cash, 2),
            "total_pnl": round(s.total_pnl, 2),
            "total_pnl_pct": round(s.total_pnl_pct * 100, 2),
            "exposure_usd": round(s.total_exposure_usd, 2),
            "exposure_pct": round(s.exposure_pct * 100, 2),
            "total_trades": s.total_trades,
            "win_rate": round(s.win_rate * 100, 1),
            "fees_paid": round(s.total_fees_paid, 2),
            "positions": [
                {
                    "market_id": mid,
                    "direction": pos.direction,
                    "size_usd": round(pos.size_usd, 2),
                    "entry_price": round(pos.entry_price, 4),
                    "current_price": round(pos.current_price, 4),
                    "pnl": round(pos.unrealized_pnl, 2),
                    "pnl_pct": round(pos.pnl_pct * 100, 2),
                }
                for mid, pos in s.positions.items()
            ],
        }
        # Record P&L history point
        self.pnl_history.append((time.time(), s.total_pnl_pct * 100))
        if len(self.pnl_history) > 500:
            self.pnl_history = self.pnl_history[-500:]

        self._broadcast({"type": "portfolio", "data": snap})
        return snap

    # -----------------------------------------------------------------------
    # WebSocket pub/sub
    # -----------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, message: dict) -> None:
        dead = set()
        for q in self._subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead.add(q)
        self._subscribers -= dead

    def full_snapshot(self) -> dict:
        """Initial payload sent to a new WebSocket connection."""
        return {
            "type": "snapshot",
            "data": {
                "trading_mode": self.trading_mode,
                "started_at": self.started_at,
                "portfolio": self.portfolio_snapshot,
                "analyses": [self._analysis_to_dict(a) for a in self.recent_analyses[-20:]],
                "events": [
                    {"kind": e.kind, "message": e.message, "ts": e.timestamp}
                    for e in self.events[-100:]
                ],
                "pnl_history": [
                    {"ts": ts, "pnl_pct": pnl} for ts, pnl in self.pnl_history
                ],
            },
        }

    @staticmethod
    def _analysis_to_dict(a: MarketAnalysis) -> dict:
        return {
            "market_id": a.market_id,
            "question": a.question,
            "prior": round(a.prior, 4),
            "posterior": round(a.posterior, 4),
            "edge": round(a.edge, 4),
            "effective_edge": round(a.effective_edge, 4),
            "trade_direction": a.trade_direction,
            "ci_lower": round(a.ci_lower, 4),
            "ci_upper": round(a.ci_upper, 4),
            "signal_count": a.signal_count,
            "signals": a.signals,
            "timestamp": a.timestamp,
        }


# Module-level singleton
agent_state = AgentState()
