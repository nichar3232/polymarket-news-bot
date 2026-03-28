"""
Polymarket CLOB order placement.

Wraps the py-clob-client SDK for live and testnet trading on Polygon.
Supports both mainnet (chain 137) and Amoy testnet (chain 80002).

Only active when TRADING_MODE=live or TRADING_MODE=testnet
and credentials are configured.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.constants import AMOY, POLYGON
    from py_clob_client.clob_types import OrderArgs
    HAS_CLOB = True
except ImportError:
    HAS_CLOB = False
    AMOY = 80002
    POLYGON = 137


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
    chain_id: int = 0


class CLOBExecutor:
    """
    Live order execution via Polymarket CLOB SDK.
    Supports mainnet (Polygon 137) and testnet (Amoy 80002).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        private_key: str,
        funder_address: str,
        host: str = "https://clob.polymarket.com",
        chain_id: int = 80002,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._private_key = private_key
        self._funder_address = funder_address
        self._host = host
        self._chain_id = chain_id
        self._client = None
        self._initialized = False

    @property
    def is_testnet(self) -> bool:
        return self._chain_id == AMOY

    @property
    def network_name(self) -> str:
        return "Amoy testnet" if self.is_testnet else "Polygon mainnet"

    def initialize(self) -> bool:
        """Initialize the CLOB client. Returns True if successful."""
        if not HAS_CLOB:
            logger.error("py-clob-client not installed. Run: pip install py-clob-client")
            return False
        try:
            self._client = ClobClient(
                host=self._host,
                key=self._private_key,
                chain_id=self._chain_id,
                creds={
                    "apiKey": self._api_key,
                    "secret": self._api_secret,
                    "passphrase": self._api_passphrase,
                },
                signature_type=2,   # POLY_GNOSIS_SAFE
                funder=self._funder_address,
            )
            self._initialized = True
            logger.info(f"CLOB client initialized on {self.network_name} (chain {self._chain_id})")
            return True
        except Exception as e:
            logger.error(f"CLOB initialization failed on {self.network_name}: {e}")
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

            net = "TESTNET" if self.is_testnet else "LIVE"
            logger.info(
                f"[{net}] Placing order: {direction} {market_id[:40]} | "
                f"${size_usd:.2f} @ {price:.4f}"
            )

            response = await asyncio.to_thread(self._client.create_and_post_order, order_args)

            if response and response.get("success"):
                order_id = response.get("orderID", "")
                tx_hash = response.get("transactionsHashes", [""])[0] if response.get("transactionsHashes") else ""
                logger.info(
                    f"[{net}] ORDER PLACED | {direction} {market_id[:40]} | "
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
                    transaction_hash=tx_hash,
                    chain_id=self._chain_id,
                )
            else:
                logger.error(f"[{net}] Order placement failed: {response}")
                return None

        except Exception as e:
            logger.error(f"CLOB order error on {self.network_name}: {e}")
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

    async def get_balance(self) -> dict | None:
        """Get CLOB allowances/balances for the configured account."""
        if not self._initialized:
            return None
        try:
            return await asyncio.to_thread(self._client.get_balance_allowance, {})
        except Exception as e:
            logger.debug(f"Balance check error: {e}")
            return None
