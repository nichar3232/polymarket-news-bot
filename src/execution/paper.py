"""
Paper trading simulator.

Simulates order execution against Polymarket prices without real capital.
Fully functional for demo — shows exactly what live trading would do.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger

from src.risk.kelly import KellyResult
from src.risk.portfolio import PortfolioManager, Position


@dataclass
class PaperOrder:
    order_id: str
    market_id: str
    direction: Literal["YES", "NO"]
    size_usd: float
    limit_price: float
    status: Literal["pending", "filled", "cancelled", "rejected"] = "pending"
    fill_price: float = 0.0
    fill_time: float = 0.0
    rejection_reason: str = ""

    @property
    def is_filled(self) -> bool:
        return self.status == "filled"


class PaperTrader:
    """
    Paper trading engine — simulates CLOB order placement and fills.

    Assumptions:
    - Orders fill immediately at the limit price (simplified execution)
    - No partial fills (simplified)
    - Slippage: +0.2% for YES buys, +0.2% for NO buys
    """

    SLIPPAGE = 0.002   # 0.2% simulated market impact

    def __init__(self, portfolio: PortfolioManager) -> None:
        self._portfolio = portfolio
        self._orders: dict[str, PaperOrder] = {}
        self._order_history: list[PaperOrder] = []

    def place_order(
        self,
        market_id: str,
        direction: Literal["YES", "NO"],
        size_usd: float,
        current_price: float,
    ) -> PaperOrder:
        """Simulate placing and immediately filling a market order."""
        order_id = str(uuid.uuid4())[:8]

        # Apply slippage
        fill_price = current_price * (1 + self.SLIPPAGE)
        fill_price = min(fill_price, 0.99)  # cap

        order = PaperOrder(
            order_id=order_id,
            market_id=market_id,
            direction=direction,
            size_usd=size_usd,
            limit_price=current_price,
        )

        # Check portfolio limits
        ok, reason = self._portfolio.can_open_position(size_usd)
        if not ok:
            order.status = "rejected"
            order.rejection_reason = reason
            logger.warning(f"Paper order rejected: {reason}")
            self._order_history.append(order)
            return order

        # Fill immediately (paper trading)
        position = self._portfolio.open_position(
            market_id=market_id,
            direction=direction,
            size_usd=size_usd,
            entry_price=fill_price,
            order_id=order_id,
            close_price=current_price,   # close opposing positions at pre-slippage price (Bug 9 fix)
        )

        if position:
            order.status = "filled"
            order.fill_price = fill_price
            order.fill_time = time.time()
            logger.info(
                f"PAPER FILL | {direction} {market_id[:40]} | "
                f"${size_usd:.2f} @ {fill_price:.4f} | ID: {order_id}"
            )
        else:
            order.status = "rejected"
            order.rejection_reason = "Portfolio limit check failed"

        self._orders[order_id] = order
        self._order_history.append(order)
        return order

    def close_position(self, market_id: str, current_price: float) -> float:
        """Close a paper position at the current price."""
        pnl = self._portfolio.close_position(market_id, current_price)
        logger.info(f"PAPER CLOSE | {market_id[:40]} @ {current_price:.4f} | PnL: {pnl:+.2f}")
        return pnl

    def place_from_kelly(
        self,
        market_id: str,
        kelly: KellyResult,
        current_price: float,
    ) -> PaperOrder:
        """Convenience: place an order from a KellyResult."""
        return self.place_order(
            market_id=market_id,
            direction=kelly.direction,
            size_usd=kelly.position_size_usd,
            current_price=current_price,
        )

    def estimate_slippage(self, size_usd: float, orderbook_depth: float = 0.0) -> float:
        """Estimate price impact based on position size relative to available depth.

        Uses a square-root market impact model: impact = k * sqrt(size / depth)
        This is standard in microstructure literature (Kyle 1985, Almgren-Chriss).

        Returns the estimated slippage as a fraction (e.g., 0.003 = 0.3%).
        """
        if orderbook_depth <= 0:
            return self.SLIPPAGE  # fallback to default

        # Square-root impact: k * sqrt(Q/V) where Q=order size, V=available depth
        k = 0.1  # calibrated for prediction market orderbooks
        participation_rate = size_usd / orderbook_depth
        impact = k * (participation_rate ** 0.5)

        # Floor at minimum slippage, cap at 2%
        return max(self.SLIPPAGE, min(impact, 0.02))

    def adjust_size_for_depth(self, size_usd: float, orderbook_depth: float) -> float:
        """Reduce position size if orderbook is too thin.

        If our order would consume >10% of available depth, scale down
        to avoid excessive market impact.
        """
        if orderbook_depth <= 0:
            return size_usd

        max_participation = 0.10  # never take more than 10% of book depth
        max_size = orderbook_depth * max_participation

        if size_usd > max_size:
            logger.info(
                f"Depth-adjusted size: ${size_usd:.2f} -> ${max_size:.2f} "
                f"(book depth=${orderbook_depth:.2f}, max 10% participation)"
            )
            return max_size
        return size_usd

    def get_order_history(self) -> list[PaperOrder]:
        return list(self._order_history)

    def get_filled_orders(self) -> list[PaperOrder]:
        return [o for o in self._order_history if o.is_filled]

    def print_summary(self) -> None:
        filled = self.get_filled_orders()
        print(f"\n{'='*60}")
        print("PAPER TRADING SUMMARY")
        print(f"{'='*60}")
        print(f"Total orders: {len(self._order_history)}")
        print(f"Filled: {len(filled)}")
        print(f"Rejected: {len([o for o in self._order_history if o.status == 'rejected'])}")
        print()
        print(self._portfolio.get_summary())
        print(f"{'='*60}\n")
