# Setup & API Keys Guide

This guide covers everything you need to go from zero to a running agent.
**TL;DR:** The entire system works with zero API keys in paper/demo mode. Keys only add LLM quality and live trading.

---

## What You Actually Need

| Credential | Required for | Cost | Time to get |
|-----------|-------------|------|-------------|
| **Nothing** | Demo, dashboard, paper trading, backtesting | Free | 0 min |
| `GROQ_API_KEY` | LLM superforecaster decomposition (best quality) | Free | 2 min |
| `GEMINI_API_KEY` | LLM fallback if Groq hits rate limit | Free | 3 min |
| Ollama (local) | LLM fallback, fully offline | Free | 5 min |
| `POLYMARKET_*` (5 fields) | Live real-money trading only | Free account | 10 min |

---

## Step 1 — Install

```bash
# Python 3.11+ required
python --version   # should show 3.11.x or 3.12.x

# Clone and install
git clone https://github.com/tharune/polymarket-news-bot.git
cd polymarket-news-bot
pip install -e .

# Copy the environment template
cp .env.example .env
```

---

## Step 2 — Run immediately (no keys)

```bash
# Terminal demo — replays Fed rate cut 2024 event end-to-end (~30 seconds)
python scripts/demo_event.py

# Web dashboard with realistic seeded data — open http://localhost:8080
python scripts/run_dashboard.py
```

Both of these work with a completely empty `.env`. No credentials, no setup.

---

## Step 3 — Add a free LLM key (recommended, 2 minutes)

The LLM enables the superforecaster decomposition signal. Without it the agent still runs on microstructure + news + cross-market signals — just missing one of the 8 inputs.

### Option A — Groq (fastest, recommended)

1. Go to **[console.groq.com](https://console.groq.com)**
2. Sign in with Google (or create account)
3. Click **API Keys** → **Create API Key**
4. Copy the key (starts with `gsk_`)
5. Add to `.env`:

```env
GROQ_API_KEY=gsk_your_key_here
```

**Free tier:** 14,400 requests/day, 6,000 tokens/minute. More than enough for continuous trading.
Model used: `llama-3.3-70b-versatile` — the best open-weights model available.

---

### Option B — Ollama (fully local, no internet required)

1. Download from **[ollama.ai](https://ollama.ai)** (macOS/Linux/Windows)
2. Install and open the app
3. Pull the model once:

```bash
ollama pull llama3.2
```

4. No `.env` changes needed — it auto-detects Ollama at `localhost:11434`

**Free tier:** Unlimited. Runs entirely on your machine. Slower than Groq but no rate limits or internet dependency.

---

### Option C — Google Gemini (fallback)

1. Go to **[aistudio.google.com](https://aistudio.google.com)**
2. Sign in with your Google account
3. Click **Get API key** → **Create API key in new project**
4. Copy the key (starts with `AIza`)
5. Add to `.env`:

```env
GEMINI_API_KEY=AIza_your_key_here
```

**Free tier:** 1,500 requests/day, 1 million tokens/day. Used as automatic fallback if Groq hits its limit.

---

## Step 4 — Run the full agent

```bash
# Paper trading mode — runs fully, places simulated trades, opens dashboard
python scripts/run_agent.py
# → open http://localhost:8080
```

The agent will:
- Fetch the top 20 markets by liquidity from Polymarket
- Run the full signal pipeline every 60 seconds
- Ingest RSS, Wikipedia, GDELT, Kalshi, Metaculus, Manifold in the background
- Display everything in real-time on the web dashboard

---

## Step 5 — Live trading (optional)

Live trading requires a Polymarket account with USDC funding on Polygon.

### Create a Polymarket account

1. Go to **[polymarket.com](https://polymarket.com)**
2. Sign in with Google or connect a wallet
3. Complete identity verification if prompted

### Get API credentials

1. In Polymarket, click your profile → **Settings** → **API**
2. Click **Create new API key**
3. Copy all four values:

```env
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
POLYMARKET_API_PASSPHRASE=your_passphrase
```

### Get your wallet credentials

Polymarket uses a Polygon (MATIC) wallet. You'll need your private key and funder address.

If you're using a dedicated trading wallet (recommended):
1. Create a new MetaMask wallet
2. Export the private key: MetaMask → Account Details → Export Private Key
3. Your funder address is the wallet address (starts with `0x`)

```env
POLYMARKET_PRIVATE_KEY=0x_your_private_key
POLYMARKET_FUNDER_ADDRESS=0x_your_wallet_address
```

### Fund the wallet

1. Bridge USDC to Polygon at **[wallet.polymarket.com](https://wallet.polymarket.com)**
2. Minimum recommended: $100 USDC (agent caps positions at $50 by default)

### Enable live mode

```env
TRADING_MODE=live
```

**Important:** Start with `TRADING_MODE=paper` and verify the agent behaves as expected before enabling live. The paper trading P&L reflects exactly what live trades would have done.

---

## All Available Settings

Copy this to your `.env` and fill in what you need. Everything has a safe default.

```env
# ── LLM (at least one recommended) ────────────────────────────────────────────
GROQ_API_KEY=                        # Groq Llama 3.3 70B — primary LLM
GEMINI_API_KEY=                      # Google Gemini 1.5 Flash — fallback
OLLAMA_BASE_URL=http://localhost:11434   # Ollama local — auto-detected
OLLAMA_MODEL=llama3.2                # Local model to use

# ── Polymarket Live Trading (leave blank for paper mode) ──────────────────────
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_PRIVATE_KEY=
POLYMARKET_FUNDER_ADDRESS=

# ── Trading Mode ──────────────────────────────────────────────────────────────
TRADING_MODE=paper                   # "paper" or "live"

# ── Risk Limits ───────────────────────────────────────────────────────────────
MAX_POSITION_SIZE_USD=50             # Hard cap per position in USD
MAX_PORTFOLIO_EXPOSURE=0.25          # Max 25% of portfolio in open positions
MIN_EDGE_THRESHOLD=0.03              # Minimum edge (after fees) to trade
KELLY_FRACTION=0.25                  # 0.25x fractional Kelly safety factor

# ── Agent Behavior ────────────────────────────────────────────────────────────
SIGNAL_REFRESH_SECONDS=60            # How often to re-evaluate each market
LLM_TIMEOUT_SECONDS=30              # Max wait for LLM response before fallback
LOG_LEVEL=INFO                       # DEBUG / INFO / WARNING
```

---

## Data Sources (zero setup required)

These all work automatically — no keys, no signups:

| Source | What it provides | Update frequency |
|--------|-----------------|-----------------|
| Polymarket REST | All open markets, prices, orderbook | On demand |
| Polymarket WebSocket | Live trade stream (for VPIN) | Real-time |
| Kalshi REST | Independent event prices | On demand |
| Metaculus API | Expert community forecasts | On demand |
| Manifold Markets | Crowd prediction prices | On demand |
| GDELT GKG 2.0 | 100+ global news sources + sentiment | Every 15 min |
| Reuters RSS | World, politics, business news | Every 60 sec |
| AP RSS | Top news | Every 60 sec |
| BBC RSS | World and business news | Every 60 sec |
| CNN RSS | Top stories | Every 60 sec |
| Guardian RSS | World, politics, business | Every 60 sec |
| NPR RSS | News | Every 60 sec |
| FT RSS | Markets | Every 60 sec |
| Politico RSS | Politics | Every 60 sec |
| WSJ RSS | World news | Every 60 sec |
| NYT RSS | World news | Every 60 sec |
| Wikipedia API | Edit velocity (pre-news signal) | Every 2 min |
| Reddit (public) | r/PredictionMarkets, r/worldnews | Every 5 min |
| BLS/FED/FDA RSS | Resolution source monitoring | On release |

---

## Running Each Mode

```bash
# ── Standalone web dashboard (demo data, no keys) ─────────────────────────────
python scripts/run_dashboard.py
# → http://localhost:8080

# ── Full autonomous agent + live dashboard ────────────────────────────────────
python scripts/run_agent.py
# → http://localhost:8080

# ── Terminal demo (judge-ready, ~30 seconds) ──────────────────────────────────
python scripts/demo_event.py

# ── Historical backtest ───────────────────────────────────────────────────────
python scripts/run_backtest.py

# ── Test suite ────────────────────────────────────────────────────────────────
pytest tests/ -v    # 36/36 should pass
```

---

## Docker

```bash
cp .env.example .env   # add any keys you have

# Full agent + dashboard on :8080
docker compose up agent

# Dashboard only (demo data, no keys needed)
docker compose --profile dashboard up

# Terminal demo
docker compose --profile demo up
```

---

## Troubleshooting

**"LLM providers available: []"**
→ No LLM key configured. Add `GROQ_API_KEY` or install Ollama. The agent still runs — it just skips the LLM decomposition signal.

**Dashboard shows "connecting…" forever**
→ Make sure the agent or dashboard script is running. The WebSocket connects to the same process serving the dashboard.

**"Insufficient cash" on trades**
→ The paper portfolio starts at $1,000 with a 25% exposure cap ($250 total). This is intentional risk management.

**GDELT fetch failed**
→ GDELT updates every 15 minutes. If it fails, it silently retries next cycle. Not critical — 14 other news sources continue running.

**Kalshi/Metaculus/Manifold return no data**
→ These APIs use fuzzy keyword matching to find relevant markets. If no matching market is found, the cross-market signal defaults to LR=1.0 (no update). Normal behavior.
