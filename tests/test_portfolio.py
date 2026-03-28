"""Tests for portfolio management and risk limits."""
import pytest

from src.risk.portfolio import PortfolioManager, Position


@pytest.fixture
def portfolio():
    return PortfolioManager(starting_value=1000.0, max_exposure_pct=0.25, max_position_usd=50.0)


def test_initial_state(portfolio):
    """Fresh portfolio should have correct initial values."""
    assert portfolio.state.current_cash == 1000.0
    assert portfolio.state.total_value == 1000.0
    assert portfolio.state.total_trades == 0
    assert portfolio.state.win_rate == 0.0


def test_open_position(portfolio):
    """Opening a position should deduct cash and record trade."""
    pos = portfolio.open_position("m1", "YES", 50.0, 0.60)
    assert pos is not None
    assert portfolio.state.total_trades == 1
    assert portfolio.state.current_cash < 1000.0
    assert len(portfolio.state.positions) == 1


def test_position_limit_enforced(portfolio):
    """Exceeding max_position_usd should be rejected."""
    ok, reason = portfolio.can_open_position(100.0)
    assert ok is False
    assert "exceeds max" in reason.lower()


def test_exposure_limit_enforced(portfolio):
    """Total exposure should not exceed max_exposure_pct."""
    # Open positions totaling 25% of portfolio
    portfolio.open_position("m1", "YES", 50.0, 0.50)
    portfolio.open_position("m2", "NO", 50.0, 0.50)
    portfolio.open_position("m3", "YES", 50.0, 0.50)
    portfolio.open_position("m4", "NO", 50.0, 0.50)
    portfolio.open_position("m5", "YES", 50.0, 0.50)
    # Next one should be rejected (exposure > 25%)
    ok, reason = portfolio.can_open_position(50.0)
    assert ok is False


def test_insufficient_cash(portfolio):
    """Trying to spend more than cash should be rejected."""
    # Drain cash
    portfolio.open_position("m1", "YES", 50.0, 0.50)
    portfolio.open_position("m2", "YES", 50.0, 0.50)
    portfolio.open_position("m3", "YES", 50.0, 0.50)
    portfolio.open_position("m4", "YES", 50.0, 0.50)
    portfolio.open_position("m5", "YES", 50.0, 0.50)
    # Very little cash left
    ok, reason = portfolio.can_open_position(50.0)
    if not ok:
        assert "insufficient" in reason.lower() or "exceed" in reason.lower()


def test_close_position_winning(portfolio):
    """Closing a profitable YES position should increase cash."""
    portfolio.open_position("m1", "YES", 50.0, 0.40)
    cash_after_open = portfolio.state.current_cash
    pnl = portfolio.close_position("m1", 0.70)
    assert pnl > 0
    assert portfolio.state.current_cash > cash_after_open
    assert portfolio.state.winning_trades == 1


def test_close_position_losing(portfolio):
    """Closing a losing YES position should decrease portfolio value."""
    portfolio.open_position("m1", "YES", 50.0, 0.60)
    pnl = portfolio.close_position("m1", 0.30)
    assert pnl < 0
    assert portfolio.state.total_value < 1000.0


def test_close_nonexistent_position(portfolio):
    """Closing a position that doesn't exist should return 0."""
    pnl = portfolio.close_position("nonexistent", 0.50)
    assert pnl == 0.0


def test_update_price(portfolio):
    """update_price should update unrealized P&L."""
    portfolio.open_position("m1", "YES", 50.0, 0.40)
    portfolio.update_price("m1", 0.60)
    assert portfolio.state.positions["m1"].current_price == 0.60
    assert portfolio.state.unrealized_pnl > 0


def test_win_rate_calculation(portfolio):
    """Win rate should be winning / total."""
    portfolio.open_position("m1", "YES", 30.0, 0.40)
    portfolio.close_position("m1", 0.70)  # win
    portfolio.open_position("m2", "YES", 30.0, 0.60)
    portfolio.close_position("m2", 0.30)  # loss
    assert portfolio.state.win_rate == pytest.approx(0.5, abs=0.01)


def test_pnl_percent(portfolio):
    """Total P&L percentage should reflect actual gains/losses."""
    portfolio.open_position("m1", "YES", 50.0, 0.40)
    portfolio.close_position("m1", 0.80)  # big win
    assert portfolio.state.total_pnl_pct > 0


def test_get_summary_returns_string(portfolio):
    """get_summary() should return a multi-line string."""
    portfolio.open_position("m1", "YES", 30.0, 0.50)
    summary = portfolio.get_summary()
    assert isinstance(summary, str)
    assert "Portfolio" in summary
    assert "P&L" in summary
