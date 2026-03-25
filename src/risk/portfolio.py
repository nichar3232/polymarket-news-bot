"""
Portfolio exposure tracker and risk manager.

Tracks all open positions, enforces exposure limits,
and monitors P&L in real time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger


@dataclass
class Position:
    market_id: str
    direction: Literal["YES", "NO"]
    size_usd: float
    entry_price: float
    current_price: float = 0.0
    timestamp: float = field(default_factory=time.time)
    order_id: str = ""

    @property
    def unrealized_pnl(self) -> float:
        if self.direction == "YES":
            return self.size_usd * (self.current_price - self.entry_price) / self.entry_price
        else:
            return self.size_usd * (self.entry_price - self.current_price) / self.entry_price

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.direction == "YES":
            return (self.current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.current_price) / self.entry_price


@dataclass
class PortfolioState:
    starting_value: float
    current_cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    closed_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    total_fees_paid: float = 0.0

    @property
    def total_exposure_usd(self) -> float:
        return sum(p.size_usd for p in self.positions.values())

    @property
    def total_value(self) -> float:
        return self.current_cash + self.total_exposure_usd + self.unrealized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self.closed_pnl + self.unrealized_pnl

    @property
    def total_pnl_pct(self) -> float:
        if self.starting_value == 0:
            return 0.0
        return self.total_pnl / self.starting_value

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def exposure_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return self.total_exposure_usd / self.total_value


class PortfolioManager:
    """
    Manages position lifecycle and enforces risk limits.
    """

    def __init__(
        self,
        starting_value: float = 1000.0,
        max_exposure_pct: float = 0.25,
        max_position_usd: float = 50.0,
        fee_rate: float = 0.02,
    ) -> None:
        self._max_exposure_pct = max_exposure_pct
        self._max_position_usd = max_position_usd
        self._fee_rate = fee_rate
        self.state = PortfolioState(
            starting_value=starting_value,
            current_cash=starting_value,
        )

    def can_open_position(self, size_usd: float) -> tuple[bool, str]:
        """Check if a new position is within risk limits."""
        if size_usd > self._max_position_usd:
            return False, f"Position ${size_usd:.2f} exceeds max ${self._max_position_usd:.2f}"

        new_exposure = self.state.total_exposure_usd + size_usd
        max_exposure = self.state.total_value * self._max_exposure_pct
        if new_exposure > max_exposure:
            return False, (
                f"New total exposure ${new_exposure:.2f} would exceed "
                f"limit ${max_exposure:.2f} ({self._max_exposure_pct:.0%} of portfolio)"
            )

        if size_usd > self.state.current_cash:
            return False, f"Insufficient cash: ${self.state.current_cash:.2f} < ${size_usd:.2f}"

        return True, "OK"

    def open_position(
        self,
        market_id: str,
        direction: Literal["YES", "NO"],
        size_usd: float,
        entry_price: float,
        order_id: str = "",
    ) -> Position | None:
        """Record a new position."""
        ok, reason = self.can_open_position(size_usd)
        if not ok:
            logger.warning(f"Cannot open position for {market_id}: {reason}")
            return None

        # Close existing position in opposite direction (flip)
        if market_id in self.state.positions:
            existing = self.state.positions[market_id]
            if existing.direction != direction:
                self.close_position(market_id, entry_price)

        position = Position(
            market_id=market_id,
            direction=direction,
            size_usd=size_usd,
            entry_price=entry_price,
            current_price=entry_price,
            order_id=order_id,
        )
        self.state.positions[market_id] = position
        fee = size_usd * self._fee_rate
        self.state.current_cash -= size_usd + fee
        self.state.total_fees_paid += fee
        self.state.total_trades += 1

        logger.info(
            f"Opened {direction} position: {market_id} | "
            f"${size_usd:.2f} @ {entry_price:.3f} | "
            f"fee=${fee:.2f}"
        )
        return position

    def close_position(self, market_id: str, exit_price: float) -> float:
        """Close a position and record P&L."""
        if market_id not in self.state.positions:
            return 0.0

        position = self.state.positions.pop(market_id)
        position.current_price = exit_price

        pnl = position.unrealized_pnl
        fee = abs(pnl) * self._fee_rate if pnl > 0 else 0
        net_pnl = pnl - fee
        self.state.total_fees_paid += fee

        # Return capital + net PnL
        self.state.current_cash += position.size_usd + net_pnl
        self.state.closed_pnl += net_pnl

        if net_pnl > 0:
            self.state.winning_trades += 1

        logger.info(
            f"Closed {position.direction} position: {market_id} | "
            f"entry={position.entry_price:.3f} exit={exit_price:.3f} | "
            f"PnL={pnl:+.2f} net={net_pnl:+.2f}"
        )
        return net_pnl

    def update_price(self, market_id: str, current_price: float) -> None:
        """Update current market price for an open position."""
        if market_id in self.state.positions:
            self.state.positions[market_id].current_price = current_price

    def get_summary(self) -> str:
        s = self.state
        lines = [
            f"Portfolio: ${s.total_value:.2f} (start ${s.starting_value:.2f})",
            f"P&L: {s.total_pnl:+.2f} ({s.total_pnl_pct:+.1%})",
            f"Cash: ${s.current_cash:.2f} | Exposure: ${s.total_exposure_usd:.2f} ({s.exposure_pct:.1%})",
            f"Trades: {s.total_trades} | Win rate: {s.win_rate:.1%} | Fees: ${s.total_fees_paid:.2f}",
        ]
        if s.positions:
            lines.append("\nOpen positions:")
            for market_id, pos in s.positions.items():
                lines.append(
                    f"  {market_id[:40]}: {pos.direction} ${pos.size_usd:.2f} "
                    f"@ {pos.entry_price:.3f} | PnL: {pos.unrealized_pnl:+.2f}"
                )
        return "\n".join(lines)
