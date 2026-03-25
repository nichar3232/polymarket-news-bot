"""
Superforecaster LLM decomposition.

This is the core of our LLM integration. Instead of asking the LLM
"is this bullish or bearish?" (what everyone else does), we implement
the full Good Judgment Project superforecaster methodology:

1. Decompose the market question into independent sub-claims
2. Estimate each P(sub-claim) with explicit reasoning
3. Apply outside-view base rates as a Bayesian anchor
4. Output calibrated P(YES) with confidence interval

The LLM output is then fed as a likelihood ratio into our Bayesian fusion engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from loguru import logger

from src.reasoning.llm_client import LLMClient, LLMResponse
from src.reasoning.prompts import SUPERFORECASTER_SYSTEM, SUPERFORECASTER_USER


@dataclass
class SubClaim:
    claim: str
    probability: float
    reasoning: str


@dataclass
class DecompositionResult:
    question: str
    sub_claims: list[SubClaim]
    joint_probability_inside_view: float
    outside_view_base_rate: float
    outside_view_reasoning: str
    blended_probability: float
    confidence_interval: tuple[float, float]
    key_uncertainties: list[str]
    update_direction: str        # "bullish" | "bearish" | "neutral"
    reasoning_summary: str
    provider: str
    latency_ms: float
    likelihood_ratio: float = field(init=False)

    def __post_init__(self) -> None:
        """Compute likelihood ratio from blended probability vs current price."""
        # LR is computed in compute() after we have market price context
        self.likelihood_ratio = 1.0

    def compute_lr(self, market_price: float) -> float:
        """
        Compute Bayesian likelihood ratio given the current market price.

        LR = P(evidence | YES) / P(evidence | NO)
           ≈ posterior_odds / prior_odds

        posterior_prob = self.blended_probability (our estimate)
        prior_prob = market_price (crowd's estimate)
        """
        prior_odds = market_price / (1 - market_price) if market_price < 1 else 100
        posterior_odds = self.blended_probability / (1 - self.blended_probability) if self.blended_probability < 1 else 100
        lr = posterior_odds / prior_odds if prior_odds > 0 else 1.0
        self.likelihood_ratio = lr
        return lr


class SuperforecasterDecomposer:
    """
    Uses LLM to perform structured superforecaster decomposition of a market question.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def decompose(
        self,
        question: str,
        resolution_criteria: str,
        current_market_price: float,
        news_context: str = "",
        cross_market_context: str = "",
    ) -> DecompositionResult | None:
        """
        Run superforecaster decomposition on a market question.

        Returns a DecompositionResult with calibrated probability estimates,
        or None if the LLM call fails.
        """
        if not self._llm.is_available():
            logger.warning("No LLM provider available, skipping decomposition")
            return None

        user_prompt = SUPERFORECASTER_USER.format(
            question=question,
            resolution_criteria=resolution_criteria,
            current_price=f"{current_market_price:.3f} ({current_market_price * 100:.1f}%)",
            news_context=news_context[:2000] if news_context else "No recent relevant news available.",
            cross_market_context=cross_market_context[:500] if cross_market_context else "No cross-market data available.",
        )

        try:
            response: LLMResponse = await self._llm.complete(
                system_prompt=SUPERFORECASTER_SYSTEM,
                user_prompt=user_prompt,
                temperature=0.1,    # Low temp for calibrated output
                max_tokens=2048,
            )

            result = self._parse_response(question, response, current_market_price)
            if result:
                result.compute_lr(current_market_price)
                logger.info(
                    f"Decomposition: P(YES)={result.blended_probability:.3f} "
                    f"(market={current_market_price:.3f}), "
                    f"LR={result.likelihood_ratio:.3f}, "
                    f"provider={response.provider.value}, "
                    f"latency={response.latency_ms:.0f}ms"
                )
            return result

        except Exception as e:
            logger.error(f"Decomposition failed: {e}")
            return None

    def _parse_response(
        self,
        question: str,
        response: LLMResponse,
        market_price: float,
    ) -> DecompositionResult | None:
        """Parse and validate the LLM JSON response."""
        try:
            data = response.parse_json()
        except Exception as e:
            logger.warning(f"Failed to parse LLM JSON: {e}\nRaw: {response.content[:200]}")
            return None

        # Validate and extract
        try:
            sub_claims = [
                SubClaim(
                    claim=sc.get("claim", ""),
                    probability=_clamp(float(sc.get("probability", 0.5))),
                    reasoning=sc.get("reasoning", ""),
                )
                for sc in data.get("sub_claims", [])
            ]

            blended = _clamp(float(data.get("blended_probability", market_price)))
            inside_view = _clamp(float(data.get("joint_probability_inside_view", blended)))
            outside_view = _clamp(float(data.get("outside_view_base_rate", 0.5)))

            ci_data = data.get("confidence_interval", {})
            ci = (
                _clamp(float(ci_data.get("lower", max(0.02, blended - 0.15)))),
                _clamp(float(ci_data.get("upper", min(0.98, blended + 0.15)))),
            )

            return DecompositionResult(
                question=question,
                sub_claims=sub_claims,
                joint_probability_inside_view=inside_view,
                outside_view_base_rate=outside_view,
                outside_view_reasoning=data.get("outside_view_reasoning", ""),
                blended_probability=blended,
                confidence_interval=ci,
                key_uncertainties=data.get("key_uncertainties", [])[:3],
                update_direction=data.get("update_direction", "neutral"),
                reasoning_summary=data.get("reasoning_summary", ""),
                provider=response.provider.value,
                latency_ms=response.latency_ms,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to build DecompositionResult: {e}")
            return None


def _clamp(value: float, lo: float = 0.02, hi: float = 0.98) -> float:
    """Clamp probability to avoid 0.0/1.0 edge cases."""
    return max(lo, min(hi, value))
