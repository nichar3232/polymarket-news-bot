export interface Signal {
  source: string
  lr: number
  eff_lr: number
  confidence: number
  notes: string
}

export interface Analysis {
  market_id: string
  question: string
  prior: number
  posterior: number
  edge: number
  effective_edge: number
  trade_direction: string
  ci_lower: number
  ci_upper: number
  signal_count: number
  signals: Signal[]
  timestamp: number
}

export interface Position {
  market_id: string
  direction: string
  size_usd: number
  entry_price: number
  current_price: number
  pnl: number
  pnl_pct: number
}

export interface Portfolio {
  total_value: number
  starting_value: number
  cash: number
  total_pnl: number
  total_pnl_pct: number
  exposure_usd: number
  exposure_pct: number
  total_trades: number
  win_rate: number
  fees_paid: number
  sharpe_ratio: number | null
  max_drawdown_pct: number | null
  profit_factor: number | null
  positions: Position[]
}

export interface AgentEvent {
  kind: string
  message: string
  ts: number
}

export interface NewsItem {
  title: string
  source: string
  relevance: number
  market_id: string
  ts: number
}

export interface PnLPoint {
  ts: number
  pnl_pct: number
}

export interface AgentConfig {
  risk: {
    max_position_usd: number
    max_portfolio_exposure_pct: number
    max_position_pct_per_trade: number
    kelly_fraction: number
  }
  engine: {
    polymarket_fee_pct: number
    min_signals: number
    min_effective_edge_pct: number
  }
}

export interface AgentState {
  trading_mode: string
  started_at: number
  config?: AgentConfig
  portfolio: Portfolio
  analyses: Analysis[]
  events: AgentEvent[]
  pnl_history: PnLPoint[]
  news: NewsItem[]
  selectedMarketId: string | null
  connected: boolean
  demoMode: boolean
}
