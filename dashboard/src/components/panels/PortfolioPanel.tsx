import { useAgent } from '../../context/AgentContext'
import './panels.css'

export function PortfolioPanel() {
  const { state } = useAgent()
  const p = state.portfolio
  const pnlColor = p.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'
  const cfg = state.config
  const maxExposure = cfg?.risk?.max_portfolio_exposure_pct ?? 25
  const maxPositionUsd = cfg?.risk?.max_position_usd ?? 50
  const minSignals = cfg?.engine?.min_signals ?? 2
  const minEffEdgePct = cfg?.engine?.min_effective_edge_pct ?? 2
  const kellyFraction = cfg?.risk?.kelly_fraction ?? 0.25
  const exposurePct = Math.min((p.exposure_pct / maxExposure) * 100, 100)

  return (
    <div className="panel">
      <div className="panel-title">Portfolio</div>

      <div className="pf-hero">
        <span className="pf-hero-value">${p.total_value.toFixed(2)}</span>
        <span className="pf-hero-pnl" style={{ color: pnlColor }}>
          {p.total_pnl >= 0 ? '+' : ''}{p.total_pnl.toFixed(2)} ({p.total_pnl_pct >= 0 ? '+' : ''}{p.total_pnl_pct.toFixed(2)}%)
        </span>
      </div>

      <div className="pf-grid">
        <div className="pf-cell">
          <span className="pf-cell-label">Cash</span>
          <span className="pf-cell-value">${p.cash.toFixed(2)}</span>
        </div>
        <div className="pf-cell">
          <span className="pf-cell-label">Exposure</span>
          <span className="pf-cell-value">${p.exposure_usd.toFixed(2)}</span>
        </div>
        <div className="pf-cell">
          <span className="pf-cell-label">Fees</span>
          <span className="pf-cell-value">${p.fees_paid.toFixed(2)}</span>
        </div>
        <div className="pf-cell">
          <span className="pf-cell-label">Exposure %</span>
          <span className="pf-cell-value">{p.exposure_pct.toFixed(1)}%</span>
        </div>
      </div>

      <div className="pf-bar">
        <div className="pf-bar-header">
          <span>RISK UTILIZATION</span>
          <span>{p.exposure_pct.toFixed(1)}% / {maxExposure}%</span>
        </div>
        <div className="pf-bar-track">
          <div
            className="pf-bar-fill"
            style={{
              width: `${exposurePct}%`,
              background: exposurePct > 80 ? 'var(--red)' : exposurePct > 50 ? 'var(--yellow)' : 'var(--green)',
            }}
          />
        </div>
      </div>

      <div className="pf-limits">
        <div className="pf-limit"><span className="pf-limit-label">Max Position</span><span className="pf-limit-value">${maxPositionUsd.toFixed(0)}</span></div>
        <div className="pf-limit"><span className="pf-limit-label">Min Eff Edge</span><span className="pf-limit-value">{minEffEdgePct.toFixed(1)}%</span></div>
        <div className="pf-limit"><span className="pf-limit-label">Min Signals</span><span className="pf-limit-value">{minSignals}</span></div>
        <div className="pf-limit"><span className="pf-limit-label">Kelly Frac.</span><span className="pf-limit-value">{kellyFraction.toFixed(2)}x</span></div>
      </div>
    </div>
  )
}
