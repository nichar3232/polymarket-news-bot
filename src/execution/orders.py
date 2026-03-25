"""
Order lifecycle management.

Routes orders to either paper trader or live CLOB based on trading mode.
Tracks pending orders and fill confirmations.
"""
from __future__ import annotations

from typing import Literal, TYPE_CHECKING

from loguru import logger

from src.execution.paper import PaperTrader, PaperOrder
from src.risk.kelly import KellyResult

if TYPE_CHECKING:
    from src.execution.clob import CLOBExecutor, CLOBOrder


class OrderRouter:
    """
    Routes trades to paper or live execution based on configuration.
    """

    def __init__(
        self,
        paper_trader: PaperTrader,
        clob_executor: "CLOBExecutor | None" = None,
        trading_mode: Literal["paper", "live"] = "paper",
    ) -> None:
        self._paper = paper_trader
        self._clob = clob_executor
        self._mode = trading_mode

        if trading_mode == "live" and clob_executor is None:
            logger.warning("Live mode requested but no CLOB executor provided. Falling back to paper.")
            self._mode = "paper"

    async def execute(
        self,
        market_id: str,
        token_id: str,
        kelly: KellyResult,
        current_price: float,
    ) -> PaperOrder | "CLOBOrder | None":
        """Execute a trade based on Kelly sizing result."""
        if not kelly.is_positive:
            logger.debug(f"Skipping trade for {market_id}: no positive Kelly fraction")
            return None

        logger.info(
            f"TRADE DECISION | {kelly.direction} {market_id[:40]} | "
            f"${kelly.position_size_usd:.2f} | edge={kelly.edge:+.3f} | "
            f"mode={self._mode}"
        )

        if self._mode == "paper":
            return self._paper.place_from_kelly(market_id, kelly, current_price)
        else:
            if self._clob is None:
                logger.error("CLOB executor not available for live trade")
                return None
            return await self._clob.place_order(
                token_id=token_id,
                market_id=market_id,
                direction=kelly.direction,
                size_usd=kelly.position_size_usd,
                price=current_price,
            )

    async def close(
        self,
        market_id: str,
        token_id: str,
        current_price: float,
        order_id: str = "",
    ) -> float:
        """Close an existing position."""
        if self._mode == "paper":
            return self._paper.close_position(market_id, current_price)
        else:
            if self._clob and order_id:
                await self._clob.cancel_order(order_id)
            return 0.0

    @property
    def mode(self) -> str:
        return self._mode
