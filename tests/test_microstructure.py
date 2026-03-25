"""Tests for VPIN and microstructure signals."""
import math
import pytest

from src.ingestion.polymarket import Trade
from src.signals.microstructure import (
    MicrostructureAnalyzer,
    VPINResult,
    _vpin_to_likelihood_ratio,
    _spread_to_likelihood_ratio,
)


def make_trades(yes_vol: float, no_vol: float, n: int = 100) -> list[Trade]:
    """Create a balanced set of fake trades."""
    trades = []
    yes_per = yes_vol / n
    no_per = no_vol / n
    for i in range(n):
        trades.append(Trade(
            market_id="test",
            price=0.5,
            size=yes_per,
            side="YES",
            timestamp=float(i),
        ))
        trades.append(Trade(
            market_id="test",
            price=0.5,
            size=no_per,
            side="NO",
            timestamp=float(i) + 0.5,
        ))
    return trades


def test_vpin_balanced_trading():
    """Balanced YES/NO volume should yield low VPIN (near 0)."""
    analyzer = MicrostructureAnalyzer(n_buckets=10)
    trades = make_trades(yes_vol=100.0, no_vol=100.0, n=50)
    analyzer.add_trades(trades)
    result = analyzer.compute_vpin()
    assert result is not None
    assert result.vpin < 0.2   # Near-balanced → low VPIN


def test_vpin_one_sided_trading():
    """All-YES volume should yield high VPIN."""
    analyzer = MicrostructureAnalyzer(n_buckets=10)
    # All trades are YES-initiated
    trades = []
    for i in range(200):
        trades.append(Trade(market_id="test", price=0.6, size=1.0, side="YES", timestamp=float(i)))
    analyzer.add_trades(trades)
    result = analyzer.compute_vpin()
    assert result is not None
    assert result.vpin > 0.8   # Fully one-sided → high VPIN


def test_vpin_returns_none_insufficient_data():
    """VPIN should return None if not enough trades."""
    analyzer = MicrostructureAnalyzer(n_buckets=50)
    trades = [Trade(market_id="t", price=0.5, size=1.0, side="YES", timestamp=float(i)) for i in range(5)]
    analyzer.add_trades(trades)
    result = analyzer.compute_vpin()
    assert result is None


def test_vpin_bullish_signal_with_yes_flow():
    """YES-heavy order flow + high VPIN → bullish signal."""
    analyzer = MicrostructureAnalyzer(n_buckets=10)
    # More YES volume than NO
    trades = []
    for i in range(300):
        trades.append(Trade(market_id="t", price=0.6, size=3.0, side="YES", timestamp=float(i)))
    for i in range(100):
        trades.append(Trade(market_id="t", price=0.4, size=1.0, side="NO", timestamp=float(i) + 0.5))
    analyzer.add_trades(trades)
    result = analyzer.compute_vpin()
    assert result is not None
    assert result.order_flow_imbalance > 0
    assert result.signal == "bullish"


def test_vpin_bearish_signal_with_no_flow():
    """NO-heavy order flow + high VPIN → bearish signal."""
    analyzer = MicrostructureAnalyzer(n_buckets=10)
    trades = []
    for i in range(100):
        trades.append(Trade(market_id="t", price=0.6, size=1.0, side="YES", timestamp=float(i)))
    for i in range(300):
        trades.append(Trade(market_id="t", price=0.4, size=3.0, side="NO", timestamp=float(i) + 0.5))
    analyzer.add_trades(trades)
    result = analyzer.compute_vpin()
    assert result is not None
    assert result.order_flow_imbalance < 0
    assert result.signal == "bearish"


def test_vpin_likelihood_ratio_neutral_when_low_vpin():
    """Low VPIN (< 0.3) should yield LR ≈ 1.0 (no signal)."""
    lr = _vpin_to_likelihood_ratio(vpin=0.1, ofi=0.5)
    assert lr == pytest.approx(1.0, abs=0.01)


def test_vpin_likelihood_ratio_positive_with_yes_flow():
    """High VPIN + positive OFI → LR > 1."""
    lr = _vpin_to_likelihood_ratio(vpin=0.6, ofi=0.5)
    assert lr > 1.0


def test_vpin_likelihood_ratio_negative_with_no_flow():
    """High VPIN + negative OFI → LR < 1."""
    lr = _vpin_to_likelihood_ratio(vpin=0.6, ofi=-0.5)
    assert lr < 1.0


def test_vpin_lr_symmetric():
    """Equal and opposite OFI should yield reciprocal LRs."""
    lr_pos = _vpin_to_likelihood_ratio(vpin=0.5, ofi=0.5)
    lr_neg = _vpin_to_likelihood_ratio(vpin=0.5, ofi=-0.5)
    assert lr_pos * lr_neg == pytest.approx(1.0, abs=0.01)


def test_spread_lr_neutral_depth():
    """Equal depth on both sides → LR close to 1."""
    lr = _spread_to_likelihood_ratio(depth_imbalance=0.0, spread_pct=0.01)
    assert lr == pytest.approx(1.0, abs=0.05)


def test_spread_lr_bounded():
    """Spread LR should stay within [0.5, 2.0]."""
    for imbalance in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        for spread in [0.001, 0.01, 0.1]:
            lr = _spread_to_likelihood_ratio(imbalance, spread)
            assert 0.5 <= lr <= 2.0


def test_vpin_informed_property():
    """is_informed should be True when VPIN > 0.4."""
    result_high = VPINResult(
        vpin=0.5, order_flow_imbalance=0.3, n_buckets_used=10,
        total_volume=100, yes_volume=65, no_volume=35,
        signal="bullish", likelihood_ratio=1.5
    )
    result_low = VPINResult(
        vpin=0.2, order_flow_imbalance=0.1, n_buckets_used=10,
        total_volume=100, yes_volume=55, no_volume=45,
        signal="neutral", likelihood_ratio=1.0
    )
    assert result_high.is_informed is True
    assert result_low.is_informed is False
