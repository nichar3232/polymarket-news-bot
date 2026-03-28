import { useAgent } from '../context/AgentContext'
import { useClock } from '../hooks/useClock'
import './TopBar.css'

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="tb-stat">
      <span className="tb-stat-label">{label}</span>
      <span className="tb-stat-value" style={color ? { color } : undefined}>{value}</span>
    </div>
  )
}

export function TopBar() {
  const { state } = useAgent()
  const clock = useClock()
  const p = state.portfolio

  const pnlColor = p.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'
  const modeLabel = state.demoMode ? 'DEMO' : state.trading_mode.toUpperCase()

  return (
    <header className="topbar">
      <div className="tb-left">
        <span className="tb-brand">SIGNAL</span>
        <span className={`tb-mode ${modeLabel.toLowerCase()}`}>{modeLabel}</span>
        <span className={`tb-conn ${state.connected ? 'on' : ''}`}>
          <span className="tb-dot" />
          {state.connected ? 'CONNECTED' : 'OFFLINE'}
        </span>
      </div>

      <div className="tb-stats">
        <Stat
          label="P&L"
          value={`${p.total_pnl >= 0 ? '+' : ''}${p.total_pnl.toFixed(2)} (${p.total_pnl_pct >= 0 ? '+' : ''}${p.total_pnl_pct.toFixed(2)}%)`}
          color={pnlColor}
        />
        <div className="tb-divider" />
        <Stat label="NAV" value={`$${p.total_value.toFixed(2)}`} />
        <Stat label="TRADES" value={p.total_trades} />
        <Stat label="WIN RATE" value={`${p.win_rate.toFixed(1)}%`} />
        <Stat label="SHARPE" value={p.sharpe_ratio?.toFixed(2) ?? '\u2014'} />
        <Stat label="MAX DD" value={p.max_drawdown_pct != null ? `${p.max_drawdown_pct.toFixed(2)}%` : '\u2014'} />
        <Stat label="PROFIT F." value={p.profit_factor?.toFixed(2) ?? '\u2014'} />
      </div>

      <div className="tb-right">
        <span className="tb-clock">{clock.toLocaleTimeString('en-US', { hour12: false })}</span>
      </div>
    </header>
  )
}
