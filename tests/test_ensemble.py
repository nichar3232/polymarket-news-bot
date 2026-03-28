"""Tests for ensemble aggregator — signal bundling and Bayesian fusion integration."""
import pytest

from src.fusion.bayesian import BayesianFusion
from src.fusion.ensemble import EnsembleAggregator, MarketSignalBundle
from src.signals.microstructure import VPINResult, SpreadSignal
from src.signals.cross_market import CrossMarketSignal
from src.signals.news_relevance import NewsRelevanceScore


@pytest.fixture
def aggregator():
    return EnsembleAggregator(BayesianFusion())


def test_empty_bundle_returns_prior(aggregator):
    """No signals → posterior should equal prior."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.40)
    result = aggregator.aggregate(bundle)
    assert result.posterior_prob == pytest.approx(0.40, abs=0.02)
    assert result.trade_direction == "NONE"


def test_vpin_signal_included(aggregator):
    """VPIN signal with LR != 1.0 should shift the posterior."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.vpin = VPINResult(
        vpin=0.55, order_flow_imbalance=0.4, n_buckets_used=50,
        total_volume=1000, yes_volume=700, no_volume=300,
        signal="bullish", likelihood_ratio=1.8,
    )
    result = aggregator.aggregate(bundle)
    assert result.posterior_prob > 0.50


def test_cross_market_signal_included(aggregator):
    """Cross-market divergence should shift the posterior."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.cross_market = CrossMarketSignal(
        polymarket_price=0.50,
        kalshi_price=0.35,
        metaculus_prob=0.30,
        manifold_prob=None,
        disagreement_magnitude=0.175,
        consensus_direction=-1,
        n_sources_agree=2,
        likelihood_ratio=0.55,
        notes="test",
    )
    result = aggregator.aggregate(bundle)
    assert result.posterior_prob < 0.50


def test_news_scores_aggregated(aggregator):
    """Multiple relevant news articles should be aggregated into one signal."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.news_scores = [
        NewsRelevanceScore(raw_relevance=0.6, sentiment=0.5, sentiment_confidence=0.7,
                           uncertainty_flag=False, likelihood_ratio=1.4),
        NewsRelevanceScore(raw_relevance=0.8, sentiment=0.4, sentiment_confidence=0.6,
                           uncertainty_flag=False, likelihood_ratio=1.3),
    ]
    result = aggregator.aggregate(bundle)
    assert result.posterior_prob > 0.50
    # Should produce exactly 1 aggregated news signal
    news_signals = [s for s in result.signals if s.source == "news_rss"]
    assert len(news_signals) == 1


def test_low_relevance_news_filtered(aggregator):
    """News with relevance below 0.15 should be filtered out."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.news_scores = [
        NewsRelevanceScore(raw_relevance=0.05, sentiment=0.9, sentiment_confidence=0.9,
                           uncertainty_flag=False, likelihood_ratio=1.8),
    ]
    result = aggregator.aggregate(bundle)
    assert result.posterior_prob == pytest.approx(0.50, abs=0.02)


def test_reddit_signal_included(aggregator):
    """Non-zero Reddit sentiment should produce a signal."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.reddit_sentiment = 0.6
    result = aggregator.aggregate(bundle)
    reddit_sigs = [s for s in result.signals if s.source == "reddit_social"]
    assert len(reddit_sigs) == 1
    assert reddit_sigs[0].confidence == 0.35


def test_wikipedia_spike_included(aggregator):
    """Wikipedia velocity LR != 1.0 should produce a signal."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.wikipedia_velocity_lr = 1.3
    result = aggregator.aggregate(bundle)
    wiki_sigs = [s for s in result.signals if s.source == "wikipedia_velocity"]
    assert len(wiki_sigs) == 1


def test_multiple_signals_compound(aggregator):
    """Multiple agreeing signals should move the posterior more than one."""
    single = MarketSignalBundle(market_id="m1", prior_price=0.50)
    single.vpin = VPINResult(
        vpin=0.55, order_flow_imbalance=0.3, n_buckets_used=50,
        total_volume=1000, yes_volume=650, no_volume=350,
        signal="bullish", likelihood_ratio=1.5,
    )

    multi = MarketSignalBundle(market_id="m2", prior_price=0.50)
    multi.vpin = VPINResult(
        vpin=0.55, order_flow_imbalance=0.3, n_buckets_used=50,
        total_volume=1000, yes_volume=650, no_volume=350,
        signal="bullish", likelihood_ratio=1.5,
    )
    multi.cross_market = CrossMarketSignal(
        polymarket_price=0.50, kalshi_price=0.65, metaculus_prob=0.62,
        manifold_prob=None, disagreement_magnitude=0.14,
        consensus_direction=1, n_sources_agree=2, likelihood_ratio=1.6,
    )

    r_single = aggregator.aggregate(single)
    r_multi = aggregator.aggregate(multi)
    assert r_multi.posterior_prob > r_single.posterior_prob


def test_neutral_vpin_excluded(aggregator):
    """VPIN with LR = 1.0 should not create a signal."""
    bundle = MarketSignalBundle(market_id="m1", prior_price=0.50)
    bundle.vpin = VPINResult(
        vpin=0.20, order_flow_imbalance=0.01, n_buckets_used=50,
        total_volume=1000, yes_volume=510, no_volume=490,
        signal="neutral", likelihood_ratio=1.0,
    )
    result = aggregator.aggregate(bundle)
    vpin_sigs = [s for s in result.signals if s.source == "microstructure_vpin"]
    assert len(vpin_sigs) == 0
