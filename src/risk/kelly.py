"""
Kelly Criterion position sizing.

The Kelly formula maximizes long-run geometric growth rate.
We use fractional Kelly (0.25x) to reduce variance and drawdowns.

Full Kelly is theoretically optimal but requires exact probability estimates.
Since our estimates have uncertainty, fractional Kelly is safer.

Kelly formula: f* = (b*p - q) / b
where:
  b = net odds (payout per unit bet)
  p = our estimated probability of winning
  q = 1 - p
  f* = optimal fraction of bankroll to bet
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class KellyResult:
    kelly_fraction: float       # f* (full Kelly)
    fractional_kelly: float     # f* * kelly_factor
    position_size_usd: float    # dollar amount to bet
    direction: str              # "YES" or "NO"
    edge: float                 # posterior - market_price
    b_odds: float               # payout odds
    expected_value: float       # EV of the bet
    max_loss: float             # maximum loss (= position_size)
    capped: bool                # True if position was capped by risk limit

    @property
    def is_positive(self) -> bool:
        return self.fractional_kelly > 0

    def describe(self) -> str:
        return (
            f"Direction: {self.direction} | "
            f"Edge: {self.edge:+.3f} | "
            f"Kelly: {self.kelly_fraction:.4f} | "
            f"Fractional ({self.fractional_kelly:.4f}) → "
            f"${self.position_size_usd:.2f} | "
            f"EV: {self.expected_value:.4f}"
        )


def compute_kelly(
    posterior_prob: float,
    market_price_yes: float,
    portfolio_value: float,
    kelly_fraction: float = 0.25,
    max_position_pct: float = 0.05,
    max_position_usd: float = 50.0,
    fee: float = 0.02,
) -> KellyResult | None:
    """
    Compute Kelly position size for a Polymarket trade.

    On Polymarket:
    - Buying YES at price p: win (1-p)/p per unit if YES, lose 1 if NO
    - Buying NO at price (1-p): win p/(1-p) per unit if NO, lose 1 if YES

    Parameters:
        posterior_prob: Our estimated P(YES)
        market_price_yes: Current market P(YES) price
        portfolio_value: Total portfolio value in USD
        kelly_fraction: Fraction of full Kelly (default: 0.25)
        max_position_pct: Maximum position as fraction of portfolio
        max_position_usd: Maximum position in dollars
        fee: Polymarket fee on profits
    """
    edge = posterior_prob - market_price_yes

    if abs(edge) < fee:
        return None   # No edge after fees

    if edge > 0:
        # YES trade: buy YES at market_price_yes
        # Gross payout: (1 - p_market) / p_market per dollar risked
        # Net payout: gross * (1 - fee)  [fee is % of profit]
        direction = "YES"
        p = posterior_prob
        q = 1 - p
        b = (1 - market_price_yes) / market_price_yes
        b_net = b * (1 - fee)

    else:
        # NO trade: buy NO at (1 - market_price_yes)
        direction = "NO"
        p = 1 - posterior_prob
        q = 1 - p
        market_price_no = 1 - market_price_yes
        b = market_price_yes / market_price_no
        b_net = b * (1 - fee)

    if b_net <= 0:
        return None

    # Kelly formula: f* = (b*p - q) / b
    kelly_f = (b_net * p - q) / b_net
    kelly_f = max(0.0, kelly_f)

    if kelly_f == 0.0:
        return None

    # Fractional Kelly
    frac_kelly = kelly_f * kelly_fraction

    # Position size (cap at both percentage and absolute limits)
    position_size = portfolio_value * frac_kelly
    max_by_pct = portfolio_value * max_position_pct
    max_size = min(max_by_pct, max_position_usd)
    capped = position_size > max_size
    position_size = min(position_size, max_size)

    # Expected value of the bet
    ev = p * b_net - q

    return KellyResult(
        kelly_fraction=kelly_f,
        fractional_kelly=frac_kelly,
        position_size_usd=position_size,
        direction=direction,
        edge=edge,
        b_odds=b,
        expected_value=ev,
        max_loss=position_size,
        capped=capped,
    )


def kelly_for_multiple_bets(
    bets: list[tuple[float, float, float]],   # (posterior_p, market_price, portfolio_weight)
    portfolio_value: float,
    kelly_fraction: float = 0.25,
) -> list[KellyResult | None]:
    """
    Compute Kelly sizing for a portfolio of simultaneous bets.
    Applies an additional diversification discount.
    """
    n = len(bets)
    diversification_discount = 1.0 / max(1.0, math.sqrt(n))

    results = []
    for posterior_p, market_price, _ in bets:
        result = compute_kelly(
            posterior_prob=posterior_p,
            market_price_yes=market_price,
            portfolio_value=portfolio_value,
            kelly_fraction=kelly_fraction * diversification_discount,
        )
        results.append(result)

    return results
