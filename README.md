# Polymarket News Bot

Autonomous Polymarket trading agent built on **Bayesian signal fusion**, **VPIN microstructure analysis**, **cross-market arbitrage detection**, and **LLM superforecaster decomposition**.

Most teams do: RSS → GPT sentiment score → trade.
We do: 8 independent signal sources → likelihood ratios → Bayesian posterior → Kelly-sized position.

---

## Quick Start

```bash
# Install (Python 3.11+)
pip install -e .

# Copy env template
cp .env.example .env

# ── Option 1: Judge demo (no credentials needed, ~30 seconds) ──
python scripts/demo_event.py

# ── Option 2: Web dashboard with realistic demo data ──
python scripts/run_dashboard.py
# → open http://localhost:8080

# ── Option 3: Full autonomous agent + live dashboard ──
python scripts/run_agent.py
# → open http://localhost:8080

# ── Option 4: Historical backtest ──
python scripts/run_backtest.py

# ── Run tests ──
pytest tests/ -v   # 36/36 pass
```

**Or with Docker:**
```bash
cp .env.example .env
docker compose up agent          # full agent + dashboard on :8080
docker compose --profile dashboard up  # demo dashboard only, no API keys needed
docker compose --profile demo up       # terminal demo
```

---

## Web Dashboard

A real-time monitoring dashboard runs at `http://localhost:8080` alongside the agent.

**Live panels:**
- **Portfolio** — current value, P&L %, open positions, fees paid
- **P&L chart** — equity curve updated every cycle
- **Market Analysis** — all tracked markets with prior → posterior, edge, 90% CI, and trade direction. Click any row to expand the full signal breakdown with likelihood ratio bars and a visual Bayesian update diagram
- **Activity Log** — real-time feed of trades, Wikipedia spikes, cycle completions, and errors

No credentials needed to see the dashboard — run `python scripts/run_dashboard.py` to populate it with realistic demo data instantly.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA INGESTION LAYER                      │
│  GDELT (15min)  RSS (15 feeds)  Wikipedia  Reddit           │
│  Polymarket WS  Kalshi REST     Metaculus  Manifold          │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│                  SIGNAL PROCESSING LAYER                      │
│  MarketMicrostructure (VPIN + OFI + spread)                  │
│  CrossMarket (Kalshi vs Metaculus vs Manifold)               │
│  NewsRelevance (TF-IDF + sentiment × GDELT tone)             │
│  LLM Decomposer (superforecaster methodology, Groq 70B)      │
│  Wikipedia (edit velocity → signal amplifier)                │
│  ResolutionCrawler (AP/Reuters/BLS/FED RSS)                  │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│                  BAYESIAN FUSION ENGINE                       │
│  Prior = Polymarket price  |  Each signal = likelihood ratio │
│  Posterior in log-odds space with correlation damping (0.85) │
│  Output: posterior P(YES), 90% CI, edge, trade direction     │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  RISK: Fractional Kelly (0.25×) | Max exposure 25%          │
│  EXEC: Paper trading (default) | Live CLOB (opt-in)         │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Sources

| Source | Signal | Latency | Auth |
|--------|--------|---------|------|
| Polymarket CLOB REST | Market prices, orderbook | <1s | None |
| Polymarket CLOB WebSocket | Live trades (for VPIN) | Real-time | None |
| Kalshi REST | Independent event prices | <5s | None |
| Metaculus API | Expert community forecasts | ~1min | None |
| Manifold Markets | Crowd prediction prices | <1s | None |
| GDELT GKG 2.0 | 100+ global news sources + tone scores | 15min | None |
| RSS (15 feeds) | Reuters, AP, BBC, CNN, Guardian, NPR, FT, Politico, WSJ, NYT | <1min | None |
| Wikipedia Recent Changes | Edit velocity (pre-news signal) | Real-time | None |
| Reddit (public JSON) | r/PredictionMarkets, r/worldnews sentiment | ~5min | None |
| Gov RSS (BLS/FED/FDA) | Resolution source monitoring | On release | None |

**20+ data sources. Zero authentication required for paper trading.**

### LLM Providers (all free-tier)

| Provider | Model | Speed | Daily Limit |
|----------|-------|-------|-------------|
| Groq (primary) | Llama 3.3 70B Versatile | ~500 tok/s | 14,400 req |
| Google Gemini (fallback) | Gemini 1.5 Flash | fast | 1,500 req |
| Ollama (local fallback) | Llama 3.2 3B | local | unlimited |

Automatic fallback chain. Agent never stalls on LLM calls.

---

## Mathematical Framework

### 1. Bayesian Signal Fusion

The crowd price is the prior. Each signal updates beliefs via a **likelihood ratio** — not a score, not a label.

```
prior_odds = p / (1 − p)

# Multiplicative update in log-odds space
log_posterior_odds = log(prior_odds) + Σ [ log(LR_i) × confidence_i × 0.85 ]

posterior_prob = sigmoid(log_posterior_odds)
edge            = posterior_prob − prior_prob
effective_edge  = |edge| − 0.02   (Polymarket fee)
```

The **0.85 correlation damping** prevents overconfidence when signals share information (they often do — news drives both RSS and GDELT).

### 2. VPIN — Informed Trading Detection

Adapted from Easley, Lopez de Prado & O'Hara (2012). Detects when informed traders are active *before* news breaks publicly.

```
# Partition trades into n equal-volume buckets
VPIN = mean( |YES_vol_bucket − NO_vol_bucket| ) / bucket_size

# VPIN > 0.4 → informed trading active
# Combined with order flow imbalance for direction:
LR = exp( 2.0 × OFI × vpin_strength )
```

Equal-volume bucketing is more robust than time-based windows — it normalizes for varying market activity.

### 3. Superforecaster LLM Decomposition

Not sentiment analysis. Full Good Judgment Project methodology:

1. Parse exact resolution criteria
2. Identify 3-5 independent sub-claims that jointly determine resolution
3. Estimate `P(sub-claim)` with explicit reasoning
4. Blend inside view (70%) with outside view base rate (30%)
5. Output calibrated `P(YES)` + 90% confidence interval

```python
# LLM output → likelihood ratio
prior_odds   = market_price / (1 − market_price)
llm_odds     = llm_estimate / (1 − llm_estimate)
lr           = llm_odds / prior_odds
```

Temperature = 0.1. Probability estimation is not creative.

### 4. Cross-Market Arbitrage

```
Δ_kalshi    = kalshi_price  − polymarket_price
Δ_metaculus = metaculus_prob − polymarket_price
Δ_manifold  = manifold_prob  − polymarket_price

# Strong signal: ≥2 sources agree, magnitude > 5%
LR = exp( direction × magnitude × source_multiplier × 3.0 )

source_multiplier: {1: 0.7,  2: 1.0,  3: 1.3}
```

Calibrated so that 2-source 20% divergence → LR ≈ 1.82.

### 5. Edge and Position Sizing

```python
# Filter: trade only when effective edge clears fee + buffer
effective_edge = |edge| − 0.02   # Polymarket 2% fee
if effective_edge < 0.03:
    return NO_TRADE

# Fractional Kelly (0.25× safety factor)
b = payout_odds * (1 − fee)       # correct fee treatment
kelly_f = (b * p − q) / b
position = portfolio * kelly_f * 0.25

# Hard caps
position = min(position, 0.05 × portfolio, $50)
```

### 6. Confidence Interval

CI from signal *disagreement* — wide when signals conflict, narrow when they agree:

```python
std_log_lr = std([ log(eff_lr) for signal in signals ])
prob_std   = posterior × (1 − posterior) × std_log_lr
half_width = 1.645 × prob_std    # 90% CI
```

---

## Demo

Run `python scripts/demo_event.py` to replay a real historical event end-to-end:

**Scenario:** "Will the Fed cut rates in March 2024?"

| Step | What Happens |
|------|-------------|
| 1 | Market fetched: Polymarket price = **18% YES** |
| 2 | Reuters: "CPI rises 0.4%, above forecast" → sentiment −0.6, relevance 0.85 |
| 3 | AP: "Powell signals no rush to cut rates" → sentiment −0.75, relevance 0.95 |
| 4 | Wikipedia spike: Federal_Reserve page — 8 edits/5min **(4.2× baseline)** |
| 5 | Kalshi=12%, Metaculus=10%, Manifold=15% — all more bearish than Polymarket |
| 6 | VPIN=0.52 → informed trading active. OFI=−0.38 → **NO pressure** |
| 7 | LLM: 3 sub-claims decomposed → P(YES)=15%, CI=[8%, 25%] |
| 8 | Bayesian fusion: **18% → 4.3%** posterior |
| 9 | Kelly: BUY NO, **$50 position** @ 0.822 |
| ✓ | Fed did NOT cut in March 2024. Trade profitable. |

---

## File Structure

```
polymarket-news-bot/
├── config/
│   ├── settings.py           # Pydantic BaseSettings from .env
│   └── markets.yaml          # Market configs + signal weights
├── src/
│   ├── ingestion/
│   │   ├── polymarket.py     # CLOB WebSocket + REST client
│   │   ├── gdelt.py          # GDELT GKG 2.0 (15-min global news)
│   │   ├── rss.py            # 15-feed async RSS monitor
│   │   ├── wikipedia.py      # Edit velocity signal
│   │   └── reddit.py         # Social sentiment via public JSON API
│   ├── signals/
│   │   ├── microstructure.py # VPIN, order flow imbalance, spread
│   │   ├── cross_market.py   # Kalshi / Metaculus / Manifold comparison
│   │   ├── news_relevance.py # TF-IDF article scoring → likelihood ratio
│   │   └── resolution.py     # Resolution source RSS crawler
│   ├── reasoning/
│   │   ├── llm_client.py     # Groq → Gemini → Ollama fallback chain
│   │   ├── decomposer.py     # Superforecaster decomposition
│   │   └── prompts.py        # Engineered system + user prompts
│   ├── fusion/
│   │   ├── bayesian.py       # Log-odds fusion with correlation damping
│   │   └── ensemble.py       # Assembles MarketSignalBundle → SignalUpdates
│   ├── risk/
│   │   ├── kelly.py          # Fractional Kelly with correct fee math
│   │   └── portfolio.py      # Position tracking, exposure limits, P&L
│   ├── execution/
│   │   ├── clob.py           # Live Polymarket CLOB (py-clob-client)
│   │   ├── orders.py         # Paper/live router
│   │   └── paper.py          # Paper trading simulator with slippage
│   ├── monitor/
│   │   └── dashboard.py      # Rich terminal UI
│   └── api/
│       ├── state.py          # Shared agent state + WebSocket pub/sub
│       ├── server.py         # FastAPI server (REST + WebSocket)
│       └── static/           # Dashboard HTML/CSS/JS (no framework)
├── scripts/
│   ├── run_agent.py          # Main agent loop + web dashboard
│   ├── run_dashboard.py      # Standalone dashboard (demo data, no keys)
│   ├── run_backtest.py       # Historical backtest on resolved markets
│   └── demo_event.py         # Canned judge demo (Fed rate cut 2024)
├── tests/
│   ├── test_bayesian.py      # 13 tests — Bayesian properties, CI, LR scaling
│   ├── test_kelly.py         # 11 tests — Kelly math, caps, edge thresholds
│   └── test_microstructure.py # 12 tests — VPIN, OFI, spread signal
├── docs/
│   └── methodology.md        # Full mathematical write-up with derivations
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## What Makes This Different

| What everyone else does | What we do |
|------------------------|-----------|
| RSS → GPT sentiment → score → trade | 8 independent signals → likelihood ratios → Bayesian posterior |
| "This news is 0.7 bullish" | `LR = exp(sentiment × relevance × confidence × k)` |
| Single LLM call for sentiment | Structured superforecaster decomposition (sub-claims + base rates) |
| Check one market price | Cross-market arbitrage vs. Kalshi + Metaculus + Manifold simultaneously |
| Time-based trade signals | VPIN (volume-synchronized) detects informed traders before news breaks |
| No news source used by any other team | GDELT — 100+ global sources, 15-min updates, tone + entity tagging |
| No pre-news signal | Wikipedia edit velocity — spikes 5-15 min before mainstream coverage |
| Fixed bet sizing | Fractional Kelly with proper fee math and diversification discount |

---

## Running Without API Keys

Everything below works with **zero credentials** in paper trading mode:

- All 20+ data sources (Polymarket, Kalshi, Metaculus, Manifold, GDELT, RSS, Wikipedia, Reddit)
- Paper trading with full P&L tracking
- Web dashboard with real-time updates
- Historical backtest
- Full demo script

The only thing that needs a key is the LLM (for superforecaster decomposition). Without one, the agent skips that signal and runs on microstructure + news + cross-market — still fully functional.

**To get the LLM working (2 minutes, free):** Sign up at `console.groq.com`, create an API key, add `GROQ_API_KEY=gsk_...` to your `.env`.

Or install Ollama (`ollama.ai`) locally and run `ollama pull llama3.2` — zero cloud dependency.
