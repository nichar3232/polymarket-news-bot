"""
Order lifecycle management.

Routes orders to paper trader, testnet CLOB, or live CLOB based on trading mode.
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
    Routes trades to paper, testnet, or live execution based on configuration.

    Modes:
      - "paper":   simulated execution via PaperTrader (default)
      - "testnet": real orders on Polygon Amoy testnet via CLOB
      - "live":    real orders on Polygon mainnet via CLOB
    """

    def __init__(
        self,
        paper_trader: PaperTrader,
        clob_executor: "CLOBExecutor | None" = None,
        trading_mode: Literal["paper", "testnet", "live"] = "paper",
    ) -> None:
        self._paper = paper_trader
        self._clob = clob_executor
        self._mode = trading_mode

        if trading_mode in ("live", "testnet") and clob_executor is None:
            logger.warning(
                f"{trading_mode} mode requested but no CLOB executor provided. "
                f"Falling back to paper."
            )
            self._mode = "paper"
        elif trading_mode in ("live", "testnet") and clob_executor is not None:
            if not clob_executor._initialized:
                ok = clob_executor.initialize()
                if not ok:
                    logger.warning("CLOB executor failed to initialize. Falling back to paper.")
                    self._mode = "paper"

    @property
    def is_on_chain(self) -> bool:
        return self._mode in ("testnet", "live")

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
            # testnet or live — route to CLOB
            if self._clob is None:
                logger.error(f"CLOB executor not available for {self._mode} trade")
                return None

            result = await self._clob.place_order(
                token_id=token_id,
                market_id=market_id,
                direction=kelly.direction,
                size_usd=kelly.position_size_usd,
                price=current_price,
            )

            # Also record in paper trader for portfolio tracking
            if result is not None:
                self._paper.place_from_kelly(market_id, kelly, current_price)

            return result

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
            # Also close in paper tracker
            return self._paper.close_position(market_id, current_price)

    @property
    def mode(self) -> str:
        return self._mode
