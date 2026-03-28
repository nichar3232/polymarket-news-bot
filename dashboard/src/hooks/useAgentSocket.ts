import { useEffect, useReducer, useCallback, useRef } from 'react'
import type { AgentState, AgentConfig, Analysis, AgentEvent, NewsItem, Portfolio } from '../types'
import { MOCK_STATE } from '../data/mockSnapshot'

const DEFAULT_CONFIG: AgentConfig = {
  risk: {
    max_position_usd: 50,
    max_portfolio_exposure_pct: 25,
    max_position_pct_per_trade: 5,
    kelly_fraction: 0.25,
  },
  engine: {
    polymarket_fee_pct: 2,
    min_signals: 2,
    min_effective_edge_pct: 2,
  },
}

const INITIAL: AgentState = {
  trading_mode: 'paper',
  started_at: Date.now() / 1000,
  config: DEFAULT_CONFIG,
  portfolio: { total_value: 0, starting_value: 0, cash: 0, total_pnl: 0, total_pnl_pct: 0, exposure_usd: 0, exposure_pct: 0, total_trades: 0, win_rate: 0, fees_paid: 0, sharpe_ratio: null, max_drawdown_pct: null, profit_factor: null, positions: [] },
  analyses: [],
  events: [],
  pnl_history: [],
  news: [],
  selectedMarketId: null,
  connected: false,
  demoMode: false,
}

type Action =
  | { type: 'snapshot'; data: any }
  | { type: 'portfolio'; data: Portfolio }
  | { type: 'analysis'; data: Analysis }
  | { type: 'event'; data: AgentEvent }
  | { type: 'news'; data: NewsItem }
  | { type: 'connected'; value: boolean }
  | { type: 'demo' }
  | { type: 'select_market'; id: string | null }

function reducer(state: AgentState, action: Action): AgentState {
  switch (action.type) {
    case 'snapshot': {
      const d = action.data
      const analyses = d.analyses ?? []
      const topEdge = analyses.reduce((best: Analysis | null, a: Analysis) =>
        !best || Math.abs(a.effective_edge) > Math.abs(best.effective_edge) ? a : best, null)
      return {
        ...state,
        trading_mode: d.trading_mode ?? state.trading_mode,
        started_at: d.started_at ?? state.started_at,
        config: d.config ?? state.config ?? DEFAULT_CONFIG,
        portfolio: d.portfolio ?? state.portfolio,
        analyses,
        events: d.events ?? [],
        pnl_history: d.pnl_history ?? [],
        news: d.news ?? [],
        selectedMarketId: state.selectedMarketId ?? topEdge?.market_id ?? null,
        connected: true,
        demoMode: false,
      }
    }
    case 'portfolio':
      return { ...state, portfolio: action.data }
    case 'analysis': {
      const existing = state.analyses.filter(a => a.market_id !== action.data.market_id)
      return { ...state, analyses: [...existing, action.data] }
    }
    case 'event':
      return { ...state, events: [action.data, ...state.events].slice(0, 200) }
    case 'news':
      return { ...state, news: [action.data, ...state.news].slice(0, 100) }
    case 'connected':
      return { ...state, connected: action.value }
    case 'demo': {
      const analyses = MOCK_STATE.analyses
      const topEdge = analyses.reduce((best: Analysis | null, a: Analysis) =>
        !best || Math.abs(a.effective_edge) > Math.abs(best.effective_edge) ? a : best, null)
      return {
        ...state,
        ...MOCK_STATE,
        config: state.config ?? DEFAULT_CONFIG,
        selectedMarketId: topEdge?.market_id ?? null,
        connected: false,
        demoMode: true,
      }
    }
    case 'select_market':
      return { ...state, selectedMarketId: action.id }
    default:
      return state
  }
}

export function useAgentSocket() {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)

  const selectMarket = useCallback((id: string | null) => {
    dispatch({ type: 'select_market', id })
  }, [])

  useEffect(() => {
    let closed = false

    function connect() {
      if (closed) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        retriesRef.current = 0
        dispatch({ type: 'connected', value: true })
      }

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          if (msg.type === 'snapshot') dispatch({ type: 'snapshot', data: msg.data })
          else if (msg.type === 'portfolio') dispatch({ type: 'portfolio', data: msg.data })
          else if (msg.type === 'analysis') dispatch({ type: 'analysis', data: msg.data })
          else if (msg.type === 'event') dispatch({ type: 'event', data: msg.data })
          else if (msg.type === 'news') dispatch({ type: 'news', data: msg.data })
        } catch { /* ignore malformed */ }
      }

      ws.onclose = () => {
        dispatch({ type: 'connected', value: false })
        if (closed) return
        retriesRef.current++
        if (retriesRef.current >= 10) {
          // Bug 2 fix: show demo data after 10 retries (~30s) instead of 3 (~7s)
          dispatch({ type: 'demo' })
          // Keep retrying in the background — if backend comes back, snapshot clears demoMode
          setTimeout(connect, 15000)
        } else {
          setTimeout(connect, Math.min(1000 * 2 ** retriesRef.current, 8000))
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      closed = true
      wsRef.current?.close()
    }
  }, [])

  return { state, selectMarket }
}
