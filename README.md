# Polymarket Autonomous Trading Agent

> **Hackathon project — University of Pennsylvania 2026**
> An autonomous prediction market trading agent that ingests 20+ real-time data sources, fuses 9 independent Bayesian signals, and executes Kelly-sized positions on Polymarket — all with a live React dashboard and zero required API keys.

Most prediction market bots pipe RSS headlines into GPT, get a sentiment score, and blindly trade on it. This agent does something fundamentally different: it ingests **20+ real-time data sources** — from GDELT's 100-country news firehose to Wikipedia edit velocity spikes that precede breaking news by 5–15 minutes — distills them into **9 independent trading signals**, each expressed as a Bayesian likelihood ratio, fuses them through a **log-odds Bayesian inference engine** with structured correlation damping, produces a calibrated posterior probability with 90% confidence interval, and sizes every position using the **Kelly criterion (0.25× fractional)** with proper fee math and portfolio-level exposure caps.

```
               ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐     ┌───────────┐
  20+ sources  │  INGESTION   │────▶│  9 SIGNALS → LR  │────▶│  BAYESIAN   │────▶│  KELLY    │
  (real-time)  │  polymarket  │     │  vpin, cross-mkt  │     │  FUSION     │     │  SIZING   │
               │  gdelt, rss  │     │  news, llm, wiki  │     │  log-odds   │     │  0.25× f* │
               │  wiki, reddit│     │  reddit, spread   │     │  posterior  │     │  position │
               │  resolution  │     │  resolution       │     │  + 90% CI   │     │  capped   │
               └─────────────┘     └──────────────────┘     └─────────────┘     └───────────┘
                                                                                       │
                                                             ┌──────────────┐          │
                                                             │   EXECUTE    │◀─────────┘
                                                             │  paper mode  │
                                                             │  or live CLOB│
                                                             └──────────────┘
```

---

## Table of Contents

1. [Project Goals](#project-goals)
2. [Quick Start](#quick-start)
3. [Demo Walkthrough](#demo-walkthrough)
4. [Data Ingestion Strategy](#data-ingestion-strategy)
5. [The 9 Trading Signals](#the-9-trading-signals)
6. [Bayesian Fusion Engine](#bayesian-fusion-engine)
7. [Kelly Criterion Position Sizing](#kelly-criterion-position-sizing)
8. [Risk Management](#risk-management)
9. [Live Dashboard](#live-dashboard)
10. [REST & WebSocket API Reference](#rest--websocket-api-reference)
11. [Configuration Reference](#configuration-reference)
12. [Trading Modes](#trading-modes)
13. [Error Handling & Graceful Fallback](#error-handling--graceful-fallback)
14. [Testing](#testing)
15. [Architecture & Project Structure](#architecture--project-structure)
16. [Docker Deployment](#docker-deployment)
17. [What Makes This Different](#what-makes-this-different)

---

## Project Goals

### The Problem

Prediction markets like Polymarket are efficient in aggregate, but that efficiency is uneven across time and information channels. Three exploitable inefficiencies exist:

1. **Information latency gaps** — the same event is priced differently on Kalshi, Metaculus, Manifold, and Polymarket at the same instant. Arbitrage is available for seconds to minutes.
2. **Pre-news signals** — Wikipedia edit velocity, informed order flow (VPIN), and GDELT's global news coverage often move before mainstream US media publishes. Whoever reads these signals first has a 5–15 minute edge.
3. **Bayesian miscalibration** — most participants anchor too heavily on the current market price and update too slowly. A calibrated agent that correctly weights independent evidence can maintain a persistent edge.

### The Approach

Build a principled, real-time trading agent that:
- **Collects evidence** from every accessible signal source (news, order flow, social, cross-platform, global media, Wikipedia, LLM reasoning)
- **Converts evidence to likelihood ratios** — the correct mathematical representation for Bayesian inference
- **Fuses signals in log-odds space** — numerically stable, independence-assumption transparent, no "magic weights"
- **Sizes positions with fractional Kelly** — maximizes long-run geometric portfolio growth given uncertainty
- **Paper trades by default** — no real money at risk until explicitly enabled
- **Shows everything in a live dashboard** — every signal, every update, in real time

### Why Polymarket

Polymarket is the largest on-chain prediction market with real money at stake, a proper CLOB (central limit order book), and a public API. The stakes and the market microstructure make it the most interesting place to trade algorithmically.

---

## Quick Start

**Requirements:** Python 3.11+, Node.js 18+ (for dashboard)

```bash
# Clone and install
git clone https://github.com/tharune/polymarket-news-bot.git
cd polymarket-news-bot
pip install -e .
cp .env.example .env

# ── Option 1: Judge demo (no credentials, ~30 seconds) ──
python3.11 scripts/demo_event.py

# ── Option 2: Standalone web dashboard (realistic demo data) ──
python3.11 scripts/run_dashboard.py        # → http://localhost:8080

# ── Option 3: Full autonomous agent + live dashboard ──
python3.11 scripts/run_agent.py            # → http://localhost:8080

# ── Option 4: Historical backtest on resolved markets ──
python3.11 scripts/run_backtest.py

# ── Run tests ──
python3.11 -m pytest tests/ -v             # 74/74 pass
```

**Or with Docker (zero Python setup):**

```bash
cp .env.example .env
docker compose up agent                        # full agent + dashboard on :8080
docker compose --profile dashboard up          # demo dashboard only, no API keys needed
docker compose --profile demo up               # terminal demo only
```

### Zero API Keys Required

Everything works out of the box with zero credentials in paper trading mode:

| Feature | No keys | With Groq key | With Polymarket keys |
|---------|:-------:|:-------------:|:--------------------:|
| All 20+ data sources | ✓ | ✓ | ✓ |
| 8 of 9 trading signals | ✓ | ✓ | ✓ |
| LLM superforecaster signal | — | ✓ | ✓ |
| Paper trading + P&L dashboard | ✓ | ✓ | ✓ |
| Testnet / live execution | — | — | ✓ |

**To enable the LLM signal (free, 2 minutes):** Sign up at [console.groq.com](https://console.groq.com), create an API key, add `GROQ_API_KEY=gsk_...` to `.env`. Free tier: 100k tokens/day.

**Alternative LLM:** Add `GEMINI_API_KEY=...` from [aistudio.google.com](https://aistudio.google.com) (free, 1,500 req/day). Or install [Ollama](https://ollama.com) locally (`ollama pull llama3.2`) for unlimited offline inference.

---

## Demo Walkthrough

```bash
python3.11 scripts/demo_event.py
```

This replays a real historical event end-to-end through the full 9-signal pipeline:

**Scenario:** *"Will the Fed cut rates at the March 2024 FOMC meeting?"*

| Step | Signal | What Fires | LR |
|:----:|--------|-----------|:--:|
| 1 | — | Market fetched: Polymarket price = **18% YES** | prior |
| 2 | News RSS | Reuters: "CPI rises 0.4%, above forecast" — sentiment -0.6, relevance 0.85 | 0.31 |
| 3 | News RSS | AP: "Powell signals no rush to cut rates" — sentiment -0.75, relevance 0.95 | 0.22 |
| 4 | Wikipedia | `Federal_Reserve` page: 8 edits/5 min **(4.2× baseline)** | 1.5 |
| 5 | Cross-Market | Kalshi=12%, Metaculus=10%, Manifold=15% — all more bearish than Polymarket | 0.28 |
| 6 | VPIN | VPIN = 0.52 — informed trading active. OFI = -0.38 — **NO pressure** | 0.46 |
| 7 | LLM | Decomposes into 3 sub-claims — P(YES) = 15%, CI = [8%, 25%] | 0.58 |
| 8 | GDELT | Global wire services: "Rate cut expectations fade" — tone -12.4 | 0.41 |
| 9 | Resolution | BLS: CPI data shows persistent inflation, inconsistent with cut | 0.35 |
| **→** | **Bayesian Fusion** | **18% → 4.3% posterior** | — |
| **→** | **Kelly Sizing** | **BUY NO, $50 position @ 0.822** | — |
| **✓** | **Result** | **Fed did NOT cut in March 2024. Trade profitable.** | — |

The demo produces formatted terminal output showing every signal, every LR, the full Bayesian update chain, and the final trade decision.

---

## Data Ingestion Strategy

The system ingests from **20+ sources** across 4 latency tiers. All sources are free and require zero authentication for paper trading.

### Real-Time Streams (< 1 second latency)

| Source | Method | Data | Update Frequency |
|--------|--------|------|-----------------|
| **Polymarket WebSocket** | WebSocket | Live trades (price, size, side) for VPIN calculation | Every trade |
| **Polymarket REST** | REST | Orderbook snapshots (bids/asks, 5 levels), market metadata | 60 seconds |
| **Kalshi** | REST | YES price for matched event markets | 5 seconds |
| **Metaculus** | REST | Community expert forecast probability | ~1 minute |
| **Manifold Markets** | REST | Crowd prediction probability | ~1 second |

### Polling Sources (1–5 minute latency)

| Source | Method | Data | Update Frequency |
|--------|--------|------|-----------------|
| **Wikipedia Recent Changes** | REST API | Edit frequency per tracked page (pre-news signal) | 2 minutes |
| **Reddit (6 subreddits)** | Public JSON API | Posts from r/PredictionMarkets, r/worldnews, r/politics, r/Economics, r/geopolitics, r/CredibleDefense | 5 minutes |
| **RSS Feeds (15 feeds)** | HTTP + feedparser | Reuters, AP, BBC, CNN, Guardian, NPR, FT, Politico, WSJ, NYT + 5 more | 60 seconds |

### Batch Sources (15-minute latency)

| Source | Method | Data | Update Frequency |
|--------|--------|------|-----------------|
| **GDELT GKG 2.0** | HTTP → ZIP → TSV | Goldstein tone scores, themes (`ECON_INFLATION`, `PROTEST`, etc.), named entities from 100+ global news sources | 15 minutes |

### Event-Driven Sources

| Source | Method | Data | Trigger |
|--------|--------|------|---------|
| **Resolution RSS** | RSS (BLS, Fed, FDA, AP, Reuters) | Official government/agency resolution data matched against market criteria | On publication |
| **LLM Reasoning Chain** | Groq → Gemini → Ollama | Structured superforecaster probability decomposition | Per evaluation cycle |

### Ingestion Metrics

Every source tracks fetch latency, item counts, and stale rejections via `src/ingestion/metrics.py`. These are accessible at `/api/ingestion`:

```json
{
  "uptime_s": 180,
  "sources": {
    "rss": { "fetch_count": 3, "avg_fetch_ms": 1708, "p95_fetch_ms": 2100, "items_ingested": 477 },
    "gdelt": { "fetch_count": 1, "avg_fetch_ms": 3200, "items_ingested": 440 },
    "polymarket_rest": { "fetch_count": 3, "avg_fetch_ms": 734, "items_ingested": 200 }
  }
}
```

### Why This Mix Matters

Most prediction market bots use a single data type (usually RSS sentiment). Our edge comes from **signal diversity across time horizons**:

- **Microstructure signals** (VPIN, order flow) detect informed trading *before* information is public — real-time
- **Wikipedia edit velocity** spikes 5–15 minutes before mainstream news breaks — near real-time
- **Cross-market arbitrage** exploits the fact that information hits Kalshi/Metaculus/Manifold at different times — seconds to minutes
- **RSS feeds** (15 sources) provide breadth across major wire services — ~1 minute
- **GDELT** covers 100+ sources globally, including non-English media that most traders never see — 15 minutes
- **LLM decomposition** applies superforecaster methodology for structured reasoning — per cycle
- **Reddit sentiment** provides noisy but sometimes early crowd signals — 5 minutes

The combination of fast signals (VPIN, Wikipedia) with authoritative slow signals (GDELT, LLM) creates a **temporal edge** that no single source provides.

---

## The 9 Trading Signals

Each signal independently produces a **likelihood ratio (LR)** — not a score, not a label — that feeds directly into the Bayesian fusion engine.

A likelihood ratio *L* means: *"This evidence is L times more probable under YES than under NO."*

- *L* > 1 — evidence supports YES
- *L* < 1 — evidence supports NO (L=0.5 means evidence is twice as likely under NO)
- *L* = 1 — evidence is uninformative; no Bayesian update

All signal LRs are bounded within practical calibrated ranges to prevent any single signal from dominating the posterior (typically capped at [0.25, 4.0] for strong signals).

---

### Signal 1: VPIN (Volume-Synchronized Probability of Informed Trading)

**File:** `src/signals/microstructure.py` | **Input:** Polymarket live WebSocket trade stream

Adapted from academic HFT literature (Easley, Lopez de Prado & O'Hara, 2012). Detects when informed traders — those with private information — are active in the market by measuring volume imbalance in equal-volume buckets.

**Algorithm:**

1. Accumulate live trades until the bucket reaches the target volume (total\_volume / num\_buckets)
2. For each completed bucket: `imbalance = |YES_volume - NO_volume| / bucket_size`
3. `VPIN = mean(imbalances over last N buckets)` — range [0, 1]; higher = more one-sided
4. `OFI = (total_YES - total_NO) / (total_YES + total_NO)` — range [-1, +1]; positive = YES pressure

**Likelihood Ratio:**

```python
vpin_strength = max(0.0, (VPIN - 0.3) / 0.7)   # 0 at VPIN=0.3, 1 at VPIN=1.0
LR = exp(2.0 * OFI * vpin_strength)              # k=2.0; max LR ≈ e^2 ≈ 7.4
```

VPIN below 0.3 produces `LR = 1.0` (neutral — uninformed trading). Above 0.4 is flagged as informed trading present.

**Why equal-volume buckets?** Time-based windows conflate low-volume and high-volume periods. Equal-volume buckets normalize for market activity, making VPIN comparable across different market conditions and times of day.

**Why it matters:** Informed traders leave measurable fingerprints in order flow *before* the news reaches public channels. VPIN gives us a 5–15 minute early warning of impending directional moves.

---

### Signal 2: Orderbook Spread & Depth

**File:** `src/signals/microstructure.py` | **Input:** Polymarket REST orderbook snapshots

Analyzes the liquidity structure — bid-ask spread and depth distribution across the top 5 levels on each side.

```python
depth_YES = sum(size for top 5 bid levels)
depth_NO  = sum(size for top 5 ask levels)
depth_imbalance = (depth_YES - depth_NO) / (depth_YES + depth_NO)   # [-1, +1]

LR = exp(depth_imbalance * 0.5)    # Mild signal; max LR ≈ 1.65
```

Wide spreads (> 5% of mid-price) halve the signal strength — high uncertainty reduces the informativeness of depth imbalance. This signal is intentionally mild: depth imbalance is correlated with VPIN (they share the same orderbook) and is assigned `INTRA_GROUP_DAMPING = 0.40` within the microstructure correlation group.

---

### Signal 3: Cross-Market Arbitrage (Kalshi, Metaculus, Manifold)

**File:** `src/signals/cross_market.py` | **Input:** 3 independent prediction platforms

When multiple independent platforms disagree with Polymarket in the same direction, that's real alpha. Each platform has different trader populations, different market designs, and different information sets — consensus across them is meaningful.

```python
for each platform (Kalshi, Metaculus, Manifold):
    delta = platform_price - polymarket_price
    if abs(delta) >= MIN_DIVERGENCE (5%):
        record direction and magnitude

# Weight by how many sources agree:
source_multiplier = {1: 0.7, 2: 1.0, 3: 1.3}[n_sources_agree]
LR = exp(direction * mean_abs_delta * source_multiplier * 3.0)
```

**Calibration:** 2 sources agreeing with 15% divergence → LR ≈ 2.5. Single-source signals are dampened 0.5× by confidence scaling.

**Practical note:** Not all Polymarket markets have exact matches on all platforms. The agent fuzzy-matches market questions using keyword overlap and only fires this signal when match confidence is high.

---

### Signal 4: News Relevance (RSS — 15 Feeds)

**File:** `src/signals/news_relevance.py` | **Input:** Reuters, AP, BBC, CNN, Guardian, NPR, FT, Politico, WSJ, NYT + 5 domain-specific feeds

TF-IDF-inspired keyword matching combined with lexicon-based sentiment analysis (no ML model required — fully deterministic).

```python
# Relevance: how much does this article relate to this specific market?
keyword_matches = sum(1 for kw in market_keywords if kw in article_text)
question_overlap = len(market_question_words & article_words) / len(market_question_words)
relevance = min(1.0, keyword_matches * log(1 + word_count) / 100 + question_overlap * 0.3)

# Sentiment: is the news positive or negative for YES?
positive_words = count(["confirmed", "passed", "won", "approved", "reached", ...])
negative_words = count(["failed", "rejected", "fell", "declined", "missed", ...])
sentiment = (positive_words - negative_words) / (positive_words + negative_words + 1)

# Uncertainty penalty: "may", "might", "unclear", "uncertain" → halve confidence
confidence = 0.5 if uncertainty_word_count > 2 else 1.0

LR = exp(sentiment * relevance * confidence * 2.5)
```

Multiple articles for the same market are aggregated via log-space weighted average (weighted by relevance score).

**Calibration:** Highly relevant (relevance=0.9) + strongly positive (sentiment=0.8) + certain → LR ≈ 3.5.

---

### Signal 5: GDELT Global News (100+ Sources)

**File:** `src/signals/news_relevance.py` + `src/ingestion/gdelt.py` | **Input:** GDELT GKG 2.0 CSV (updated every 15 minutes)

GDELT (Global Database of Events, Language, and Tone) processes 100+ news sources in 65 languages every 15 minutes. The GKG (Global Knowledge Graph) output contains:
- **Goldstein tone** — numeric sentiment score for each article (range -100 to +100)
- **CAMEO themes** — structured event categories (`ECON_INFLATION`, `GOV_REFORM`, `PROTEST`, etc.)
- **Named entities** — persons, organizations, locations mentioned

```python
# Per-event relevance scoring
entity_match = (  person_match(market_keywords)
                + org_match(market_keywords)
                + location_match(market_keywords)
                + theme_match(market_themes) )
relevance = min(1.0, entity_match / 3.0)

# Tone to LR conversion
tone_normalized = goldstein_tone / 50.0           # normalize to [-1, +1]
activity_confidence = min(activity_ref_density / 5.0, 1.0)
LR = exp(tone_normalized * relevance * activity_confidence * 2.0)
```

Events are buffered per-market in `run_agent.py` (up to 50 events per market, pruned at 12 hours). Each evaluation cycle aggregates the buffer via relevance-weighted log-average LR.

**Why it matters:** GDELT covers non-English media, regional outlets, and wire services from 100+ countries. Events that most English-language traders haven't seen yet are already priced into this signal.

---

### Signal 6: LLM Superforecaster Decomposition

**File:** `src/reasoning/decomposer.py` | **LLM Chain:** Groq (Llama 3.3 70B) → Gemini 1.5 Flash → Ollama (local)

Instead of asking "is this bullish?" (what most bots do), we implement the full **Good Judgment Project superforecaster methodology**:

1. **Parse** the exact resolution criteria — what must be true for YES?
2. **Decompose** into 3–5 independent, mutually exclusive sub-claims
3. **Estimate** P(each sub-claim) with explicit step-by-step reasoning
4. **Calculate** joint P(YES) from the inside view (specific evidence + context)
5. **Anchor** with outside view: `blended = 0.70 × inside_view + 0.30 × historical_base_rate`
6. **Output** calibrated P(YES) + 90% confidence interval

```python
# Convert LLM probability to likelihood ratio:
prior_odds     = market_price / (1 - market_price)
posterior_odds = blended_prob / (1 - blended_prob)
LR = posterior_odds / prior_odds

# Confidence derived from CI width:
confidence = max(0.3, 1.0 - ci_width * 2)   # narrow CI = higher confidence
```

**Temperature:** 0.1 — probability estimation should be near-deterministic, not creative.

**Fallback chain:** Groq → Gemini → Ollama. If all LLM providers fail, this signal produces `LR = 1.0` (neutral) and the agent continues with the remaining 8 signals. The agent is fully functional without LLM.

---

### Signal 7: Wikipedia Edit Velocity

**File:** `src/ingestion/wikipedia.py` | **Input:** Wikipedia Recent Changes API

Wikipedia has thousands of volunteer editors who monitor news feeds and update articles in real time. This creates a *leading indicator*: Wikipedia pages related to a market event show edit spikes **5–15 minutes before** mainstream news publishes.

```python
baseline_rate  = edits_last_60min / 12           # 5-min average over last hour
velocity       = edits_last_5min / baseline_rate   # spike multiplier
is_spiking     = (velocity >= 3.0) and (edits_last_5min >= 3)

LR = min(1.0 + (velocity - 3.0) * 0.1, 1.5)     # Capped at 1.5; max at velocity=8.0
```

A spike means *something is happening* — but Wikipedia edits don't tell us the direction. The LR is always ≥ 1.0 (never bearish in isolation). It amplifies the confidence in whatever direction other signals indicate, acting as a volatility multiplier.

**Which pages are tracked:** The Wikipedia monitor extracts named entities from each market question (using keyword parsing), maps them to Wikipedia page titles, and monitors those pages. 26 pages tracked on average.

---

### Signal 8: Reddit Social Sentiment

**File:** `src/ingestion/reddit.py` | **Input:** 6 subreddits via public JSON (no OAuth)

Monitored subreddits: `r/PredictionMarkets`, `r/worldnews`, `r/politics`, `r/Economics`, `r/geopolitics`, `r/CredibleDefense`

```python
positive_words = count(["winning", "confirmed", "passed", "approved", ...])
negative_words = count(["losing", "failed", "rejected", "missed", ...])
sentiment = (positive_words - negative_words) / (total_sentiment_words + 1)
LR = exp(sentiment * 0.8)
confidence = 0.35   # Reddit is intentionally given low confidence
```

Confidence is held at 0.35 — Reddit is noisy, often contrarian, and unreliable as a primary signal. Its contribution is dampened accordingly. It's included because it occasionally surfaces early crowd sentiment before professional media reacts.

---

### Signal 9: Resolution Source Monitor

**File:** `src/signals/resolution.py` | **Input:** Official resolution authority RSS feeds

Every Polymarket market specifies a resolution authority — Reuters, AP, BLS (CPI), the Federal Reserve, FDA, etc. This signal directly polls those sources and pattern-matches against the market's resolution criteria.

```python
# Example: "Will CPI exceed 3.5% in January 2025?"
# Resolution source: BLS.gov CPI release RSS
# Pattern: extract CPI value from article, compare to threshold

if resolution_found:
    LR = exp(confidence * 2.0) if likely_yes else exp(-confidence * 2.0)
    LR = max(0.25, min(4.0, LR))   # bounded to [0.25, 4.0]
else:
    LR = 1.0   # no evidence yet
```

This is the highest-confidence signal when it fires — it's direct evidence from the resolution authority itself. The confidence is high (0.85+) when the match is clear and unambiguous.

---

## Bayesian Fusion Engine

**File:** `src/fusion/bayesian.py` | **Aggregation:** `src/fusion/ensemble.py`

### Core Framework

The fusion engine uses **multiplicative Bayesian updating in log-odds space** — the mathematically correct way to combine independent evidence with an informative prior.

**Step 1 — Prior from Polymarket price:**

```python
prior_prob     = market_price_yes          # Polymarket crowd aggregates all public info
prior_odds     = prior_prob / (1 - prior_prob)
prior_log_odds = log(prior_odds)
```

Treating the market price as the prior captures everything the market already knows. We're only looking for evidence the market *hasn't fully priced in yet*.

**Step 2 — Effective likelihood ratio per signal:**

```python
effective_LR_i = 1.0 + (raw_LR_i - 1.0) * confidence_i
```

This dampens each LR toward 1.0 (neutral) proportional to signal uncertainty. A signal with `LR = 4.0` but `confidence = 0.25` contributes an effective LR of 1.75 — only 25% of its claimed update.

**Step 3 — Accumulate in log-odds space with correlation damping:**

```python
for signal in sorted_signals:
    group = signal.correlation_group
    damping = INTRA_GROUP_DAMPING if group_seen[group] else INTER_GROUP_DAMPING
    log_lr_sum += log(effective_LR) * damping
    group_seen[group] = True
```

**Step 4 — Compute posterior probability:**

```python
posterior_log_odds = prior_log_odds + log_lr_sum
posterior_prob     = sigmoid(posterior_log_odds)                  # = e^x / (1 + e^x)
posterior_prob     = clamp(posterior_prob, 0.01, 0.99)
```

**Step 5 — Edge and trade decision:**

```python
edge           = posterior_prob - prior_prob
effective_edge = abs(edge) - POLYMARKET_FEE      # subtract 2% fee
trade_direction = "YES" if (edge > 0 and effective_edge >= MIN_EDGE) else \
                  "NO"  if (edge < 0 and effective_edge >= MIN_EDGE) else "NONE"
```

### Why Log-Odds Space?

In probability space, combining evidence with a prior requires repeated application of Bayes' theorem. In log-odds space, Bayesian updating is simply **additive**:

```
posterior_log_odds = prior_log_odds + Σ log(LR_i)
```

This is:
- **Numerically stable** — no underflow near 0% or overflow near 100%
- **Transparent** — each signal's contribution is visible as an additive term
- **Correct** — exactly equivalent to multiplicative Bayesian updating in probability space

### Structured Correlation Damping

Signals are not truly independent — a Reuters article about the Fed drives both the RSS score (Signal 4) AND the GDELT tone score (Signal 5). Informed trading causes both the VPIN spike (Signal 1) AND the depth imbalance shift (Signal 2).

Naive combination would double-count correlated evidence and overstate certainty.

We use **structured group damping**:

```python
# Correlation groups and their INTRA-group damping:
GROUPS = {
    "microstructure": ["vpin", "spread"],         # share orderbook data → 0.40×
    "news":           ["news_rss", "news_gdelt"],  # share article sources → 0.40×
    "reasoning":      ["llm_decomposition"],       # independent → 0.90× (first signal only)
    "cross_market":   ["cross_market"],            # independent → 0.90×
    "alternative":    ["wikipedia", "resolution"], # weakly correlated → 0.90×
    "social":         ["reddit"],                  # independent → 0.90×
}

INTER_GROUP_DAMPING = 0.90   # first signal from each group: mild discount (mostly independent)
INTRA_GROUP_DAMPING = 0.40   # 2nd+ signal from same group: heavy discount (they share info)
```

**Effect:** The first VPIN signal gets 90% of its weight. The spread/depth signal (same microstructure group) gets only 40% — because it's measuring the same underlying informed trading. Across-group signals (VPIN + cross-market + LLM) get most of their weight because they're genuinely measuring different things.

This is strictly better than scalar damping: it preserves information from independent groups while correctly discounting redundant signals within the same group.

### 90% Confidence Interval

The CI is derived from **signal disagreement** — when signals point in different directions, uncertainty is high regardless of what the posterior says.

```python
log_lrs = [log(effective_LR_i) for each active signal]
std_log_lr = std(log_lrs)

# Delta method: map log-odds uncertainty to probability uncertainty
prob_std = posterior_prob * (1 - posterior_prob) * std_log_lr

# 90% CI (z = 1.645 for one-tailed 95%)
half_width = 1.645 * max(prob_std, 0.02)    # floor at ±2%
CI = [clamp(posterior - half_width, 0.01, 0.99),
      clamp(posterior + half_width, 0.01, 0.99)]
```

**Wide CI** → signals disagree → less certainty → smaller Kelly position size.
**Narrow CI** → signals align → more confidence → larger Kelly position size.

### Calibration Tracking

**File:** `src/fusion/calibration.py`

The agent tracks Brier scores and calibration buckets across all resolved markets. After markets resolve, `calibration_tracker.resolve_market(market_id, outcome)` computes calibration statistics:

- **Brier score** (lower = better): `mean((predicted_prob - actual_outcome)^2)`
- **Calibration buckets**: markets where we predicted 40–60% actually resolved YES ~50% of the time?

```
/api/state → calibration field:
{
  "brier_score": 0.12,
  "n_predictions": 47,
  "n_resolved": 12,
  "calibration": [
    {"bucket": "0-20%", "predicted": 0.11, "actual": 0.08, "n": 5},
    {"bucket": "20-40%", "predicted": 0.31, "actual": null, "n": 0},
    ...
  ]
}
```

### Key Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `POLYMARKET_FEE` | 0.02 | 2% fee deducted from edge before trade decisions |
| `MIN_EDGE` | 0.02 | 2% minimum effective edge to trigger a trade |
| `MIN_SIGNALS` | 2 | Minimum active signals required before any trade fires |
| `INTER_GROUP_DAMPING` | 0.90 | Cross-group per-signal log-LR multiplier |
| `INTRA_GROUP_DAMPING` | 0.40 | Within-group log-LR multiplier (2nd+ signal) |
| `CI_Z` | 1.645 | z-score for 90% confidence interval |

---

## Kelly Criterion Position Sizing

**File:** `src/risk/kelly.py`

The Kelly criterion maximizes the expected logarithm of portfolio value — equivalently, it maximizes the long-run geometric growth rate. We use **0.25× fractional Kelly** for robustness under estimation uncertainty.

### Full Derivation

For a **YES trade** (posterior > market price):

```python
p = posterior_prob              # our estimated probability YES resolves
q = 1 - p
b = (1 - market_price_yes) / market_price_yes    # gross payout odds (shares gained per share staked)
b_net = b * (1 - FEE)           # net of Polymarket's 2% fee

# Full Kelly fraction:
f_star = (b_net * p - q) / b_net    # = p - q/b_net
f_star = max(0.0, f_star)           # never bet negative

# Fractional Kelly (0.25×):
f_fractional = f_star * KELLY_FRACTION   # default 0.25

# Position size:
position_usd = portfolio_value * f_fractional
```

For a **NO trade** (posterior < market price):

```python
p = 1 - posterior_prob          # probability NO resolves (= probability YES is wrong)
q = 1 - p
market_price_no = 1 - market_price_yes
if market_price_no <= 1e-6:     # defensive guard
    return None
b = market_price_yes / market_price_no
b_net = b * (1 - FEE)
# ... same formula as YES
```

### Why 0.25× Kelly?

Full Kelly assumes your probability estimates are exactly correct. Our estimates carry uncertainty (reflected in the CI width). Using 0.25× Kelly is equivalent to inflating our uncertainty by 4× — a conservative but appropriate adjustment.

| Kelly Fraction | Expected Log Return | Max Drawdown | Variance |
|:--------------:|:-------------------:|:------------:|:--------:|
| 1.00× (full) | 100% | Very high | Very high |
| 0.50× (half) | ~87% | High | High |
| **0.25× (ours)** | **~70%** | **Moderate** | **Low** |
| 0.10× | ~45% | Low | Very low |

0.25× retains ~70% of the maximum expected return while dramatically cutting drawdown and variance. This is the standard academic recommendation when probability estimates are uncertain.

### Diversification Discount

When the portfolio holds multiple simultaneous positions, an additional diversification discount prevents overconcentration:

```python
diversification_discount = 1.0 / sqrt(n_open_positions)
adjusted_fraction = kelly_fraction * diversification_discount
```

With 4 open positions: discount = 0.5 → effective Kelly = 0.125×.

### Hard Caps

After Kelly sizing, three independent caps are applied:

```python
position_usd = min(
    position_usd,                           # Kelly-sized amount
    portfolio_value * max_position_pct,     # % cap (default: 5% per trade)
    max_position_usd,                       # absolute cap (default: $50)
)
```

---

## Risk Management

**File:** `src/risk/portfolio.py`

### Portfolio Tracking

The `PortfolioManager` tracks every position in real time:

```
Position fields:
  market_id     — Polymarket condition_id
  direction     — "YES" or "NO"
  size_usd      — dollars invested
  entry_price   — fill price (with slippage if paper trading)
  current_price — latest Polymarket price
  unrealized_pnl = size_usd * (current_price - entry_price) / entry_price  (YES)
                 = size_usd * (entry_price - current_price) / (1 - entry_price)  (NO)
```

### Risk Gates (Pre-Trade Checks)

Before any position opens:

```python
# 1. Cash available?
if size_usd > current_cash:
    reject("Insufficient cash")

# 2. Absolute position limit?
if size_usd > max_position_size_usd:
    reject("Exceeds single-position limit")

# 3. Portfolio exposure cap?
new_exposure = total_exposure_usd + size_usd
if new_exposure / total_value > max_portfolio_exposure:
    reject("Exceeds portfolio exposure limit")
```

### Position Flip Handling

If the agent decides to reverse a position (e.g., open NO when a YES already exists), the existing position is closed at the current market price *before* the new position is opened. The closing price uses the *pre-slippage* market price — not the new order's fill price — to accurately account for PnL on the closed leg.

### Paper Trading Slippage Model

```python
fill_price = current_price * (1 + SLIPPAGE)    # 0.2% simulated market impact
fill_price = min(fill_price, 0.99)              # cap at 99 cents
```

The 0.2% slippage approximates the market impact of a small order on a Polymarket book with typical depth. Actual slippage is adjusted for orderbook depth using the Kyle (1985) square-root market impact model when orderbook data is available.

### Portfolio State

Available at `/api/portfolio` and broadcast to all WebSocket clients after every agent cycle:

| Field | Type | Description |
|-------|------|-------------|
| `total_value` | float | Cash + unrealized position value |
| `starting_value` | float | Initial portfolio value (default $1,000) |
| `cash` | float | Uninvested cash |
| `total_pnl` | float | Realized + unrealized P&L |
| `total_pnl_pct` | float | P&L as % of starting value |
| `exposure_usd` | float | Total capital in open positions |
| `exposure_pct` | float | Exposure as % of portfolio |
| `total_trades` | int | Trades executed since start |
| `win_rate` | float | % of closed trades with positive net P&L |
| `fees_paid` | float | Total fees paid |
| `sharpe_ratio` | float\|null | Annualized Sharpe (requires 20 data points) |
| `max_drawdown_pct` | float\|null | Peak-to-trough drawdown in % points |
| `profit_factor` | float\|null | Gross profits / gross losses |
| `positions` | list | Open position details |

---

## Live Dashboard

**Tech Stack:** React 18 + TypeScript + Vite | **Source:** `dashboard/`

```bash
python3.11 scripts/run_agent.py       # Agent + dashboard at http://localhost:8080
python3.11 scripts/run_dashboard.py   # Demo dashboard (no agent needed)

# Development mode with hot reload:
cd dashboard && npm run dev           # → http://localhost:5173 (proxies API to :8080)
```

### Dashboard Panels

**TopBar** — persistent header with live KPIs:
- Trading mode badge (PAPER / TESTNET / LIVE / DEMO)
- Connection status indicator (live dot when WS connected)
- P&L in dollars and percent (green/red)
- NAV (Net Asset Value)
- Trades executed
- Win rate
- Sharpe ratio
- Max drawdown
- Profit factor
- Live clock

**DEMO MODE banner** — displayed when the backend is unreachable after 10 WebSocket retry attempts. The banner clearly labels synthetic data so judges know the state.

**Portfolio Panel** — detailed portfolio breakdown:
- Hero value display with P&L
- Cash / Exposure / Fees / Exposure % grid
- Risk utilization bar (green→yellow→red as exposure approaches 25% cap)
- Risk limits reference (Max Position, Min Edge, Min Signals, Kelly Fraction)

**P&L Chart** — real-time equity curve:
- SVG line chart with area fill (green/red based on current P&L)
- Zero-baseline reference line
- Updates every agent cycle (~60 seconds)

**Signal Breakdown Panel** — per-market signal analysis:
- Market selector (click any market in the table)
- 9-signal breakdown: source name, likelihood ratio, effective LR, confidence bar, notes
- Bayesian update summary: prior → posterior, edge, effective edge, trade direction badge

**Markets Table** — sortable table of all tracked markets:
- Question text (truncated)
- Prior (Polymarket price) and Posterior (our estimate)
- Edge and Effective Edge
- Confidence interval
- Active signal count
- Trade direction badge (YES / NO / HOLD)

**Activity Log** — live event feed:
- Trade executions (green)
- Agent cycle completions
- Wikipedia spikes (purple)
- Errors (red)
- Info events (dim)

**News Feed** — articles ingested from RSS feeds:
- Title, source, relevance score, market match
- Newest articles at top

### WebSocket Data Flow

```
Browser                              FastAPI Server
  │                                       │
  │──── WS connect to /ws ───────────────▶│
  │◀─── {type: "snapshot", data: {...}} ───│  (full initial state)
  │                                       │
  │          [Every ~60s, per cycle]       │
  │◀─── {type: "portfolio", data: {...}} ──│  (push_portfolio broadcast)
  │◀─── {type: "analysis", data: {...}} ───│  (per market evaluated)
  │◀─── {type: "event", data: {...}} ──────│  (trade/cycle/error events)
  │◀─── {type: "news", data: {...}} ───────│  (new RSS articles)
```

If the backend is unreachable, the dashboard retries up to 10 times with exponential backoff (up to 8 seconds per attempt). After 10 failures (~30 seconds), it activates DEMO MODE with synthetic data and continues retrying every 15 seconds. When the backend comes back, the next successful connection clears DEMO MODE automatically.

---

## REST & WebSocket API Reference

The FastAPI server runs on port 8080. All endpoints return JSON.

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the React dashboard (`dashboard/dist/index.html`) |
| `GET` | `/api/state` | Full agent state snapshot (portfolio, analyses, events, calibration) |
| `GET` | `/api/portfolio` | Portfolio snapshot only (also triggers WS broadcast) |
| `GET` | `/api/analyses` | Last 100 market analyses with signal details |
| `GET` | `/api/events` | Last 500 agent events (trades, cycles, errors) |
| `GET` | `/api/ingestion` | Per-source ingestion metrics (fetch counts, latency, item counts) |
| `WS` | `/ws` | WebSocket stream — initial snapshot + live updates |

### GET /api/state Response Shape

```json
{
  "trading_mode": "paper",
  "started_at": 1711620000.0,
  "portfolio": { "...see Portfolio State table above..." },
  "analyses": [
    {
      "market_id": "0xabc...",
      "question": "Will the Fed cut rates in March 2024?",
      "prior": 0.18,
      "posterior": 0.043,
      "edge": -0.137,
      "effective_edge": -0.117,
      "trade_direction": "NO",
      "ci_lower": 0.021,
      "ci_upper": 0.068,
      "signal_count": 7,
      "signals": [
        { "source": "news_rss", "lr": 0.31, "eff_lr": 0.28, "confidence": 0.85, "notes": "..." },
        { "source": "microstructure_vpin", "lr": 0.46, "eff_lr": 0.44, "confidence": 0.72, "notes": "..." }
      ],
      "timestamp": 1711620060.0
    }
  ],
  "events": [
    { "kind": "trade", "message": "BUY NO $50 @ 0.822 ...", "ts": 1711620070.0 },
    { "kind": "cycle", "message": "Cycle 1: evaluating 20 markets", "ts": 1711620060.0 }
  ],
  "pnl_history": [
    { "ts": 1711620000.0, "pnl_pct": 0.0 },
    { "ts": 1711620060.0, "pnl_pct": -0.12 }
  ],
  "news": [
    { "title": "Fed holds rates steady...", "source": "Reuters", "relevance": 0.87, "market_id": "0xabc...", "ts": 1711620050.0 }
  ],
  "calibration": {
    "brier_score": null,
    "n_predictions": 20,
    "n_resolved": 0,
    "calibration": []
  }
}
```

### WebSocket Message Types

| Type | When Sent | Payload |
|------|-----------|---------|
| `snapshot` | On initial WS connection | Full state (same as `/api/state`) |
| `portfolio` | After every agent cycle (~60s) | Portfolio dict (same as `/api/portfolio`) |
| `analysis` | When a market is evaluated | Single analysis object |
| `event` | Trade, cycle, error, info | `{kind, message, ts}` |
| `news` | New RSS article ingested | `{title, source, relevance, market_id, ts}` |

The server sends a 30-second heartbeat `ping` frame to keep connections alive through proxies.

---

## Configuration Reference

All configuration is loaded from `.env` via Pydantic BaseSettings (`config/settings.py`). Every field has a safe default so the agent starts with zero configuration.

### LLM Providers

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | `""` | Groq API key (free, 100k tokens/day). Primary LLM. |
| `GEMINI_API_KEY` | `""` | Google Gemini key (free, 1,500 req/day). Secondary LLM. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama base URL for local LLM |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model to use |

### News APIs (all optional — public RSS always works)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWSAPI_KEY` | `""` | NewsAPI.org key (free tier). Enables additional news sources. |
| `GUARDIAN_API_KEY` | `""` | The Guardian API (free). |
| `NYTIMES_API_KEY` | `""` | New York Times API (free). |

### Polymarket CLOB (required for live/testnet only)

| Variable | Default | Description |
|----------|---------|-------------|
| `POLYMARKET_API_KEY` | `""` | CLOB API key |
| `POLYMARKET_API_SECRET` | `""` | CLOB API secret |
| `POLYMARKET_API_PASSPHRASE` | `""` | CLOB API passphrase |
| `POLYMARKET_PRIVATE_KEY` | `""` | Polygon wallet private key (hex) |
| `POLYMARKET_FUNDER_ADDRESS` | `""` | Wallet address holding USDC |

All 5 fields must be set for `settings.has_polymarket_creds` to return `True`. Partial credentials cause silent CLOB initialization failure.

### Trading Mode

| Variable | Default | Options | Description |
|----------|---------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper`, `testnet`, `live` | Execution mode |

### Risk Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_POSITION_SIZE_USD` | `50.0` | Hard cap on any single trade ($USD) |
| `MAX_PORTFOLIO_EXPOSURE` | `0.25` | Max total portfolio at risk (25%) |
| `MAX_POSITION_PCT_PER_TRADE` | `0.05` | Max single position as % of portfolio (5%) |
| `MIN_EDGE_THRESHOLD` | `0.02` | Minimum effective edge after fees to trigger trade |
| `KELLY_FRACTION` | `0.25` | Fractional Kelly multiplier |

### Agent Behavior

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNAL_REFRESH_SECONDS` | `60` | Agent evaluation cycle period |
| `LLM_TIMEOUT_SECONDS` | `30` | Per-provider LLM call timeout |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) |

### Reddit (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDDIT_CLIENT_ID` | `""` | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | `""` | Reddit app secret |
| `REDDIT_USER_AGENT` | `polymarket-news-bot/0.1.0` | User agent string |

Reddit is accessed via public JSON API without OAuth by default. OAuth credentials only needed for higher rate limits.

---

## Trading Modes

### Paper Trading (default)

```bash
TRADING_MODE=paper python3.11 scripts/run_agent.py
```

- All trades are simulated by the `PaperTrader` (`src/execution/paper.py`)
- 0.2% slippage applied to all fills
- Full portfolio tracking with P&L, win rate, Sharpe, drawdown
- No real money, no Polymarket credentials required
- Indistinguishable from live mode in the dashboard

### Testnet (Polygon Amoy)

```bash
TRADING_MODE=testnet python3.11 scripts/run_agent.py
```

- Requires all 5 Polymarket CLOB credentials
- Trades executed on Polygon Amoy testnet (chain ID 80002)
- USDC is testnet USDC (no real value)
- Real CLOB order flow, real fills, real orderbook interaction
- Full `CLOBExecutor` path exercised

### Live (Polygon Mainnet)

```bash
TRADING_MODE=live python3.11 scripts/run_agent.py
```

- Requires all 5 Polymarket CLOB credentials
- Real USDC, real positions, real P&L
- All risk limits still apply (hard-coded $50 cap per position, 25% portfolio cap)
- `MIN_EDGE_THRESHOLD = 0.02` ensures only high-conviction trades execute

---

## Error Handling & Graceful Fallback

The agent is designed to degrade gracefully — no individual component failure should crash the process.

### LLM Failure Fallback

```
Groq rate limit / timeout
    → try Gemini
Gemini rate limit / not configured
    → try Ollama
Ollama not running
    → LLM signal produces LR = 1.0 (neutral)
    → Agent continues with 8 remaining signals
```

The LLM decomposition signal is the only optional one. The agent is fully functional without it.

### Data Source Failure Handling

Every data source (`rss.py`, `gdelt.py`, `wikipedia.py`, `reddit.py`, cross-market platforms) wraps all network calls in try/except. Failures are logged as warnings and that source's signal produces `LR = 1.0` for that cycle.

### WebSocket Reconnect (Dashboard)

```
WS connection drops
    → exponential backoff retry (1s, 2s, 4s, 8s, ... cap at 8s)
After 10 retries (~30s):
    → activate DEMO MODE with synthetic data
    → display "DEMO MODE — backend not connected" banner
    → continue retrying every 15 seconds
On reconnect:
    → receive snapshot message → demoMode = false → banner hides
```

### CLOB Execution Failure

```
CLOB executor fails to initialize:
    → OrderRouter falls back to paper trading
    → logs WARNING "Falling back to paper"
    → agent continues without interruption
```

### Agent Cycle Errors

```
asyncio.gather(*market_eval_tasks, return_exceptions=True)
    → individual market failures are caught as exceptions
    → logged as warnings, not re-raised
    → other markets in the same cycle continue normally
```

### React Error Boundary

The dashboard wraps the entire component tree in a React `ErrorBoundary`. If any panel throws a render error (bad data shape, null dereference, etc.), the boundary catches it and shows an isolated error message with a retry button — the rest of the dashboard continues working.

---

## Testing

```bash
python3.11 -m pytest tests/ -v   # 74/74 pass
```

**74 tests** covering the mathematical core, full signal pipeline, and portfolio accounting:

| Test File | Count | Coverage |
|-----------|------:|---------|
| `test_bayesian.py` | 13 | No signals → posterior = prior; bullish/bearish updates; bound checking; neutral LR passthrough; opposing signal cancellation; edge calculation; CI computation; trade direction thresholds |
| `test_kelly.py` | 11 | No edge → no trade; YES/NO direction; size = portfolio × f × fraction; USD and % caps; non-negative Kelly; EV correctness; fee math; high-probability market behavior |
| `test_microstructure.py` | 12 | VPIN equal-volume bucketing; OFI bounds [-1, +1]; VPIN > 0.4 informed detection; spread LR calculation; OFI-to-LR direction mapping; symmetry |
| `test_cross_market.py` | 9 | No alt data → neutral; single/multi-source consensus; mixed signals cancel; MIN_DIVERGENCE threshold; LR bounds [0.5, 2.5] |
| `test_news_relevance.py` | 10 | Irrelevant → LR=1.0; positive/negative → LR direction; uncertainty penalty; question overlap boost; keyword match relevance; LR bounds |
| `test_ensemble.py` | 10 | Empty bundle → prior; VPIN/cross-market/news/Reddit/Wikipedia signal inclusion; multi-signal compounding; neutral signal filtering; aggregation |
| `test_portfolio.py` | 12 | Initial state; open/close positions; position/exposure/cash limit enforcement; P&L calculation; win rate; unrealized PnL; price updates |

All tests are pure unit tests with no network calls, no API keys required, and run in < 0.5 seconds.

---

## Architecture & Project Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA INGESTION LAYER                        │
│  Polymarket WS (live trades)   │  Polymarket REST (orderbook)   │
│  Kalshi REST   │  Metaculus API  │  Manifold Markets API        │
│  GDELT GKG 2.0 (100+ sources, 15min) │ RSS (15 feeds, 60s)     │
│  Wikipedia Recent Changes (2min) │ Reddit (6 subreddits, 5min)  │
│  Resolution RSS (BLS, Fed, FDA, Reuters, AP)                    │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SIGNAL PROCESSING LAYER                        │
│  Signal 1: VPIN (informed trading)      → LR via exp(k × OFI)  │
│  Signal 2: Spread/Depth (liquidity)     → LR via depth_imb      │
│  Signal 3: Cross-Market (3 platforms)   → LR via divergence      │
│  Signal 4: News RSS (15 feeds)          → LR via TF-IDF + sent  │
│  Signal 5: GDELT (100+ sources)         → LR via tone scoring   │
│  Signal 6: LLM Superforecaster          → LR via decomposition  │
│  Signal 7: Wikipedia Velocity           → LR via edit spike      │
│  Signal 8: Reddit Sentiment             → LR via lexicon        │
│  Signal 9: Resolution Source            → LR via criteria match  │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BAYESIAN FUSION ENGINE                         │
│  Prior = Polymarket price (efficient market baseline)           │
│  Each signal = likelihood ratio (not a score)                   │
│  Posterior computed in log-odds space (numerically stable)       │
│  Structured damping: INTER=0.90, INTRA=0.40 by correlation group│
│  Output: P(YES), 90% CI, edge, effective_edge, trade_direction  │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         RISK LAYER                               │
│  Kelly sizing: 0.25× fractional with fee math                   │
│  Hard caps: $50/position, 5%/position, 25% portfolio exposure   │
│  Diversification discount: 1/√(n_positions)                     │
│  Gates: ≥2 active signals AND effective_edge ≥ 2%              │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXECUTION LAYER                             │
│  Paper: simulated fill with 0.2% slippage + portfolio tracking  │
│  Testnet: Polygon Amoy CLOB (real order flow, fake USDC)        │
│  Live: Polygon Mainnet CLOB (real money)                        │
└─────────────────────────────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               MONITORING & DASHBOARD LAYER                       │
│  FastAPI server: REST + WebSocket pub/sub on :8080              │
│  React 18 + TypeScript + Vite dashboard (dashboard/)            │
│  Rich terminal UI (fallback when no browser available)          │
│  WebSocket broadcast after every cycle via push_portfolio()     │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
polymarket-news-bot/
├── config/
│   ├── settings.py              # Pydantic BaseSettings — all config from .env
│   └── markets.yaml             # Market configs + signal weights
│
├── src/
│   ├── ingestion/               # Data source clients
│   │   ├── polymarket.py        # CLOB WebSocket (live trades) + REST (orderbook, markets)
│   │   ├── gdelt.py             # GDELT GKG 2.0 batch downloader + CSV parser
│   │   ├── rss.py               # 15-feed async RSS monitor + dedup
│   │   ├── wikipedia.py         # Wikipedia Recent Changes edit velocity tracker
│   │   ├── reddit.py            # Reddit public JSON API (no OAuth)
│   │   └── metrics.py           # Per-source fetch latency + item count tracking
│   │
│   ├── signals/                 # Raw data → Likelihood Ratio converters
│   │   ├── microstructure.py    # VPIN (Signal 1) + Spread/Depth (Signal 2)
│   │   ├── cross_market.py      # Kalshi/Metaculus/Manifold arbitrage (Signal 3)
│   │   ├── news_relevance.py    # TF-IDF + sentiment → LR (Signals 4, 5)
│   │   └── resolution.py        # Resolution authority RSS monitor (Signal 9)
│   │
│   ├── reasoning/               # LLM integration (Signal 6)
│   │   ├── llm_client.py        # Groq → Gemini → Ollama fallback chain
│   │   ├── decomposer.py        # Superforecaster decomposition logic
│   │   └── prompts.py           # Calibrated prompt templates
│   │
│   ├── fusion/                  # Bayesian inference engine
│   │   ├── bayesian.py          # Log-odds fusion + CI computation
│   │   ├── ensemble.py          # Signal aggregation → BayesianResult
│   │   └── calibration.py       # Brier score + calibration bucket tracking
│   │
│   ├── risk/                    # Position sizing + portfolio management
│   │   ├── kelly.py             # Fractional Kelly with fee math + div discount
│   │   └── portfolio.py         # Position tracking, P&L accounting, exposure limits
│   │
│   ├── execution/               # Order execution
│   │   ├── clob.py              # Polymarket CLOB executor (testnet + live)
│   │   ├── orders.py            # Paper/testnet/live router + order lifecycle
│   │   └── paper.py             # Paper trading with slippage simulation
│   │
│   ├── monitor/
│   │   └── dashboard.py         # Rich terminal live display (fallback UI)
│   │
│   └── api/                     # Web API
│       ├── state.py             # Shared agent state + WebSocket pub/sub
│       └── server.py            # FastAPI REST endpoints + WebSocket handler
│
├── dashboard/                   # React dashboard (React 18 + TypeScript + Vite)
│   ├── src/
│   │   ├── App.tsx              # Root: ErrorBoundary + AgentProvider + DemoBanner
│   │   ├── components/
│   │   │   ├── TopBar.tsx       # Live KPI header
│   │   │   ├── DashboardGrid.tsx # Panel layout
│   │   │   └── panels/
│   │   │       ├── PortfolioPanel.tsx   # Portfolio detail + risk bar
│   │   │       ├── PnLChart.tsx         # Real-time equity curve
│   │   │       ├── SignalBreakdown.tsx  # Per-market signal detail
│   │   │       ├── MarketsTable.tsx     # Sortable markets overview
│   │   │       ├── ActivityLog.tsx      # Live event feed
│   │   │       └── NewsFeed.tsx         # Latest RSS articles
│   │   ├── context/AgentContext.tsx     # React context wrapping useAgentSocket
│   │   ├── hooks/
│   │   │   ├── useAgentSocket.ts        # WS connection + state reducer
│   │   │   └── useClock.ts              # Live clock hook
│   │   ├── data/mockSnapshot.ts         # Synthetic demo data
│   │   └── types.ts                     # TypeScript type definitions
│   ├── dist/                    # Production build (served by FastAPI)
│   ├── package.json
│   └── vite.config.ts
│
├── scripts/
│   ├── run_agent.py             # Main agent + dashboard server
│   ├── run_dashboard.py         # Standalone demo dashboard (no agent)
│   ├── run_backtest.py          # Historical backtest on resolved markets
│   └── demo_event.py            # Fed rate scenario replay
│
├── tests/                       # 74 pytest unit tests
│   ├── test_bayesian.py         # 13 tests
│   ├── test_kelly.py            # 11 tests
│   ├── test_microstructure.py   # 12 tests
│   ├── test_cross_market.py     # 9 tests
│   ├── test_news_relevance.py   # 10 tests
│   ├── test_ensemble.py         # 10 tests (full signal pipeline)
│   └── test_portfolio.py        # 12 tests
│
├── docs/
│   └── methodology.md           # Full mathematical derivations
│
├── Dockerfile                   # python3.11-slim + uv install + CMD python3.11
├── docker-compose.yml
├── .dockerignore                # Excludes node_modules, __pycache__, .env
├── .env.example                 # Template — copy to .env
└── pyproject.toml               # Dependencies: fastapi, aiohttp, pydantic-settings, etc.
```

---

## Docker Deployment

```bash
cp .env.example .env
# Edit .env with any optional API keys

# Full agent + dashboard
docker compose up agent

# Demo dashboard only (no credentials needed)
docker compose --profile dashboard up

# Terminal demo only
docker compose --profile demo up
```

The Dockerfile uses:
- **Base image:** `python:3.11-slim`
- **Dependency installer:** `uv` for fast resolution
- **Dashboard:** pre-built `dashboard/dist/` is copied into the image
- **CMD:** `python3.11 scripts/run_agent.py`
- **Port:** 8080

`.dockerignore` excludes `dashboard/node_modules` (~200MB), `__pycache__`, `.env`, and `.git` to keep the build context small and secrets out of the image.

---

## What Makes This Different

| What everyone else does | What we do |
|------------------------|-----------|
| RSS → GPT sentiment → score → trade | 9 independent signals → likelihood ratios → Bayesian posterior |
| "This news is 0.7 bullish" | `LR = exp(sentiment × relevance × confidence × k)` — mathematically correct |
| Single LLM call for sentiment | Superforecaster decomposition: sub-claims + base rate anchoring (Good Judgment Project methodology) |
| Check one market price | Cross-market arbitrage vs. Kalshi + Metaculus + Manifold simultaneously |
| Time-based trading signals | VPIN (volume-synchronized) detects informed traders *before* news breaks publicly |
| Western English-only news | GDELT: 100+ global sources, 15-min updates, Goldstein tone + entity/theme tagging |
| No pre-news signal | Wikipedia edit velocity: spikes 5–15 min before mainstream coverage |
| Fixed bet sizing | Fractional Kelly (0.25×) with fee math, diversification discount, and hard caps |
| Scores that can't be combined | Likelihood ratios that multiply correctly under Bayes' rule |
| Single data source | 20+ sources across 4 latency tiers: real-time → polling → batch → event-driven |
| Scalar confidence damping | Structured group damping: INTRA=0.40 (correlated), INTER=0.90 (independent) |
| No uncertainty quantification | 90% CI derived from signal disagreement — wide CI → smaller position |
| Trade or no trade | Continuous position sizing: Kelly-optimal fractions, not binary decisions |
| Dashboard as afterthought | React 18 + TypeScript + WebSocket — every signal, every update, in real time |

### The Core Mathematical Insight

The reason this works is that **likelihood ratios are the correct unit for Bayesian evidence**. A score of "0.7 bullish" tells you nothing — bullish compared to what? By what factor?

A likelihood ratio of 3.0 has a precise meaning: *"This evidence is 3× more likely to occur in a world where YES resolves than in a world where NO resolves."*

When you have multiple likelihood ratios, you multiply them — that's Bayes' theorem. In log space, that's addition. The prior is the market price (which efficiently encodes all public information). Each signal updates the odds only by the amount it adds beyond what the market already knows.

The result: a principled, calibrated estimate of `P(YES)` with proper uncertainty quantification, updated continuously from 9 independent data streams.

---

## Running Without API Keys

Everything works with **zero credentials** in paper trading mode:

- All 20+ data sources (Polymarket, Kalshi, Metaculus, Manifold, GDELT, RSS, Wikipedia, Reddit)
- 8 of 9 trading signals (all except LLM decomposition)
- Paper trading with full P&L tracking and portfolio analytics
- Real-time React dashboard with WebSocket updates
- Historical backtest on resolved markets
- Full demo script (`demo_event.py`)

The only optional credential is for LLM (Signal 6). Without it, the agent runs the other 8 signals — still fully functional, still makes calibrated decisions.

**To enable free LLM (2 minutes):**
1. Sign up at [console.groq.com](https://console.groq.com)
2. Create an API key
3. Add `GROQ_API_KEY=gsk_...` to your `.env`
4. Free tier: 100k tokens/day (resets at midnight UTC)
