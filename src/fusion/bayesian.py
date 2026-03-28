"""
Bayesian Multi-Signal Fusion Engine.

Core mathematical framework:

Prior: current Polymarket price (crowd wisdom as starting point)
Each signal updates via likelihood ratio (not raw scores).

posterior_odds = prior_odds × L_news × L_social × L_microstructure × L_cross_market × L_llm
posterior_prob = posterior_odds / (1 + posterior_odds)
edge = posterior_prob - prior_prob

This is strictly correct Bayesian inference under the assumption of
conditional independence between signals. In practice signals are
correlated, so we apply a damping factor to prevent overconfidence.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Literal

from loguru import logger


SignalSource = Literal[
    "news_rss",
    "news_gdelt",
    "microstructure_vpin",
    "microstructure_spread",
    "cross_market",
    "llm_decomposition",
    "reddit_social",
    "wikipedia_velocity",
    "resolution_source",
]


@dataclass
class SignalUpdate:
    source: SignalSource
    likelihood_ratio: float     # L > 1 = evidence for YES, L < 1 = evidence for NO
    confidence: float           # 0.0–1.0 (how much we trust this signal)
    raw_value: float            # Original signal value (e.g., sentiment score, VPIN)
    notes: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def effective_lr(self) -> float:
        """Dampen LR toward 1.0 based on confidence and signal age."""
        base = self.likelihood_ratio
        if base >= 1.0:
            dampened = 1.0 + (base - 1.0) * self.confidence
        else:
            dampened = 1.0 - (1.0 - base) * self.confidence

        # Exponential time decay: half-life of 30 minutes
        age_s = max(0, time.time() - self.timestamp)
        half_life = 1800  # 30 minutes
        decay = 2 ** (-age_s / half_life)
        # Decay pulls LR toward 1.0 (neutral)
        return 1.0 + (dampened - 1.0) * decay


@dataclass
class BayesianResult:
    market_id: str
    prior_prob: float
    posterior_prob: float
    posterior_odds: float
    edge: float                           # posterior - prior (positive = YES edge)
    effective_edge: float                 # edge after fee deduction
    signals: list[SignalUpdate]
    confidence_interval: tuple[float, float]
    trade_direction: Literal["YES", "NO", "NONE"]
    reasoning: str

    @property
    def has_edge(self) -> bool:
        return abs(self.effective_edge) > 0

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    def describe(self) -> str:
        lines = [
            f"Market: {self.market_id}",
            f"Prior: {self.prior_prob:.3f} → Posterior: {self.posterior_prob:.3f}",
            f"Edge: {self.edge:+.3f} | Effective edge: {self.effective_edge:+.3f}",
            f"Trade: {self.trade_direction}",
            f"CI: [{self.confidence_interval[0]:.3f}, {self.confidence_interval[1]:.3f}]",
            "",
            "Signals:",
        ]
        for sig in self.signals:
            direction = "YES" if sig.likelihood_ratio > 1 else "NO"
            lines.append(
                f"  [{sig.source}] LR={sig.likelihood_ratio:.3f} "
                f"(eff={sig.effective_lr:.3f}) → {direction} | {sig.notes}"
            )
        return "\n".join(lines)


class BayesianFusion:
    """
    Fuses multiple signals into a calibrated posterior probability.

    Key design choices:
    - Uses multiplicative Bayesian updating (log-odds space)
    - Signals treated as conditionally independent (with damping for correlation)
    - Correlation damping: multiply each LR by CORRELATION_DAMPING before combining
    - CI computed from signal variance
    """

    POLYMARKET_FEE = 0.02       # 2% fee on profits
    MIN_EDGE = 0.02             # 2% minimum effective edge after fees
    MIN_SIGNALS = 2             # require at least 2 independent signals to trade

    # Correlation groups: signals within a group share information and get
    # heavier damping when combined.  Signals across groups are more
    # independent and keep more of their weight.
    CORRELATION_GROUPS: dict[str, list[str]] = {
        "news":           ["news_rss", "news_gdelt"],
        "microstructure": ["microstructure_vpin", "microstructure_spread"],
        "reasoning":      ["llm_decomposition"],
        "cross_market":   ["cross_market"],
        "alternative":    ["wikipedia_velocity", "resolution_source"],
    }
    # Damping applied to 2nd, 3rd, ... signal within the same correlation group
    INTRA_GROUP_DAMPING = 0.40
    # Damping applied to each signal across groups (mild — they're mostly independent)
    INTER_GROUP_DAMPING = 0.90

    def fuse(
        self,
        market_id: str,
        prior_prob: float,
        signals: list[SignalUpdate],
        min_edge_threshold: float | None = None,
    ) -> BayesianResult:
        """
        Perform Bayesian fusion of all signals.

        Algorithm:
        1. Convert prior to log-odds
        2. For each signal: add log(LR) to log-odds (multiplicative in odds space)
        3. Apply correlation damping
        4. Convert back to probability
        5. Compute edge and CI
        """
        min_edge = min_edge_threshold if min_edge_threshold is not None else self.MIN_EDGE

        # Clip prior to avoid log(0)
        prior = max(0.01, min(0.99, prior_prob))
        prior_log_odds = math.log(prior / (1 - prior))

        # Accumulate log-likelihood ratios with structured correlation damping.
        # Within a correlation group the 1st signal keeps full weight but each
        # additional signal in the same group is heavily damped (they share
        # information).  Across groups we apply only mild damping.
        log_lr_sum = 0.0
        group_counts: dict[str, int] = {}

        # Build a reverse lookup: source -> group name
        source_to_group: dict[str, str] = {}
        for gname, sources in self.CORRELATION_GROUPS.items():
            for src in sources:
                source_to_group[src] = gname

        for signal in signals:
            eff_lr = max(0.01, signal.effective_lr)   # never take log(0)
            log_lr = math.log(eff_lr)

            # Determine damping based on correlation group
            group = source_to_group.get(signal.source, signal.source)
            group_counts[group] = group_counts.get(group, 0) + 1

            if group_counts[group] > 1:
                # 2nd+ signal in same group: heavy damping
                damping = self.INTRA_GROUP_DAMPING
            else:
                # First signal in group: mild cross-group damping
                damping = self.INTER_GROUP_DAMPING

            log_lr_sum += log_lr * damping

        posterior_log_odds = prior_log_odds + log_lr_sum

        # Clamp log-odds to prevent math.exp overflow (>709 → OverflowError
        # or inf → NaN when dividing inf/inf).
        posterior_log_odds = max(-20.0, min(20.0, posterior_log_odds))

        posterior_odds = math.exp(posterior_log_odds)
        posterior_prob = posterior_odds / (1 + posterior_odds)
        posterior_prob = max(0.01, min(0.99, posterior_prob))

        edge = posterior_prob - prior
        effective_edge = abs(edge) - self.POLYMARKET_FEE

        # Confidence interval from signal uncertainty
        ci = self._compute_ci(posterior_prob, signals)

        # Trade direction — require both edge AND minimum signal count
        if effective_edge >= min_edge and len(signals) >= self.MIN_SIGNALS:
            trade_direction: Literal["YES", "NO", "NONE"] = "YES" if edge > 0 else "NO"
        else:
            trade_direction = "NONE"

        reasoning = self._build_reasoning(prior, posterior_prob, edge, effective_edge, signals)

        return BayesianResult(
            market_id=market_id,
            prior_prob=prior,
            posterior_prob=posterior_prob,
            posterior_odds=posterior_odds,
            edge=edge,
            effective_edge=effective_edge,
            signals=signals,
            confidence_interval=ci,
            trade_direction=trade_direction,
            reasoning=reasoning,
        )

    def _compute_ci(
        self,
        posterior: float,
        signals: list[SignalUpdate],
    ) -> tuple[float, float]:
        """
        Compute 90% confidence interval using signal disagreement as variance proxy.

        When signals strongly agree → narrow CI
        When signals disagree → wide CI
        """
        if not signals:
            return (max(0.02, posterior - 0.15), min(0.98, posterior + 0.15))

        # Variance from LR disagreement
        log_lrs = [math.log(max(0.01, s.effective_lr)) for s in signals]
        if len(log_lrs) > 1:
            mean_log_lr = sum(log_lrs) / len(log_lrs)
            variance = sum((x - mean_log_lr) ** 2 for x in log_lrs) / len(log_lrs)
            std = math.sqrt(variance)
        else:
            std = 0.1

        # Map log-odds std to probability std (approximation around posterior)
        prob_std = posterior * (1 - posterior) * std

        # 90% CI ≈ ±1.645 std
        half_width = 1.645 * max(prob_std, 0.02)

        lower = max(0.02, posterior - half_width)
        upper = min(0.98, posterior + half_width)
        return (lower, upper)

    def _build_reasoning(
        self,
        prior: float,
        posterior: float,
        edge: float,
        effective_edge: float,
        signals: list[SignalUpdate],
    ) -> str:
        direction = "YES" if edge > 0 else "NO"
        strong = [s for s in signals if abs(math.log(max(0.01, s.effective_lr))) > 0.3]
        strong_str = ", ".join(s.source for s in strong[:3]) if strong else "no dominant signals"

        return (
            f"Prior: {prior:.3f} → Posterior: {posterior:.3f} | "
            f"Edge: {edge:+.3f} ({direction}) | Eff edge: {effective_edge:+.3f} | "
            f"Strong signals: {strong_str}"
        )


def compute_news_lr(
    relevance: float,
    sentiment: float,
    confidence: float = 0.7,
) -> float:
    """
    Convenience function: convert news signal to likelihood ratio.
    Used when building SignalUpdate objects.
    """
    if relevance < 0.15:
        return 1.0
    k = 1.2
    return max(0.5, min(2.0, math.exp(sentiment * relevance * confidence * k)))


def prob_to_log_odds(p: float) -> float:
    p = max(0.001, min(0.999, p))
    return math.log(p / (1 - p))


def log_odds_to_prob(lo: float) -> float:
    return 1.0 / (1.0 + math.exp(-lo))
