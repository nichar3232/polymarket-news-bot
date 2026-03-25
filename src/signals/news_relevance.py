"""
News-to-market relevance scoring.

Combines TF-IDF-like keyword matching with GDELT event codes
and RSS article analysis to score how relevant a news event is
to each tracked market.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ingestion.rss import NewsItem
    from src.ingestion.gdelt import GDELTEvent


POSITIVE_SENTIMENT_WORDS = frozenset({
    "approve", "approved", "win", "winning", "wins", "victory", "pass", "passed",
    "confirm", "confirmed", "agree", "agreement", "signed", "deal", "support",
    "positive", "strong", "surge", "rise", "grew", "growth", "up", "higher",
    "likely", "probable", "expect", "expects", "projected", "forecast",
    "optimistic", "confident", "bullish", "advance", "lead", "leads", "leading",
})

NEGATIVE_SENTIMENT_WORDS = frozenset({
    "reject", "rejected", "fail", "failed", "lose", "losing", "loss", "collapse",
    "veto", "blocked", "deny", "denied", "oppose", "opposition", "negative",
    "weak", "decline", "fell", "drop", "lower", "unlikely", "doubt", "concerns",
    "pessimistic", "bearish", "retreat", "behind", "crisis", "recession",
})

UNCERTAINTY_WORDS = frozenset({
    "unclear", "uncertain", "unknown", "ambiguous", "unclear", "may", "might",
    "could", "possible", "perhaps", "maybe", "allegedly", "reportedly",
})


@dataclass
class NewsRelevanceScore:
    raw_relevance: float      # 0.0–1.0 keyword match strength
    sentiment: float          # -1.0 to +1.0
    sentiment_confidence: float  # 0.0–1.0 (how many sentiment words found)
    uncertainty_flag: bool    # True if article is hedged/uncertain
    likelihood_ratio: float   # Bayesian LR


def score_news_item(
    text: str,
    keywords: list[str],
    question: str = "",
) -> NewsRelevanceScore:
    """
    Score a news article's relevance and sentiment for a prediction market.

    text: concatenated title + summary
    keywords: market-relevant terms
    question: the market question text (for additional context matching)
    """
    text_lower = text.lower()
    words = re.findall(r"\b\w+\b", text_lower)
    word_set = set(words)

    # --- Relevance: TF-IDF-inspired ---
    relevance = 0.0
    matched_keywords = 0
    for kw in keywords:
        kw_lower = kw.lower()
        # Exact phrase match (multi-word)
        if kw_lower in text_lower:
            # IDF-like: shorter keywords are less distinctive
            kw_words = kw_lower.split()
            idf_weight = math.log(1 + len(kw_words))
            relevance += 0.3 * idf_weight
            matched_keywords += 1

    # Question text matching
    if question:
        q_words = set(re.findall(r"\b\w{4,}\b", question.lower()))
        overlap = q_words & word_set
        relevance += len(overlap) / max(len(q_words), 1) * 0.2

    relevance = min(relevance, 1.0)

    # --- Sentiment ---
    pos_count = len(word_set & POSITIVE_SENTIMENT_WORDS)
    neg_count = len(word_set & NEGATIVE_SENTIMENT_WORDS)
    uncertainty_count = len(word_set & UNCERTAINTY_WORDS)

    sentiment_total = pos_count + neg_count
    if sentiment_total == 0:
        sentiment = 0.0
        sentiment_confidence = 0.0
    else:
        sentiment = (pos_count - neg_count) / sentiment_total
        # Confidence: more sentiment words = higher confidence
        sentiment_confidence = min(sentiment_total / 5.0, 1.0)

    uncertainty_flag = uncertainty_count > 2

    # Apply uncertainty penalty to confidence
    if uncertainty_flag:
        sentiment_confidence *= 0.5

    # --- Likelihood ratio ---
    lr = _news_to_lr(relevance, sentiment, sentiment_confidence)

    return NewsRelevanceScore(
        raw_relevance=relevance,
        sentiment=sentiment,
        sentiment_confidence=sentiment_confidence,
        uncertainty_flag=uncertainty_flag,
        likelihood_ratio=lr,
    )


def score_rss_item(item: "NewsItem", keywords: list[str], question: str = "") -> NewsRelevanceScore:
    return score_news_item(item.full_text, keywords, question)


def score_gdelt_event(
    event: "GDELTEvent",
    keywords: list[str],
    question: str = "",
) -> NewsRelevanceScore:
    """Score a GDELT event using tone scores and keyword matching."""
    from src.ingestion.gdelt import score_gdelt_relevance

    # Use GDELT's own relevance scorer
    relevance = score_gdelt_relevance(event, keywords)

    # GDELT tone: -100 to +100 scale. Normalize to -1 to +1.
    # Goldstein scale is used for geopolitical events
    normalized_tone = max(-1.0, min(1.0, event.tone / 50.0))

    # Confidence from activity reference density (higher = more prominent story)
    confidence = min(event.activity_ref_density / 5.0, 1.0)

    uncertainty_flag = abs(event.polarity) < 0.5 and abs(event.tone) < 5

    lr = _news_to_lr(relevance, normalized_tone, confidence)

    return NewsRelevanceScore(
        raw_relevance=relevance,
        sentiment=normalized_tone,
        sentiment_confidence=confidence,
        uncertainty_flag=uncertainty_flag,
        likelihood_ratio=lr,
    )


def _news_to_lr(relevance: float, sentiment: float, confidence: float) -> float:
    """
    Convert news relevance + sentiment to a Bayesian likelihood ratio.

    If irrelevant → LR = 1.0 (no update)
    If relevant and positive → LR > 1
    If relevant and negative → LR < 1

    Formula:
    LR = exp(sentiment * relevance * confidence * k)
    k = 2.5 calibrated so that a highly relevant, strongly positive article → LR ≈ 3.5
    """
    if relevance < 0.1:
        return 1.0

    k = 2.5
    exponent = sentiment * relevance * confidence * k
    return math.exp(exponent)
