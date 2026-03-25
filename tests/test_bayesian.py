"""Tests for Bayesian fusion engine."""
import math
import pytest

from src.fusion.bayesian import BayesianFusion, SignalUpdate, prob_to_log_odds, log_odds_to_prob


@pytest.fixture
def bayesian():
    return BayesianFusion()


def test_no_signals_returns_prior(bayesian):
    """With no signals, posterior should equal prior."""
    result = bayesian.fuse("market-1", prior_prob=0.40, signals=[])
    assert result.posterior_prob == pytest.approx(0.40, abs=0.01)
    assert result.edge == pytest.approx(0.0, abs=0.01)
    assert result.trade_direction == "NONE"


def test_bullish_signal_raises_posterior(bayesian):
    """A strong bullish signal should raise posterior above prior."""
    signals = [
        SignalUpdate(
            source="news_rss",
            likelihood_ratio=3.0,   # Strong YES evidence
            confidence=0.9,
            raw_value=0.8,
        )
    ]
    result = bayesian.fuse("market-1", prior_prob=0.40, signals=signals)
    assert result.posterior_prob > 0.40


def test_bearish_signal_lowers_posterior(bayesian):
    """A strong bearish signal should lower posterior below prior."""
    signals = [
        SignalUpdate(
            source="cross_market",
            likelihood_ratio=0.2,   # Strong NO evidence
            confidence=0.9,
            raw_value=0.1,
        )
    ]
    result = bayesian.fuse("market-1", prior_prob=0.50, signals=signals)
    assert result.posterior_prob < 0.50


def test_posterior_bounded(bayesian):
    """Posterior must stay in (0, 1)."""
    # Extremely strong signal
    signals = [
        SignalUpdate(source="microstructure_vpin", likelihood_ratio=100.0, confidence=1.0, raw_value=0.9)
    ]
    result = bayesian.fuse("market-1", prior_prob=0.50, signals=signals)
    assert 0.0 < result.posterior_prob < 1.0


def test_neutral_signal_no_change(bayesian):
    """LR=1.0 signal should not change posterior."""
    signals = [
        SignalUpdate(source="reddit_social", likelihood_ratio=1.0, confidence=0.5, raw_value=0.0)
    ]
    result = bayesian.fuse("market-1", prior_prob=0.30, signals=signals)
    assert result.posterior_prob == pytest.approx(0.30, abs=0.02)


def test_multiple_agreeing_signals_compound(bayesian):
    """Multiple signals in the same direction should compound."""
    single_signal = [
        SignalUpdate(source="news_rss", likelihood_ratio=2.0, confidence=0.8, raw_value=0.7)
    ]
    double_signals = [
        SignalUpdate(source="news_rss", likelihood_ratio=2.0, confidence=0.8, raw_value=0.7),
        SignalUpdate(source="cross_market", likelihood_ratio=2.0, confidence=0.8, raw_value=0.7),
    ]

    result_single = bayesian.fuse("m1", prior_prob=0.40, signals=single_signal)
    result_double = bayesian.fuse("m2", prior_prob=0.40, signals=double_signals)

    assert result_double.posterior_prob > result_single.posterior_prob


def test_opposing_signals_reduce_update(bayesian):
    """Opposing signals should partially cancel."""
    signals = [
        SignalUpdate(source="news_rss", likelihood_ratio=3.0, confidence=0.8, raw_value=0.8),
        SignalUpdate(source="cross_market", likelihood_ratio=0.33, confidence=0.8, raw_value=0.2),
    ]
    result = bayesian.fuse("market-1", prior_prob=0.40, signals=signals)
    # Should be close to prior since signals cancel
    assert abs(result.posterior_prob - 0.40) < 0.15


def test_edge_calculation(bayesian):
    """Edge should be posterior - prior."""
    signals = [
        SignalUpdate(source="llm_decomposition", likelihood_ratio=2.5, confidence=0.9, raw_value=0.65)
    ]
    result = bayesian.fuse("market-1", prior_prob=0.45, signals=signals)
    assert result.edge == pytest.approx(result.posterior_prob - 0.45, abs=0.001)


def test_effective_edge_subtracts_fee(bayesian):
    """Effective edge should be |edge| - fee."""
    signals = [
        SignalUpdate(source="news_rss", likelihood_ratio=2.0, confidence=0.9, raw_value=0.7)
    ]
    result = bayesian.fuse("market-1", prior_prob=0.40, signals=signals)
    expected_eff = abs(result.edge) - bayesian.POLYMARKET_FEE
    assert result.effective_edge == pytest.approx(expected_eff, abs=0.001)


def test_trade_direction_none_when_small_edge(bayesian):
    """Small edge should yield NONE trade direction."""
    signals = [
        SignalUpdate(source="reddit_social", likelihood_ratio=1.05, confidence=0.3, raw_value=0.1)
    ]
    result = bayesian.fuse("market-1", prior_prob=0.50, signals=signals)
    # Tiny signal, tiny edge — should not trade
    if abs(result.effective_edge) < bayesian.MIN_EDGE:
        assert result.trade_direction == "NONE"


def test_ci_wider_with_disagreeing_signals(bayesian):
    """Disagreeing signals should produce wider confidence interval."""
    agreeing = [
        SignalUpdate(source="news_rss", likelihood_ratio=2.0, confidence=0.8, raw_value=0.7),
        SignalUpdate(source="cross_market", likelihood_ratio=1.8, confidence=0.8, raw_value=0.65),
    ]
    disagreeing = [
        SignalUpdate(source="news_rss", likelihood_ratio=2.0, confidence=0.8, raw_value=0.7),
        SignalUpdate(source="cross_market", likelihood_ratio=0.5, confidence=0.8, raw_value=0.3),
    ]

    r_agree = bayesian.fuse("m1", prior_prob=0.45, signals=agreeing)
    r_disagree = bayesian.fuse("m2", prior_prob=0.45, signals=disagreeing)

    ci_width_agree = r_agree.confidence_interval[1] - r_agree.confidence_interval[0]
    ci_width_disagree = r_disagree.confidence_interval[1] - r_disagree.confidence_interval[0]

    assert ci_width_disagree >= ci_width_agree


def test_log_odds_roundtrip():
    """Log odds conversion should be invertible."""
    for p in [0.1, 0.25, 0.5, 0.75, 0.9]:
        lo = prob_to_log_odds(p)
        p_recovered = log_odds_to_prob(lo)
        assert p_recovered == pytest.approx(p, abs=0.001)


def test_signal_effective_lr_confidence_scaling():
    """Higher confidence should make effective LR closer to raw LR."""
    sig_high = SignalUpdate(source="news_rss", likelihood_ratio=3.0, confidence=1.0, raw_value=1.0)
    sig_low = SignalUpdate(source="news_rss", likelihood_ratio=3.0, confidence=0.3, raw_value=1.0)

    # High confidence: effective_lr should be close to 3.0
    assert sig_high.effective_lr == pytest.approx(3.0, abs=0.01)
    # Low confidence: effective_lr should be much closer to 1.0
    assert sig_low.effective_lr < sig_high.effective_lr
    assert sig_low.effective_lr < 2.0
