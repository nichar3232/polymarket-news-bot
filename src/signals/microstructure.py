"""
Market microstructure signals: VPIN, order flow imbalance, spread analysis.

VPIN (Volume-synchronized Probability of Informed Trading) is adapted from
academic HFT literature. It detects when informed traders are active by
measuring the imbalance of buy vs. sell initiated volume in equal-volume buckets.

High VPIN → likely informed trading is occurring → follow the order flow direction.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger

from src.ingestion.polymarket import Trade, OrderbookSnapshot


@dataclass
class VPINResult:
    vpin: float                      # 0.0–1.0 (higher = more informed trading)
    order_flow_imbalance: float      # -1.0 to +1.0 (positive = YES pressure)
    n_buckets_used: int
    total_volume: float
    yes_volume: float
    no_volume: float
    signal: Literal["bullish", "bearish", "neutral"]
    likelihood_ratio: float          # Bayesian LR to feed into fusion engine

    @property
    def is_informed(self) -> bool:
        return self.vpin > 0.4

    @property
    def is_highly_informed(self) -> bool:
        return self.vpin > 0.6


@dataclass
class SpreadSignal:
    best_bid: float
    best_ask: float
    spread: float
    spread_pct: float         # spread / mid_price
    mid_price: float
    depth_yes: float          # total liquidity on YES side (top 5 levels)
    depth_no: float           # total liquidity on NO side (top 5 levels)
    depth_imbalance: float    # (depth_yes - depth_no) / (depth_yes + depth_no)
    likelihood_ratio: float


class MicrostructureAnalyzer:
    """
    Computes VPIN and order flow signals from a stream of trades.
    Maintains a rolling buffer of recent trades for computation.
    """

    def __init__(self, n_buckets: int = 50, buffer_size: int = 2000) -> None:
        self._n_buckets = n_buckets
        self._trade_buffer: deque[Trade] = deque(maxlen=buffer_size)

    def add_trade(self, trade: Trade) -> None:
        self._trade_buffer.append(trade)

    def add_trades(self, trades: list[Trade]) -> None:
        for t in trades:
            self._trade_buffer.append(t)

    def compute_vpin(self) -> VPINResult | None:
        """
        Compute VPIN from the current trade buffer.

        Algorithm:
        1. Partition trades into n equal-volume buckets
        2. For each bucket: sum YES-initiated vs NO-initiated volume
        3. VPIN = mean(|yes_vol - no_vol|) / bucket_size
        """
        trades = list(self._trade_buffer)
        if len(trades) < self._n_buckets * 2:
            return None

        total_volume = sum(t.size for t in trades)
        if total_volume == 0:
            return None

        bucket_size = total_volume / self._n_buckets

        # Partition into volume buckets
        buckets: list[tuple[float, float]] = []   # (yes_vol, no_vol) per bucket
        current_yes = 0.0
        current_no = 0.0
        current_vol = 0.0

        for trade in trades:
            remaining = trade.size
            while remaining > 0:
                space = bucket_size - current_vol
                fill = min(remaining, space)

                if trade.side == "YES":
                    current_yes += fill
                else:
                    current_no += fill

                current_vol += fill
                remaining -= fill

                if current_vol >= bucket_size - 1e-9:
                    buckets.append((current_yes, current_no))
                    current_yes = 0.0
                    current_no = 0.0
                    current_vol = 0.0

        if not buckets:
            return None

        # VPIN = mean absolute imbalance / bucket_size
        imbalances = [abs(y - n) for y, n in buckets]
        vpin = sum(imbalances) / (len(buckets) * bucket_size)
        vpin = min(vpin, 1.0)

        # Order flow imbalance (direction)
        total_yes = sum(y for y, _ in buckets)
        total_no = sum(n for _, n in buckets)
        ofi_denominator = total_yes + total_no
        ofi = (total_yes - total_no) / ofi_denominator if ofi_denominator > 0 else 0.0

        # Signal direction
        if vpin > 0.4:
            signal: Literal["bullish", "bearish", "neutral"] = (
                "bullish" if ofi > 0.05 else "bearish" if ofi < -0.05 else "neutral"
            )
        else:
            signal = "neutral"

        # Convert to likelihood ratio
        lr = _vpin_to_likelihood_ratio(vpin, ofi)

        return VPINResult(
            vpin=vpin,
            order_flow_imbalance=ofi,
            n_buckets_used=len(buckets),
            total_volume=total_volume,
            yes_volume=total_yes,
            no_volume=total_no,
            signal=signal,
            likelihood_ratio=lr,
        )

    def compute_spread_signal(self, snapshot: OrderbookSnapshot) -> SpreadSignal:
        """
        Analyze orderbook depth and spread for microstructure signals.

        Depth imbalance: if more liquidity is sitting on NO side, market makers
        expect downward pressure (and vice versa).
        """
        depth_yes = sum(size for price, size in snapshot.bids[:5])
        depth_no = sum(size for price, size in snapshot.asks[:5])
        d_total = depth_yes + depth_no
        depth_imbalance = (depth_yes - depth_no) / d_total if d_total > 0 else 0.0

        spread_pct = snapshot.spread / snapshot.mid_price if snapshot.mid_price > 0 else 0.0

        lr = _spread_to_likelihood_ratio(depth_imbalance, spread_pct)

        return SpreadSignal(
            best_bid=snapshot.best_bid,
            best_ask=snapshot.best_ask,
            spread=snapshot.spread,
            spread_pct=spread_pct,
            mid_price=snapshot.mid_price,
            depth_yes=depth_yes,
            depth_no=depth_no,
            depth_imbalance=depth_imbalance,
            likelihood_ratio=lr,
        )


def _vpin_to_likelihood_ratio(vpin: float, ofi: float) -> float:
    """
    Map VPIN + order flow imbalance to a Bayesian likelihood ratio.

    Logic:
    - If VPIN is high AND order flow is directional → strong signal
    - VPIN alone (without direction) → uncertainty → LR near 1.0
    - Informed buying (high vpin, ofi > 0) → LR > 1 (YES signal)
    - Informed selling (high vpin, ofi < 0) → LR < 1 (NO signal)
    """
    if vpin < 0.3:
        return 1.0   # No informed trading — neutral

    # Scale: VPIN 0.3–1.0 mapped to strength 0–1
    vpin_strength = (vpin - 0.3) / 0.7

    # OFI direction: |ofi| * sign
    direction_magnitude = ofi * vpin_strength

    # Map to LR: e^(k * direction_magnitude)
    # k=2 means OFI=1.0 at full vpin → LR = e^2 ≈ 7.4 (very strong)
    k = 2.0
    lr = math.exp(k * direction_magnitude)
    return lr


def _spread_to_likelihood_ratio(depth_imbalance: float, spread_pct: float) -> float:
    """
    Convert depth imbalance to a likelihood ratio.

    depth_imbalance > 0 → more YES liquidity → market makers hedging YES risk → NO signal
    (market makers provide liquidity against the direction they expect to move)

    Actually more nuanced — large depth imbalance either way is informative.
    We use a mild signal here.
    """
    # Small depth imbalance contribution
    # Positive depth_imbalance (more YES bids) = market expects YES → LR slight boost
    lr = math.exp(depth_imbalance * 0.5)

    # Very wide spread → uncertainty → LR closer to 1
    if spread_pct > 0.05:
        lr = 1.0 + (lr - 1.0) * 0.5   # halve the signal under wide spread

    return max(0.5, min(lr, 2.0))   # Cap for safety
