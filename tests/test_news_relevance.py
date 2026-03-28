"""Tests for news relevance scoring and sentiment → LR conversion."""
import pytest

from src.signals.news_relevance import (
    score_news_item,
    _news_to_lr,
    NewsRelevanceScore,
)


def test_irrelevant_article_neutral():
    """Completely irrelevant text should yield LR = 1.0."""
    result = score_news_item(
        text="The weather in Bermuda is lovely this time of year.",
        keywords=["Federal Reserve", "interest rate", "FOMC"],
    )
    assert result.likelihood_ratio == pytest.approx(1.0, abs=0.01)


def test_relevant_positive_article():
    """Relevant + positive article should yield LR > 1."""
    result = score_news_item(
        text="Federal Reserve confirms rate cut approved, strong growth expected",
        keywords=["Federal Reserve", "rate cut"],
    )
    assert result.raw_relevance > 0.15
    assert result.sentiment > 0
    assert result.likelihood_ratio > 1.0


def test_relevant_negative_article():
    """Relevant + negative article should yield LR < 1."""
    result = score_news_item(
        text="Federal Reserve rejected rate cut, economy in recession and decline",
        keywords=["Federal Reserve", "rate cut"],
    )
    assert result.raw_relevance > 0.15
    assert result.sentiment < 0
    assert result.likelihood_ratio < 1.0


def test_uncertainty_reduces_confidence():
    """Articles with many uncertainty words should have lower confidence."""
    certain = score_news_item(
        text="Federal Reserve confirmed rate cut approved, strong consensus",
        keywords=["Federal Reserve", "rate cut"],
    )
    uncertain = score_news_item(
        text="Federal Reserve may perhaps possibly cut rates, unclear if maybe it could happen, reportedly",
        keywords=["Federal Reserve", "rate cut"],
    )
    assert uncertain.uncertainty_flag is True
    assert uncertain.sentiment_confidence <= certain.sentiment_confidence


def test_question_overlap_boosts_relevance():
    """Matching the market question text should boost relevance."""
    without_q = score_news_item(
        text="FOMC meeting scheduled for next week, discussion expected",
        keywords=["FOMC"],
        question="",
    )
    with_q = score_news_item(
        text="FOMC meeting scheduled for next week, discussion expected",
        keywords=["FOMC"],
        question="Will the Federal Reserve cut interest rates at the March 2024 FOMC meeting?",
    )
    assert with_q.raw_relevance >= without_q.raw_relevance


def test_news_lr_bounded():
    """News LR should stay within [0.5, 2.0]."""
    for sent in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        for rel in [0.0, 0.3, 0.6, 1.0]:
            for conf in [0.0, 0.5, 1.0]:
                lr = _news_to_lr(rel, sent, conf)
                assert 0.5 <= lr <= 2.0


def test_low_relevance_always_neutral():
    """Relevance below 0.15 should always return LR = 1.0."""
    lr = _news_to_lr(relevance=0.05, sentiment=0.9, confidence=1.0)
    assert lr == 1.0


def test_sentiment_score_range():
    """Sentiment should be in [-1, +1]."""
    result = score_news_item(
        text="approved confirmed win pass lose fail collapse crisis",
        keywords=["approved"],
    )
    assert -1.0 <= result.sentiment <= 1.0


def test_multiple_keyword_match_higher_relevance():
    """More keyword matches should yield higher relevance."""
    single = score_news_item(
        text="Federal Reserve announced new policy",
        keywords=["Federal Reserve", "rate cut", "FOMC", "inflation"],
    )
    multi = score_news_item(
        text="Federal Reserve rate cut at FOMC meeting amid inflation concerns",
        keywords=["Federal Reserve", "rate cut", "FOMC", "inflation"],
    )
    assert multi.raw_relevance >= single.raw_relevance
