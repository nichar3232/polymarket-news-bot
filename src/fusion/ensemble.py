"""
Multi-signal ensemble aggregator.

Collects signals from all data sources, formats them as SignalUpdate objects,
and passes them to the Bayesian fusion engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from src.fusion.bayesian import BayesianFusion, BayesianResult, SignalUpdate

if TYPE_CHECKING:
    from src.signals.microstructure import VPINResult, SpreadSignal
    from src.signals.cross_market import CrossMarketSignal
    from src.signals.news_relevance import NewsRelevanceScore
    from src.signals.resolution import ResolutionSignal
    from src.reasoning.decomposer import DecompositionResult


@dataclass
class MarketSignalBundle:
    """All signals collected for a single market in one evaluation cycle."""
    market_id: str
    prior_price: float

    vpin: "VPINResult | None" = None
    spread: "SpreadSignal | None" = None
    cross_market: "CrossMarketSignal | None" = None
    news_scores: list["NewsRelevanceScore"] = field(default_factory=list)
    llm_decomposition: "DecompositionResult | None" = None
    resolution: "ResolutionSignal | None" = None
    reddit_sentiment: float = 0.0           # -1.0 to +1.0
    wikipedia_velocity_lr: float = 1.0


class EnsembleAggregator:
    """
    Converts raw signals into SignalUpdate list for the Bayesian engine.
    """

    def __init__(self, bayesian: BayesianFusion | None = None) -> None:
        self._bayesian = bayesian or BayesianFusion()

    def aggregate(self, bundle: MarketSignalBundle) -> BayesianResult:
        """Build signal list from bundle and run Bayesian fusion."""
        signals: list[SignalUpdate] = []

        # 1. VPIN microstructure signal
        if bundle.vpin is not None and bundle.vpin.likelihood_ratio != 1.0:
            signals.append(SignalUpdate(
                source="microstructure_vpin",
                likelihood_ratio=bundle.vpin.likelihood_ratio,
                confidence=0.7 if bundle.vpin.is_informed else 0.4,
                raw_value=bundle.vpin.vpin,
                notes=(
                    f"VPIN={bundle.vpin.vpin:.3f}, OFI={bundle.vpin.order_flow_imbalance:+.3f}, "
                    f"signal={bundle.vpin.signal}"
                ),
            ))

        # 2. Spread / depth signal
        if bundle.spread is not None and bundle.spread.likelihood_ratio != 1.0:
            signals.append(SignalUpdate(
                source="microstructure_spread",
                likelihood_ratio=bundle.spread.likelihood_ratio,
                confidence=0.5,
                raw_value=bundle.spread.depth_imbalance,
                notes=f"depth_imbalance={bundle.spread.depth_imbalance:+.3f}",
            ))

        # 3. Cross-market signal
        if bundle.cross_market is not None and bundle.cross_market.likelihood_ratio != 1.0:
            confidence = min(0.5 * bundle.cross_market.n_sources_agree, 0.9)
            signals.append(SignalUpdate(
                source="cross_market",
                likelihood_ratio=bundle.cross_market.likelihood_ratio,
                confidence=confidence,
                raw_value=bundle.cross_market.disagreement_magnitude,
                notes=bundle.cross_market.notes,
            ))

        # 4. News signals — aggregate multiple articles
        if bundle.news_scores:
            # Filter to meaningfully relevant articles
            relevant = [ns for ns in bundle.news_scores if ns.raw_relevance > 0.15]
            if relevant:
                log_lr_sum = sum(
                    math.log(max(0.01, ns.likelihood_ratio)) * ns.raw_relevance
                    for ns in relevant
                )
                weight_sum = sum(ns.raw_relevance for ns in relevant)
                if weight_sum > 0:
                    avg_log_lr = log_lr_sum / weight_sum
                    agg_lr = math.exp(avg_log_lr)
                    # Cap confidence lower — news sentiment is noisy
                    avg_confidence = min(weight_sum / 5.0, 0.60)
                    signals.append(SignalUpdate(
                        source="news_rss",
                        likelihood_ratio=agg_lr,
                        confidence=avg_confidence,
                        raw_value=weight_sum,
                        notes=f"Aggregated {len(relevant)} articles",
                    ))

        # 5. LLM decomposition
        if bundle.llm_decomposition is not None:
            decomp = bundle.llm_decomposition
            # Confidence from CI width: narrow CI = high confidence
            # Floor raised from 0.3 to 0.4 — wide-CI LLM outputs are noise
            ci_width = decomp.confidence_interval[1] - decomp.confidence_interval[0]
            confidence = max(0.4, 1.0 - ci_width * 2)
            # Cap LLM LR — LLMs are not calibrated forecasters
            capped_lr = max(0.5, min(2.0, decomp.likelihood_ratio))
            signals.append(SignalUpdate(
                source="llm_decomposition",
                likelihood_ratio=capped_lr,
                confidence=confidence,
                raw_value=decomp.blended_probability,
                notes=(
                    f"P(YES)={decomp.blended_probability:.3f}, "
                    f"CI=[{decomp.confidence_interval[0]:.3f},{decomp.confidence_interval[1]:.3f}], "
                    f"direction={decomp.update_direction}"
                ),
            ))

        # 6. Resolution source
        if bundle.resolution is not None and bundle.resolution.found_evidence:
            # likely_yes can be True, False, or None (direction unknown)
            raw_val = (
                1.0 if bundle.resolution.likely_yes is True
                else -1.0 if bundle.resolution.likely_yes is False
                else 0.0
            )
            signals.append(SignalUpdate(
                source="resolution_source",
                likelihood_ratio=bundle.resolution.likelihood_ratio,
                confidence=bundle.resolution.confidence,
                raw_value=raw_val,
                notes=f"Evidence found: {bundle.resolution.evidence_text[:80]}",
            ))

        # 7. Reddit social sentiment — DISABLED
        # Reddit sentiment at 0.35 confidence adds noise, not alpha.
        # Keeping the field in MarketSignalBundle for future use if we
        # build a better NLP pipeline.

        # 8. Wikipedia velocity
        if bundle.wikipedia_velocity_lr != 1.0:
            signals.append(SignalUpdate(
                source="wikipedia_velocity",
                likelihood_ratio=bundle.wikipedia_velocity_lr,
                confidence=0.45,   # was 0.6 — Wikipedia spikes are suggestive, not definitive
                raw_value=bundle.wikipedia_velocity_lr,
                notes="Wikipedia edit spike detected",
            ))

        logger.debug(
            f"Market {bundle.market_id}: {len(signals)} signals → Bayesian fusion"
        )

        return self._bayesian.fuse(
            market_id=bundle.market_id,
            prior_prob=bundle.prior_price,
            signals=signals,
        )
