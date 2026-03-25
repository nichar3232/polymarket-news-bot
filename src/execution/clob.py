"""
Polymarket CLOB order placement.

Wraps the py-clob-client SDK for live trading.
Only active when TRADING_MODE=live and credentials are configured.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.constants import POLYGON
    from py_clob_client.clob_types import OrderArgs
    HAS_CLOB = True
except ImportError:
    HAS_CLOB = False


@dataclass
class CLOBOrder:
    order_id: str
    market_id: str
    token_id: str
    direction: Literal["YES", "NO"]
    size: float
    price: float
    status: str
    transaction_hash: str = ""


class CLOBExecutor:
    """
    Live order execution via Polymarket CLOB SDK.
    Requires valid API credentials and funder address.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        private_key: str,
        funder_address: str,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._private_key = private_key
        self._funder_address = funder_address
        self._client = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the CLOB client. Returns True if successful."""
        if not HAS_CLOB:
            logger.error("py-clob-client not installed. Run: pip install py-clob-client")
            return False
        try:
            self._client = ClobClient(
                host="https://clob.polymarket.com",
                key=self._private_key,
                chain_id=POLYGON,
                creds={
                    "apiKey": self._api_key,
                    "secret": self._api_secret,
                    "passphrase": self._api_passphrase,
                },
                signature_type=2,   # POLY_GNOSIS_SAFE
                funder=self._funder_address,
            )
            self._initialized = True
            logger.info("CLOB client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"CLOB initialization failed: {e}")
            return False

    async def place_order(
        self,
        token_id: str,
        market_id: str,
        direction: Literal["YES", "NO"],
        size_usd: float,
        price: float,
    ) -> CLOBOrder | None:
        """Place a limit order on the CLOB."""
        if not self._initialized:
            logger.error("CLOB client not initialized")
            return None

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size_usd / price,  # size in shares
                side="BUY",
            )

            response = await asyncio.to_thread(self._client.create_and_post_order, order_args)

            if response and response.get("success"):
                order_id = response.get("orderID", "")
                logger.info(
                    f"LIVE ORDER PLACED | {direction} {market_id[:40]} | "
                    f"${size_usd:.2f} @ {price:.4f} | ID: {order_id}"
                )
                return CLOBOrder(
                    order_id=order_id,
                    market_id=market_id,
                    token_id=token_id,
                    direction=direction,
                    size=size_usd / price,
                    price=price,
                    status="open",
                )
            else:
                logger.error(f"Order placement failed: {response}")
                return None

        except Exception as e:
            logger.error(f"CLOB order error: {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if not self._initialized:
            return False
        try:
            result = await asyncio.to_thread(self._client.cancel, order_id)
            return bool(result)
        except Exception as e:
            logger.error(f"Cancel order error: {e}")
            return False

    async def get_order_status(self, order_id: str) -> dict | None:
        """Get current order status."""
        if not self._initialized:
            return None
        try:
            return await asyncio.to_thread(self._client.get_order, order_id)
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            return None
