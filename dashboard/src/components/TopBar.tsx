import { useAgent } from '../context/AgentContext'
import { useClock } from '../hooks/useClock'
import './TopBar.css'

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={color ? { color } : undefined}>{value}</span>
    </div>
  )
}

export function TopBar() {
  const { state } = useAgent()
  const clock = useClock()
  const p = state.portfolio

  const pnlColor = p.total_pnl >= 0 ? 'var(--green)' : 'var(--rose)'
  const modeLabel = state.demoMode ? 'DEMO' : state.trading_mode.toUpperCase()
  const modeClass = state.demoMode ? 'mode-demo' : state.trading_mode === 'live' ? 'mode-live' : 'mode-paper'

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-brand">
          <span className="brand-icon">&#9670;</span>
          <span className="brand-name">POLYMARKET AGENT</span>
        </div>
        <div className={`topbar-mode ${modeClass}`}>{modeLabel}</div>
        <div className={`topbar-status ${state.connected ? 'connected' : ''}`}>
          <span className="status-dot" />
          <span>{state.connected ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </div>

      <div className="topbar-stats">
        <Stat label="P&L" value={`${p.total_pnl >= 0 ? '+' : ''}$${p.total_pnl.toFixed(2)}`} color={pnlColor} />
        <Stat label="P&L %" value={`${p.total_pnl_pct >= 0 ? '+' : ''}${p.total_pnl_pct.toFixed(2)}%`} color={pnlColor} />
        <Stat label="VALUE" value={`$${p.total_value.toFixed(2)}`} />
        <Stat label="TRADES" value={p.total_trades} />
        <Stat label="WIN" value={`${p.win_rate.toFixed(1)}%`} />
        <Stat label="SHARPE" value={p.sharpe_ratio?.toFixed(2) ?? '--'} />
        <Stat label="MAX DD" value={p.max_drawdown_pct != null ? `${p.max_drawdown_pct.toFixed(2)}%` : '--'} />
        <Stat label="PF" value={p.profit_factor?.toFixed(2) ?? '--'} />
      </div>

      <div className="topbar-right">
        <span className="topbar-clock">{clock.toLocaleTimeString('en-US', { hour12: false })}</span>
        <span className="topbar-date">{clock.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
      </div>
    </header>
  )
}
