"""Tests for cross-market arbitrage signal."""
import math
import pytest

from src.signals.cross_market import CrossMarketAnalyzer, _cross_market_lr


@pytest.fixture
def analyzer():
    return CrossMarketAnalyzer()


def test_no_alternative_data_returns_neutral(analyzer):
    """No alternative prices → LR = 1.0 (no update)."""
    signal = analyzer.compute_signal(polymarket_price=0.50)
    assert signal.likelihood_ratio == pytest.approx(1.0, abs=0.01)
    assert signal.n_sources_agree == 0


def test_single_source_above_threshold(analyzer):
    """Single source with large delta should produce a mild signal."""
    signal = analyzer.compute_signal(
        polymarket_price=0.50,
        kalshi_price=0.70,
    )
    # Single source, large divergence → weak but non-neutral
    assert signal.n_sources_agree >= 1
    assert signal.likelihood_ratio != 1.0


def test_two_sources_agreeing_stronger_than_one(analyzer):
    """Two agreeing sources should produce a stronger signal than one."""
    single = analyzer.compute_signal(
        polymarket_price=0.50,
        kalshi_price=0.65,
    )
    double = analyzer.compute_signal(
        polymarket_price=0.50,
        kalshi_price=0.65,
        metaculus_prob=0.68,
    )
    # Both say YES > PM → stronger consensus
    assert abs(math.log(double.likelihood_ratio)) >= abs(math.log(single.likelihood_ratio))


def test_three_sources_consensus(analyzer):
    """Three sources all saying NO → strong bearish signal."""
    signal = analyzer.compute_signal(
        polymarket_price=0.50,
        kalshi_price=0.30,
        metaculus_prob=0.25,
        manifold_prob=0.28,
    )
    assert signal.n_sources_agree == 3
    assert signal.consensus_direction == -1
    assert signal.likelihood_ratio < 1.0


def test_mixed_signals_cancel(analyzer):
    """Sources disagreeing should produce near-neutral signal."""
    signal = analyzer.compute_signal(
        polymarket_price=0.50,
        kalshi_price=0.65,     # above PM
        metaculus_prob=0.35,   # below PM
    )
    # Mixed: one above, one below — no consensus
    assert signal.likelihood_ratio == pytest.approx(1.0, abs=0.3)


def test_small_divergence_ignored(analyzer):
    """Divergence below MIN_DIVERGENCE threshold should be neutral."""
    signal = analyzer.compute_signal(
        polymarket_price=0.50,
        kalshi_price=0.52,
        metaculus_prob=0.53,
    )
    # Tiny deltas below 8% threshold
    assert signal.likelihood_ratio == pytest.approx(1.0, abs=0.05)


def test_cross_market_lr_bounded():
    """LR should stay within [0.5, 2.5]."""
    for mag in [0.0, 0.1, 0.2, 0.5, 1.0]:
        for n in [1, 2, 3]:
            for d in [-1, 1]:
                lr = _cross_market_lr(mag, n, d)
                assert 0.5 <= lr <= 2.5


def test_notes_contain_prices(analyzer):
    """Notes string should include all provided prices."""
    signal = analyzer.compute_signal(
        polymarket_price=0.40,
        kalshi_price=0.55,
        manifold_prob=0.60,
    )
    assert "PM=" in signal.notes
    assert "Kalshi=" in signal.notes
    assert "Manifold=" in signal.notes
