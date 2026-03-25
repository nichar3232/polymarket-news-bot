"""Tests for Kelly criterion position sizing."""
import pytest

from src.risk.kelly import compute_kelly, KellyResult


def test_no_edge_returns_none():
    """When posterior == market price, there's no edge → None."""
    result = compute_kelly(
        posterior_prob=0.50,
        market_price_yes=0.50,
        portfolio_value=1000.0,
    )
    assert result is None


def test_positive_yes_edge():
    """Posterior > market price → YES trade with positive fraction."""
    result = compute_kelly(
        posterior_prob=0.65,
        market_price_yes=0.50,
        portfolio_value=1000.0,
        kelly_fraction=0.25,
        max_position_usd=100.0,
    )
    assert result is not None
    assert result.direction == "YES"
    assert result.kelly_fraction > 0
    assert result.fractional_kelly > 0
    assert result.position_size_usd > 0


def test_negative_edge_yields_no_trade():
    """Posterior < market price → NO trade."""
    result = compute_kelly(
        posterior_prob=0.30,
        market_price_yes=0.50,
        portfolio_value=1000.0,
    )
    assert result is not None
    assert result.direction == "NO"


def test_kelly_fraction_applied():
    """Fractional Kelly must be exactly kelly_f * fraction."""
    result = compute_kelly(
        posterior_prob=0.70,
        market_price_yes=0.50,
        portfolio_value=1000.0,
        kelly_fraction=0.25,
        max_position_usd=10_000.0,
        max_position_pct=1.0,
    )
    assert result is not None
    assert result.fractional_kelly == pytest.approx(result.kelly_fraction * 0.25, abs=0.0001)


def test_position_capped_by_usd_limit():
    """Position size should not exceed max_position_usd."""
    result = compute_kelly(
        posterior_prob=0.80,
        market_price_yes=0.40,
        portfolio_value=10_000.0,
        kelly_fraction=0.5,
        max_position_pct=0.50,
        max_position_usd=50.0,
    )
    assert result is not None
    assert result.position_size_usd <= 50.0
    assert result.capped is True


def test_position_capped_by_pct_limit():
    """Position size should not exceed max_position_pct of portfolio."""
    portfolio = 1000.0
    max_pct = 0.05
    result = compute_kelly(
        posterior_prob=0.80,
        market_price_yes=0.40,
        portfolio_value=portfolio,
        kelly_fraction=0.5,
        max_position_pct=max_pct,
        max_position_usd=10_000.0,   # huge, so pct is binding
    )
    assert result is not None
    assert result.position_size_usd <= portfolio * max_pct + 0.01


def test_kelly_never_negative():
    """Kelly fraction should never be negative (no shorting)."""
    for market_price in [0.1, 0.3, 0.5, 0.7, 0.9]:
        # Even if posterior == market price (no edge), should return None or 0
        result = compute_kelly(
            posterior_prob=market_price,
            market_price_yes=market_price,
            portfolio_value=1000.0,
        )
        if result is not None:
            assert result.kelly_fraction >= 0
            assert result.fractional_kelly >= 0


def test_edge_just_above_fee_is_tradeable():
    """An edge just above the fee threshold should still generate a trade."""
    fee = 0.02
    edge = 0.025   # Just above fee
    posterior = 0.50 + edge
    result = compute_kelly(
        posterior_prob=posterior,
        market_price_yes=0.50,
        portfolio_value=1000.0,
        kelly_fraction=0.25,
        max_position_usd=100.0,
    )
    # Should trade since edge > fee
    assert result is not None


def test_edge_below_fee_not_tradeable():
    """An edge below the fee threshold should not generate a trade."""
    fee = 0.02
    edge = 0.01   # Below fee
    posterior = 0.50 + edge
    result = compute_kelly(
        posterior_prob=posterior,
        market_price_yes=0.50,
        portfolio_value=1000.0,
        fee=fee,
    )
    # abs(edge) = 0.01 < fee = 0.02 → no trade
    assert result is None


def test_kelly_result_describe():
    """KellyResult.describe() should return a non-empty string."""
    result = compute_kelly(
        posterior_prob=0.65,
        market_price_yes=0.50,
        portfolio_value=1000.0,
    )
    assert result is not None
    desc = result.describe()
    assert isinstance(desc, str)
    assert len(desc) > 0
    assert "YES" in desc or "NO" in desc


def test_high_probability_market():
    """Near-certain events should produce a trade, capped by risk limits."""
    result = compute_kelly(
        posterior_prob=0.98,   # We think it's near-certain
        market_price_yes=0.95,
        portfolio_value=1000.0,
        kelly_fraction=0.25,
        max_position_usd=50.0,   # hard cap keeps position reasonable
        max_position_pct=0.05,
    )
    assert result is not None
    assert result.direction == "YES"
    # Position is capped by risk limits regardless of raw Kelly
    assert result.position_size_usd <= 50.0
    # Fractional Kelly (raw × 0.25) is still a real bet
    assert result.fractional_kelly > 0
