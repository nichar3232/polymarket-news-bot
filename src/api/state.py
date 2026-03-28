"""
Shared agent state — single source of truth for both the agent and the web API.

The agent writes to this module; the API reads from it and broadcasts
updates to connected WebSocket clients. All accesses happen in the same
asyncio event loop, so no locking is required.
"""
from __future__ import annotations

import asyncio
import math
import time
from math import sqrt
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
        self.news_items: list[dict] = []
        self.pnl_history: list[tuple[float, float]] = []   # (timestamp, pnl_pct)
        self.started_at: float = time.time()
        self._seen_news_titles: set[str] = set()   # dedup by normalized title

        # WebSocket subscribers — set of asyncio.Queue instances, one per connection
        self._subscribers: set[asyncio.Queue[dict]] = set()

        # Rate-limit pnl_history recording (Bug 10 fix)
        self._last_pnl_record: float = 0.0

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

        from src.fusion.calibration import calibration_tracker
        calibration_tracker.record_prediction(
            market_id=result.market_id,
            predicted_prob=result.posterior_prob,
            signal_count=result.signal_count,
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

    MAX_NEWS = 200

    def push_news(self, title: str, source: str, relevance: float, market_id: str = "") -> None:
        # Deduplicate by normalized title — same article can match multiple markets
        key = title.strip().lower()[:120]
        if key in self._seen_news_titles:
            return
        self._seen_news_titles.add(key)
        # Prevent unbounded growth of the seen set
        if len(self._seen_news_titles) > 2000:
            self._seen_news_titles = set(list(self._seen_news_titles)[-1000:])

        item = {
            "title": title,
            "source": source,
            "relevance": round(relevance, 2),
            "market_id": market_id,
            "ts": time.time(),
        }
        self.news_items.append(item)
        if len(self.news_items) > self.MAX_NEWS:
            self.news_items = self.news_items[-self.MAX_NEWS:]
        self._broadcast({"type": "news", "data": item})

    def _build_portfolio_snap(self) -> dict:
        """Build portfolio snapshot dict — pure, no side effects."""
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

        # Sharpe ratio (annualized) — require at least 20 data points to be meaningful
        sharpe_ratio = None
        if len(self.pnl_history) >= 20:
            pnl_vals = [p for _, p in self.pnl_history]
            returns = [pnl_vals[i] - pnl_vals[i - 1] for i in range(1, len(pnl_vals))]
            mean_ret = sum(returns) / len(returns)
            std_ret = (sum((r - mean_ret) ** 2 for r in returns) / len(returns)) ** 0.5
            if std_ret > 0:
                sharpe_ratio = round(max(-9.99, min(9.99, (mean_ret / std_ret) * sqrt(252))), 2)

        # Max drawdown (peak-to-trough) from pnl_history
        max_drawdown_pct = None
        if len(self.pnl_history) >= 2:
            pnl_vals = [p for _, p in self.pnl_history]
            peak = pnl_vals[0]
            max_dd = 0.0
            for v in pnl_vals:
                if v > peak:
                    peak = v
                dd = peak - v
                if dd > max_dd:
                    max_dd = dd
            max_drawdown_pct = round(max_dd, 2)

        # Profit factor
        profit_factor = None
        pf = s.profit_factor
        if not (math.isnan(pf) if isinstance(pf, float) and not math.isinf(pf) else False):
            profit_factor = round(pf, 2) if not math.isinf(pf) else 999.99

        snap["sharpe_ratio"] = sharpe_ratio
        snap["max_drawdown_pct"] = max_drawdown_pct
        snap["profit_factor"] = profit_factor
        return snap

    def _record_pnl_point(self) -> None:
        """Append a P&L history point — rate-limited to once per 30 s (Bug 10 fix)."""
        now = time.time()
        if now - self._last_pnl_record >= 30:
            self.pnl_history.append((now, self.portfolio.total_pnl_pct * 100))
            self._last_pnl_record = now
            if len(self.pnl_history) > 500:
                self.pnl_history = self.pnl_history[-500:]

    def push_portfolio(self) -> None:
        """Broadcast current portfolio to all WS clients.

        Call this at the end of each agent cycle — portfolio_snapshot is only
        triggered on WS connect / REST GET, so without this the TopBar P&L is
        permanently stale (Bug 1 fix).
        """
        if self.portfolio is None:
            return
        self._record_pnl_point()
        snap = self._build_portfolio_snap()
        self._broadcast({"type": "portfolio", "data": snap})

    @property
    def portfolio_snapshot(self) -> dict:
        if self.portfolio is None:
            return {}
        self._record_pnl_point()
        snap = self._build_portfolio_snap()
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
        for q in list(self._subscribers):   # copy to avoid RuntimeError on concurrent subscribe/unsubscribe (Bug 3 fix)
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
                "news": self.news_items[-50:],
            },
        }

    @staticmethod
    def _safe_float(v: float, default: float = 0.0) -> float:
        """Replace NaN / Infinity with a safe default so JSON stays valid."""
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return default
        return v

    @classmethod
    def _analysis_to_dict(cls, a: MarketAnalysis) -> dict:
        sf = cls._safe_float
        return {
            "market_id": a.market_id,
            "question": a.question,
            "prior": sf(round(a.prior, 4), 0.5),
            "posterior": sf(round(a.posterior, 4), 0.5),
            "edge": sf(round(a.edge, 4)),
            "effective_edge": sf(round(a.effective_edge, 4)),
            "trade_direction": a.trade_direction,
            "ci_lower": sf(round(a.ci_lower, 4), 0.02),
            "ci_upper": sf(round(a.ci_upper, 4), 0.98),
            "signal_count": a.signal_count,
            "signals": [
                {
                    k: (sf(v) if isinstance(v, float) else v)
                    for k, v in sig.items()
                }
                for sig in a.signals
            ],
            "timestamp": a.timestamp,
        }


# Module-level singleton
agent_state = AgentState()
