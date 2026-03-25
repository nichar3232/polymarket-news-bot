"""
Polymarket CLOB WebSocket + REST client.

Streams live orderbook data and trades for VPIN / microstructure calculations.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import aiohttp
from loguru import logger


POLYMARKET_REST = "https://clob.polymarket.com"
POLYMARKET_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_REST = "https://gamma-api.polymarket.com"


@dataclass
class Trade:
    market_id: str
    price: float
    size: float
    side: str        # "YES" or "NO"
    timestamp: float = field(default_factory=time.time)
    maker_order_id: str = ""
    taker_order_id: str = ""


@dataclass
class OrderbookSnapshot:
    market_id: str
    timestamp: float
    bids: list[tuple[float, float]]   # (price, size)
    asks: list[tuple[float, float]]
    best_bid: float = 0.0
    best_ask: float = 0.0
    mid_price: float = 0.0
    spread: float = 0.0

    def __post_init__(self) -> None:
        if self.bids:
            self.best_bid = max(p for p, _ in self.bids)
        if self.asks:
            self.best_ask = min(p for p, _ in self.asks)
        if self.best_bid and self.best_ask:
            self.mid_price = (self.best_bid + self.best_ask) / 2
            self.spread = self.best_ask - self.best_bid


@dataclass
class MarketInfo:
    condition_id: str
    question: str
    description: str
    end_date: str
    yes_token_id: str
    no_token_id: str
    price_yes: float = 0.0
    price_no: float = 0.0
    volume: float = 0.0
    liquidity: float = 0.0


class PolymarketClient:
    """REST + WebSocket client for Polymarket CLOB."""

    def __init__(self, api_key: str = "", api_secret: str = "", api_passphrase: str = "") -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._session: aiohttp.ClientSession | None = None
        self._trade_callbacks: list[Callable[[Trade], None]] = []

    async def __aenter__(self) -> "PolymarketClient":
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session:
            await self._session.close()

    def on_trade(self, callback: Callable[[Trade], None]) -> None:
        self._trade_callbacks.append(callback)

    async def get_markets(self, limit: int = 100, active_only: bool = True) -> list[MarketInfo]:
        """Fetch active markets from Gamma API (no auth required)."""
        params: dict[str, str | int] = {"limit": limit}
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"

        try:
            async with self._session.get(f"{GAMMA_REST}/markets", params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
                markets = []
                for m in data:
                    try:
                        yes_token = no_token = ""
                        price_yes = price_no = 0.0
                        for token in m.get("tokens", []):
                            if token.get("outcome") == "Yes":
                                yes_token = token.get("token_id", "")
                                price_yes = float(token.get("price", 0))
                            elif token.get("outcome") == "No":
                                no_token = token.get("token_id", "")
                                price_no = float(token.get("price", 0))

                        markets.append(MarketInfo(
                            condition_id=m.get("conditionId", ""),
                            question=m.get("question", ""),
                            description=m.get("description", ""),
                            end_date=m.get("endDate", ""),
                            yes_token_id=yes_token,
                            no_token_id=no_token,
                            price_yes=price_yes,
                            price_no=price_no,
                            volume=float(m.get("volume", 0)),
                            liquidity=float(m.get("liquidity", 0)),
                        ))
                    except (KeyError, ValueError, TypeError):
                        continue
                logger.info(f"Fetched {len(markets)} markets from Polymarket")
                return markets
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    async def get_orderbook(self, token_id: str) -> OrderbookSnapshot | None:
        """Fetch orderbook snapshot for a token (YES or NO side)."""
        try:
            async with self._session.get(
                f"{POLYMARKET_REST}/book",
                params={"token_id": token_id},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
                asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]
                return OrderbookSnapshot(
                    market_id=token_id,
                    timestamp=time.time(),
                    bids=bids,
                    asks=asks,
                )
        except Exception as e:
            logger.warning(f"Orderbook fetch failed for {token_id}: {e}")
            return None

    async def get_recent_trades(self, token_id: str, limit: int = 500) -> list[Trade]:
        """Fetch recent trades for a token."""
        try:
            async with self._session.get(
                f"{POLYMARKET_REST}/trades",
                params={"token_id": token_id, "limit": limit},
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                trades = []
                for t in data:
                    try:
                        trades.append(Trade(
                            market_id=token_id,
                            price=float(t.get("price", 0)),
                            size=float(t.get("size", 0)),
                            side="YES" if t.get("side", "").upper() == "BUY" else "NO",
                            timestamp=float(t.get("timestamp", time.time())),
                            maker_order_id=t.get("makerOrderId", ""),
                            taker_order_id=t.get("takerOrderId", ""),
                        ))
                    except (KeyError, ValueError, TypeError):
                        continue
                return trades
        except Exception as e:
            logger.warning(f"Trade fetch failed for {token_id}: {e}")
            return []

    async def stream_trades(self, token_ids: list[str]) -> AsyncIterator[Trade]:
        """Stream live trades via WebSocket."""
        import websockets

        subscribe_msg = json.dumps({
            "type": "Market",
            "assets_ids": token_ids,
        })

        while True:
            try:
                async with websockets.connect(POLYMARKET_WS) as ws:
                    await ws.send(subscribe_msg)
                    logger.info(f"WebSocket connected, tracking {len(token_ids)} tokens")

                    async for raw in ws:
                        try:
                            events = json.loads(raw)
                            if not isinstance(events, list):
                                events = [events]
                            for event in events:
                                if event.get("event_type") == "trade":
                                    trade = Trade(
                                        market_id=event.get("asset_id", ""),
                                        price=float(event.get("price", 0)),
                                        size=float(event.get("size", 0)),
                                        side="YES" if event.get("side", "").upper() == "BUY" else "NO",
                                        timestamp=float(event.get("timestamp", time.time())),
                                    )
                                    for cb in self._trade_callbacks:
                                        cb(trade)
                                    yield trade
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            except Exception as e:
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
