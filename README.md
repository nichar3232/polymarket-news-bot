# Polymarket News Bot — Autonomous Trading Agent

Most prediction market bots pipe RSS headlines into GPT, get a sentiment score, and blindly trade on it. This agent does something fundamentally different: it ingests **20+ real-time data sources** — from GDELT's 100-country news firehose to Wikipedia edit velocity spikes that precede breaking news by 5–15 minutes — distills them into **8 independent trading signals**, each expressed as a Bayesian likelihood ratio, fuses them through a **log-odds Bayesian inference engine** with correlation damping to produce a calibrated posterior probability with 90% confidence interval, and sizes every position using the **Kelly criterion** (0.25x fractional) with proper fee math and portfolio-level exposure caps. The result is an agent that reacts to breaking news, informed order flow, and cross-platform arbitrage opportunities in real time — and knows exactly how much to bet on each one. **Zero API keys required to run.**

```text
               ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐     ┌───────────┐
  20+ sources  │  INGESTION   │────▶│  8 SIGNALS → LR  │────▶│  BAYESIAN   │────▶│  KELLY    │
  (real-time)  │  polymarket  │     │  vpin, cross-mkt  │     │  FUSION     │     │  SIZING   │
               │  gdelt, rss  │     │  news, llm, wiki  │     │  log-odds   │     │  0.25× f* │
               │  wiki, reddit│     │  reddit, spread   │     │  posterior   │     │  position  │
               └─────────────┘     └──────────────────┘     └─────────────┘     └───────────┘
                                                                                       │
                                                            ┌───────────┐              │
                                                            │  EXECUTE  │◀─────────────┘
                                                            │  paper or │
                                                            │  live CLOB│
                                                            └───────────┘
```

---

## See It In Action (30 seconds, no setup)

```bash
pip install -e .
cp .env.example .env
python scripts/demo_event.py
```

This replays a real historical event — **"Will the Fed cut rates in March 2024?"** — through the full pipeline: 8 signals fire, Bayesian fusion shifts the posterior from 18% → 4.3%, Kelly sizes a $50 NO position, and the trade is profitable when the Fed holds rates. No API keys, no credentials, no waiting.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Demo Walkthrough](#demo-walkthrough)
3. [Data Ingestion Strategy](#data-ingestion-strategy)
4. [The 8 Trading Signals](#the-8-trading-signals)
5. [Bayesian Confidence Scoring](#bayesian-confidence-scoring)
6. [Kelly Criterion Position Sizing](#kelly-criterion-position-sizing)
7. [Live Dashboard](#live-dashboard)
8. [Backtesting](#backtesting)
9. [Testing](#testing)
10. [Architecture](#architecture)
11. [What Makes This Different](#what-makes-this-different)

---

## Quick Start

```bash
# Install (Python 3.11+)
pip install -e .
cp .env.example .env

# ── Option 1: Judge demo (no credentials, ~30 seconds) ──
python scripts/demo_event.py

# ── Option 2: Web dashboard with realistic demo data ──
python scripts/run_dashboard.py        # → http://localhost:8080

# ── Option 3: Full autonomous agent + live dashboard ──
python scripts/run_agent.py            # → http://localhost:8080

# ── Option 4: Historical backtest on resolved markets ──
python scripts/run_backtest.py

# ── Run tests ──
pytest tests/ -v                       # 36/36 pass
```

**Or with Docker:**

```bash
cp .env.example .env
docker compose up agent                        # full agent + dashboard on :8080
docker compose --profile dashboard up          # demo dashboard only, no API keys
docker compose --profile demo up               # terminal demo
```

---

## Demo Walkthrough

```bash
python scripts/demo_event.py
```

This replays a real historical event end-to-end through the full 8-signal pipeline:

**Scenario:** *"Will the Fed cut rates at the March 2024 FOMC meeting?"*

| Step | What Happens |
|:----:|-------------|
| 1 | Market fetched: Polymarket price = **18% YES** |
| 2 | Reuters: "CPI rises 0.4%, above forecast" — sentiment -0.6, relevance 0.85 |
| 3 | AP: "Powell signals no rush to cut rates" — sentiment -0.75, relevance 0.95 |
| 4 | Wikipedia spike: `Federal_Reserve` page — 8 edits/5min **(4.2x baseline)** |
| 5 | Kalshi = 12%, Metaculus = 10%, Manifold = 15% — all more bearish than Polymarket |
| 6 | VPIN = 0.52 — informed trading active. OFI = -0.38 — **NO pressure** |
| 7 | LLM decomposes into 3 sub-claims — P(YES) = 15%, CI = [8%, 25%] |
| 8 | **Bayesian fusion: 18% → 4.3% posterior** |
| 9 | Kelly criterion: BUY NO, **$50 position** @ 0.822 |
| **Result** | Fed did NOT cut in March 2024. **Trade profitable.** |

---

## Data Ingestion Strategy

The system ingests from **20+ sources** across 4 latency tiers. Every source is free and requires zero authentication for paper trading.

### Real-Time Streams (< 1 second latency)

| Source | Method | Data | Update Frequency |
|--------|--------|------|-----------------|
| **Polymarket WebSocket** | WebSocket | Live trades (price, size, side) for VPIN | Every trade |
| **Polymarket REST** | REST | Orderbook snapshots (bids/asks, 5 levels) | 60 seconds |
| **Kalshi** | REST | YES price for matched event markets | 5 seconds |
| **Metaculus** | REST | Community expert forecast probability | ~1 minute |
| **Manifold Markets** | REST | Crowd prediction probability | ~1 second |

### Polling Sources (1–5 minute latency)

| Source | Method | Data | Update Frequency |
|--------|--------|------|-----------------|
| **Wikipedia Recent Changes** | REST API | Edit frequency per page (pre-news signal) | 2 minutes |
| **Reddit (6 subreddits)** | Public JSON | Posts from r/PredictionMarkets, r/worldnews, r/politics, r/Economics, r/geopolitics, r/CredibleDefense | 5 minutes |
| **RSS Feeds (15 feeds)** | HTTP + feedparser | Articles from Reuters, AP, BBC, CNN, Guardian, NPR, FT, Politico, WSJ, NYT | 60 seconds |

### Batch Sources (15 minute latency)

| Source | Method | Data | Update Frequency |
|--------|--------|------|-----------------|
| **GDELT GKG 2.0** | HTTP → ZIP → TSV parse | Goldstein tone scores, themes (`ECON_INFLATION`, `PROTEST`, etc.), named entities from 100+ global news sources | 15 minutes |

### Event-Driven Sources

| Source | Method | Data | Trigger |
|--------|--------|------|---------|
| **Resolution RSS** | RSS (BLS, Fed, FDA) | Official government/agency resolution data | On publication |
| **LLM Chain** | Groq → Gemini → Ollama | Structured superforecaster probability decomposition | Per evaluation cycle |

### Why This Mix Matters

Most prediction market bots use a single data type (usually news sentiment). Our edge comes from **signal diversity across time horizons**:

- **Microstructure signals** (VPIN, order flow) detect informed trading **before** the information is public — real-time
- **Wikipedia edit velocity** spikes 5–15 minutes before mainstream news breaks — near real-time
- **Cross-market arbitrage** exploits the fact that information hits Kalshi/Metaculus/Manifold at different times — seconds to minutes
- **RSS feeds** (15 sources) provide breadth across major wire services — ~1 minute
- **GDELT** covers 100+ sources globally, including non-English media that most traders miss — 15 minutes
- **LLM decomposition** applies superforecaster methodology for structured reasoning — per cycle
- **Reddit sentiment** provides noisy but sometimes early crowd signals — 5 minutes

The combination of fast signals (VPIN, Wikipedia) with slow authoritative signals (GDELT, LLM) creates a **temporal edge** that no single source can provide.

### Authentication: Zero Keys Required

| Component | Paper Trading | Live Trading |
|-----------|:------------:|:------------:|
| All 20+ data sources | No keys | No keys |
| Paper trading P&L | No keys | — |
| Web dashboard | No keys | No keys |
| LLM signal (optional) | Free Groq key | Free Groq key |
| Trade execution | — | Polymarket CLOB keys |

---

## The 8 Trading Signals

Each signal independently produces a **likelihood ratio** (LR) — not a score, not a label — that feeds into the Bayesian fusion engine.

A likelihood ratio *L* means: *"This evidence is L times more likely under YES than under NO."*

- *L* > 1 — evidence supports YES
- *L* < 1 — evidence supports NO
- *L* = 1 — evidence is uninformative (no Bayesian update)

### Signal 1: VPIN (Volume-Synchronized Probability of Informed Trading)

**Source:** `src/signals/microstructure.py` | **Input:** Polymarket live trade stream

Adapted from academic HFT literature (Easley, Lopez de Prado & O'Hara, 2012). Detects when informed traders are active by measuring volume imbalance in equal-volume buckets.

**Algorithm:**

1. Partition trades into 50 equal-volume buckets
2. For each bucket, compute |YES\_volume - NO\_volume|
3. VPIN = mean(bucket\_imbalances) / bucket\_size — range \[0, 1\]
4. Order flow imbalance: OFI = (total\_YES - total\_NO) / (total\_YES + total\_NO) — range \[-1, +1\]

**Likelihood Ratio:**

```python
vpin_strength = (VPIN - 0.3) / 0.7         # 0 at VPIN=0.3, 1 at VPIN=1.0
LR = exp(2.0 * OFI * vpin_strength)        # k=2.0; max LR ≈ e^2 ≈ 7.4
```

VPIN below 0.3 produces `LR = 1.0` (neutral). Above 0.4 is flagged as informed trading. Equal-volume bucketing is more robust than time-based windows because it normalizes for varying market activity.

**Why it matters:** Informed traders leave measurable fingerprints in order flow BEFORE news breaks publicly.

### Signal 2: Orderbook Spread & Depth

**Source:** `src/signals/microstructure.py` | **Input:** Polymarket orderbook snapshots

Analyzes the liquidity structure (top 5 levels) on both sides of the book.

```python
depth_YES = sum(size for top 5 bid levels)
depth_NO  = sum(size for top 5 ask levels)
depth_imbalance = (depth_YES - depth_NO) / (depth_YES + depth_NO)  # [-1, +1]

LR = exp(depth_imbalance * 0.5)            # Mild signal, capped at [0.5, 2.0]
```

Wide spreads (> 5% of mid-price) halve the signal strength — high uncertainty reduces informativeness.

### Signal 3: Cross-Market Arbitrage (Kalshi, Metaculus, Manifold)

**Source:** `src/signals/cross_market.py` | **Input:** 3 independent prediction platforms

When multiple independent platforms disagree with Polymarket in the same direction, that's real alpha.

```python
# For each available platform:
delta = platform_price - polymarket_price

# Count agreements: how many deltas exceed 5% in the same direction
source_multiplier = {1: 0.7, 2: 1.0, 3: 1.3}[n_sources_agree]
LR = exp(direction * mean_abs_delta * source_multiplier * 3.0)
```

**Calibration:** 2 sources agreeing with 15% divergence produces LR ~ 2.5. Requires at least 2 sources agreeing for a strong signal; single-source signals are dampened by 0.5x.

### Signal 4: News Relevance (RSS — 15 Feeds)

**Source:** `src/signals/news_relevance.py` | **Input:** Reuters, AP, BBC, CNN, Guardian, NPR, FT, Politico, WSJ, NYT + 5 more

TF-IDF-inspired keyword matching combined with lexicon-based sentiment analysis.

```python
relevance = sum(keyword_match * log(1 + word_count)) + question_overlap   # [0, 1]
sentiment = (positive_words - negative_words) / total_sentiment_words      # [-1, +1]

# Uncertainty penalty: articles with "may", "might", "unclear" halve confidence
if uncertainty_word_count > 2:
    confidence *= 0.5

LR = exp(sentiment * relevance * confidence * 2.5)
```

**Calibration:** Highly relevant + strongly positive article produces LR ~ 3.5. Multiple articles are aggregated via log-space weighted average (weighted by relevance).

### Signal 5: GDELT Global News (100+ Sources)

**Source:** `src/signals/news_relevance.py` + `src/ingestion/gdelt.py` | **Input:** GDELT GKG 2.0 batch

GDELT processes 100+ global news sources every 15 minutes, extracting themes (`ECON_INFLATION`, `PROTEST`, etc.), named entities (persons, organizations, locations), and Goldstein tone scores.

```python
relevance = keyword_match(persons, organizations, locations, themes)   # [0, 1]
tone_normalized = goldstein_tone / 50.0                                # [-1, +1]
confidence = min(activity_ref_density / 5.0, 1.0)

LR = exp(tone_normalized * relevance * confidence * 2.0)
```

**Why it matters:** GDELT covers sources that most traders never see — non-English media, regional outlets, wire services from 100+ countries.

### Signal 6: LLM Superforecaster Decomposition

**Source:** `src/reasoning/decomposer.py` | **LLM Chain:** Groq (Llama 3.3 70B) → Gemini 1.5 Flash → Ollama local

Instead of asking "is this bullish?" (what everyone else does), we implement the full **Good Judgment Project superforecaster methodology**:

1. **Parse** the exact resolution criteria — what must be true for YES?
2. **Decompose** into 3–5 independent sub-claims
3. **Estimate** P(each sub-claim) with explicit step-by-step reasoning
4. **Calculate** joint P(YES) from inside view (specific evidence)
5. **Anchor** with outside view: `blended = 0.70 * inside_view + 0.30 * historical_base_rate`
6. **Output** calibrated P(YES) + 90% confidence interval

**Likelihood Ratio:**

```python
prior_odds     = market_price / (1 - market_price)
posterior_odds = blended_probability / (1 - blended_probability)
LR = posterior_odds / prior_odds
```

**Temperature:** 0.1 — probability estimation is deterministic, not creative.

**Confidence** derived from CI width: `confidence = max(0.3, 1.0 - ci_width * 2)`. Narrow CI = high confidence.

### Signal 7: Wikipedia Edit Velocity

**Source:** `src/ingestion/wikipedia.py` | **Input:** Wikipedia Recent Changes API

Wikipedia editors (a crowd of thousands monitoring news feeds) update articles **5–15 minutes before** mainstream media publishes stories.

```python
baseline_rate = edits_last_60min / 12         # Average 5-minute rate over last hour
velocity = edits_last_5min / baseline_rate
is_spiking = (velocity >= 3.0) and (edits_last_5min >= 3)

LR = min(1.0 + (velocity - 3.0) * 0.1, 1.5)  # Capped at 1.5
```

A spike means *something is happening* — but doesn't tell us direction. The capped LR amplifies confidence in whatever direction other signals indicate.

### Signal 8: Reddit Social Sentiment

**Source:** `src/ingestion/reddit.py` | **Input:** 6 subreddits (public JSON API, no OAuth needed)

```python
sentiment = (positive_word_count - negative_word_count) / total    # [-1, +1]
LR = exp(sentiment * 0.8)
confidence = 0.35             # Reddit is noisy
```

Intentionally low confidence (0.35). Reddit is a noisy contrarian indicator at best, but occasionally provides early crowd signals before professional media.

---

## Bayesian Confidence Scoring

**Source:** `src/fusion/bayesian.py`

### Core Framework

The fusion engine uses **multiplicative Bayesian updating in log-odds space** — the mathematically correct way to combine independent evidence.

**Step 1 — Prior from market price:**

```python
prior_odds     = market_price / (1 - market_price)
prior_log_odds = log(prior_odds)
```

**Step 2 — Compute effective likelihood ratio for each signal:**

```python
effective_LR_i = 1.0 + (raw_LR_i - 1.0) * confidence_i
```

This dampens the LR toward 1.0 (neutral) when confidence is low. A signal with `LR = 3.0` but `confidence = 0.5` contributes an effective LR of 2.0.

**Step 3 — Accumulate in log-odds space with correlation damping:**

```python
log_lr_sum = sum(log(effective_LR_i) * 0.85 for each signal)
```

The 0.85 damping factor accounts for the fact that signals share partial information.

**Step 4 — Compute posterior probability:**

```python
posterior_log_odds = prior_log_odds + log_lr_sum
posterior_prob     = exp(posterior_log_odds) / (1 + exp(posterior_log_odds))
posterior_prob     = clamp(posterior_prob, 0.01, 0.99)
```

**Step 5 — Compute edge:**

```python
edge           = posterior_prob - prior_prob
effective_edge = abs(edge) - 0.02          # Subtract Polymarket's 2% fee
```

A trade is triggered when `effective_edge >= 0.03` (3% minimum edge after fees).

### Why Log-Odds Space?

In probability space, combining evidence requires complex formulas. In log-odds space, Bayesian updating is simply **additive**:

```python
posterior_log_odds = prior_log_odds + sum(log(LR_i) for each signal)
```

This is numerically stable (no underflow near 0 or overflow near 1), makes the independence assumption transparent, and allows each signal to contribute independently.

### Correlation Damping (0.85x)

Signals are not truly independent — a breaking news article drives both the RSS score AND the GDELT tone score. Informed trading causes both the VPIN spike AND the depth imbalance shift.

The 0.85 damping factor is applied to each log-LR before summation:

```python
damped_log_lr_i = log(effective_LR_i) * 0.85
```

This is equivalent to assuming ~15% information overlap between any two signals. It prevents the posterior from becoming overconfident when multiple correlated signals fire simultaneously.

**Why not model the full covariance?** Full covariance estimation requires far more data than we have across diverse signal types. A scalar damping factor is simple, robust, and captures the essential insight that signals share information.

### 90% Confidence Interval

The CI is derived from **signal disagreement** — when signals point in different directions, uncertainty is high.

```python
log_lrs    = [log(effective_LR_i) for each signal]
std_log_lr = std(log_lrs)

# Delta method: map log-odds std to probability std
prob_std   = posterior * (1 - posterior) * std_log_lr

# 90% CI (z = 1.645)
half_width = 1.645 * max(prob_std, 0.02)
CI = [posterior - half_width, posterior + half_width]
```

**Wide CI** — signals disagree — less certain — smaller Kelly position.
**Narrow CI** — signals agree — more confident — larger position.

### Key Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `POLYMARKET_FEE` | 0.02 | 2% fee deducted from edge before trade decisions |
| `MIN_EDGE` | 0.03 | 3% minimum edge after fees to trigger a trade |
| `CORRELATION_DAMPING` | 0.85 | Per-signal log-LR discount for inter-signal correlation |

---

## Kelly Criterion Position Sizing

**Source:** `src/risk/kelly.py`

The Kelly criterion maximizes long-run geometric growth rate of the portfolio. We use **fractional Kelly (0.25x)** for robustness.

### Formula

For a YES trade when posterior > market price:

```python
b     = (1 - p_market) / p_market          # Gross payout odds per unit
b_net = b * (1 - 0.02)                     # Net of Polymarket's 2% fee

f_star = (b_net * p_posterior - q) / b_net  # Full Kelly fraction (q = 1 - p_posterior)

f_fractional = f_star * 0.25               # Fractional Kelly

position_usd = portfolio_value * f_fractional
position_usd = min(position_usd, portfolio_value * 0.05, 50.0)   # Risk caps
```

For a NO trade (posterior < market price), the same formula is applied symmetrically using the NO side's odds.

### Why 0.25x Kelly?

Full Kelly assumes you know the true probability exactly. Our estimates have uncertainty (reflected in the CI). Using 0.25x Kelly is equivalent to assuming our estimates are ~4x more uncertain than stated.

| Kelly Fraction | Expected Return | Max Drawdown | Variance |
|:-:|:-:|:-:|:-:|
| 1.00x (full) | 100% | Very high | Very high |
| 0.50x (half) | ~87% | High | High |
| **0.25x (ours)** | **~70%** | **Moderate** | **Low** |
| 0.10x | ~45% | Low | Very low |

0.25x retains ~70% of the expected return while dramatically cutting variance and drawdown risk. This is the right tradeoff when probability estimates have meaningful uncertainty.

### Portfolio Diversification

When holding multiple simultaneous positions, an additional diversification discount prevents overexposure:

```python
diversification_discount = 1.0 / sqrt(n_positions)
adjusted_fraction = 0.25 * diversification_discount
```

### Risk Limits

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_position_usd` | $50 | Hard cap on any single position |
| `max_portfolio_exposure` | 25% | Maximum total portfolio at risk |
| `kelly_fraction` | 0.25 | Fractional Kelly multiplier |
| `min_edge_threshold` | 3% | Minimum edge after fees to trigger trade |
| `polymarket_fee` | 2% | Fee on profits, deducted from edge |

---

## Live Dashboard

The web dashboard provides real-time visualization of all 8 signals via WebSocket.

```bash
python scripts/run_agent.py       # Full agent + dashboard at http://localhost:8080
python scripts/run_dashboard.py   # Standalone demo (no API keys needed)
```

### Features

- **Signal Radar Chart** — 8-axis radar showing each signal's current strength and direction in real time, color-coded by net directional bias
- **8-Signal Grid** — per-market card view of all signals with LR value, strength bars, confidence bars, and active/inactive status indicators
- **Signal Dots** — inline market table shows 8 colored dots per market indicating which signals are active (green = YES, red = NO, gray = inactive)
- **Bayesian Visualization** — prior → posterior bar chart with 90% confidence interval overlay
- **P&L Equity Curve** — real-time chart with green/red coloring based on cumulative performance
- **Activity Log** — live feed of trades, Wikipedia spikes, cycle events, errors with color-coded entries
- **Portfolio KPIs** — topbar with P&L %, total value, trades executed, win rate, active signal count, uptime

All data flows through a WebSocket pub/sub system (`src/api/state.py`) — zero polling, instant updates.

---

## Backtesting

```bash
python scripts/run_backtest.py
```

The backtest engine:

1. Fetches resolved markets from Polymarket's Gamma API (with hardcoded fallback for reliability)
2. Simulates all 8 signal types for each market using statistical proxies
3. Runs full Bayesian fusion + Kelly sizing pipeline
4. Reports accuracy, P&L, calibration by probability bucket, and a detailed trade log

---

## Testing

```bash
pytest tests/ -v
```

**36 tests** covering the mathematical core:

- **`test_bayesian.py`** (13 tests) — no signals → posterior = prior, bullish/bearish updates, bound checking, neutral LR passthrough, opposing signal cancellation, edge calculation, CI computation, trade direction thresholds
- **`test_kelly.py`** (11 tests) — no edge → no trade, YES/NO direction, size = portfolio * kelly\_f * fraction, USD and % caps, non-negative kelly, EV correctness, fee math
- **`test_microstructure.py`** (12 tests) — VPIN equal-volume bucketing, OFI bounds \[-1, +1\], VPIN > 0.4 informed detection, spread LR calculation, OFI-to-LR direction mapping

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                      DATA INGESTION LAYER                       │
│  Polymarket WS (trades)  │  Polymarket REST (orderbook)        │
│  Kalshi REST  │  Metaculus API  │  Manifold Markets API        │
│  GDELT GKG 2.0 (100+ sources)  │  RSS (15 feeds)              │
│  Wikipedia Recent Changes  │  Reddit (6 subreddits)            │
│  Resolution RSS (BLS, Fed, FDA)                                │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SIGNAL PROCESSING LAYER                       │
│  Signal 1: VPIN (informed trading)     → LR via exp(k * OFI)  │
│  Signal 2: Spread/Depth (liquidity)    → LR via depth_imb     │
│  Signal 3: Cross-Market (3 platforms)  → LR via divergence     │
│  Signal 4: News RSS (15 feeds)         → LR via TF-IDF + sent │
│  Signal 5: GDELT (100+ sources)        → LR via tone scoring  │
│  Signal 6: LLM Superforecaster         → LR via decomposition │
│  Signal 7: Wikipedia Velocity          → LR via edit spike     │
│  Signal 8: Reddit Sentiment            → LR via lexicon        │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BAYESIAN FUSION ENGINE                        │
│  Prior = Polymarket price (crowd wisdom)                       │
│  Each signal = likelihood ratio (not a score)                  │
│  Posterior computed in log-odds space                           │
│  Correlation damping: 0.85x per signal                         │
│  Output: P(YES), 90% CI, edge, effective_edge, trade_direction │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  RISK: Fractional Kelly (0.25x) │ Max $50/position │ 25% cap  │
│  EXEC: Paper trading (default)  │ Live CLOB (opt-in)          │
│  MONITOR: Real-time web dashboard (WebSocket) + terminal UI    │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```text
polymarket-news-bot/
├── config/
│   ├── settings.py              # Pydantic BaseSettings from .env
│   └── markets.yaml             # Market configs + signal weights
├── src/
│   ├── ingestion/               # Data source clients
│   │   ├── polymarket.py        # CLOB WebSocket + REST
│   │   ├── gdelt.py             # GDELT GKG 2.0 batch parser
│   │   ├── rss.py               # 15-feed async RSS monitor
│   │   ├── wikipedia.py         # Edit velocity tracker
│   │   └── reddit.py            # Social sentiment (public JSON)
│   ├── signals/                 # Signal → Likelihood Ratio converters
│   │   ├── microstructure.py    # VPIN + spread/depth
│   │   ├── cross_market.py      # Kalshi/Metaculus/Manifold arb
│   │   ├── news_relevance.py    # TF-IDF + sentiment → LR
│   │   └── resolution.py        # Resolution source monitoring
│   ├── reasoning/               # LLM integration
│   │   ├── llm_client.py        # Groq → Gemini → Ollama fallback
│   │   ├── decomposer.py        # Superforecaster methodology
│   │   └── prompts.py           # Calibrated prompt engineering
│   ├── fusion/                  # Bayesian engine
│   │   ├── bayesian.py          # Log-odds fusion + CI computation
│   │   └── ensemble.py          # Signal aggregation → BayesianResult
│   ├── risk/                    # Position sizing
│   │   ├── kelly.py             # Fractional Kelly with fees
│   │   └── portfolio.py         # Position tracking, P&L, exposure
│   ├── execution/               # Order execution
│   │   ├── clob.py              # Live Polymarket CLOB
│   │   ├── orders.py            # Paper/live router
│   │   └── paper.py             # Paper trading with slippage sim
│   ├── monitor/
│   │   └── dashboard.py         # Rich terminal UI
│   └── api/                     # Web dashboard
│       ├── state.py             # Shared state + WebSocket pub/sub
│       ├── server.py            # FastAPI REST + WebSocket
│       └── static/              # HTML/CSS/JS (zero-framework)
├── scripts/
│   ├── run_agent.py             # Main agent loop
│   ├── run_dashboard.py         # Standalone demo dashboard
│   ├── run_backtest.py          # Historical backtest
│   └── demo_event.py            # Canned demo scenario
├── tests/                       # 36 tests
├── docs/
│   └── methodology.md           # Full mathematical derivations
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## What Makes This Different

| What everyone else does | What we do |
|------------------------|-----------|
| RSS → GPT sentiment → score → trade | 8 independent signals → likelihood ratios → Bayesian posterior |
| "This news is 0.7 bullish" | `LR = exp(sentiment * relevance * confidence * k)` — mathematically correct |
| Single LLM call for sentiment | Structured superforecaster decomposition (sub-claims + base rate anchoring) |
| Check one market price | Cross-market arbitrage vs. Kalshi + Metaculus + Manifold simultaneously |
| Time-based trade signals | VPIN (volume-synchronized) detects informed traders before news breaks |
| Western English-only news | GDELT — 100+ global sources, 15-min updates, Goldstein tone + entity tagging |
| No pre-news signal | Wikipedia edit velocity — spikes 5–15 min before mainstream coverage |
| Fixed bet sizing | Fractional Kelly with proper fee math, diversification discount, and hard caps |
| Scores that can't be combined | Likelihood ratios that multiply correctly under Bayes' rule |

---

## Running Without API Keys

Everything works with **zero credentials** in paper trading mode:

- All 20+ data sources (Polymarket, Kalshi, Metaculus, Manifold, GDELT, RSS, Wikipedia, Reddit)
- Paper trading with full P&L tracking
- Web dashboard with real-time signal visualization
- Historical backtest
- Full demo script

The only optional key is for the LLM (superforecaster decomposition). Without one, the agent runs on the other 7 signals — still fully functional.

**To enable LLM (2 minutes, free):** Sign up at `console.groq.com`, create an API key, add `GROQ_API_KEY=gsk_...` to your `.env`. Or install Ollama locally (`ollama pull llama3.2`) for zero cloud dependency.
