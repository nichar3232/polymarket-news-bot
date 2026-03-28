import { useAgent } from '../../context/AgentContext'
import './panels.css'

export function PortfolioPanel() {
  const { state } = useAgent()
  const p = state.portfolio

  const rows = [
    { label: 'Total Value', value: `$${p.total_value.toFixed(2)}`, color: 'var(--text)' },
    { label: 'Cash', value: `$${p.cash.toFixed(2)}`, color: 'var(--text-mid)' },
    { label: 'Exposure', value: `$${p.exposure_usd.toFixed(2)}`, color: 'var(--amber)' },
    { label: 'Exposure %', value: `${p.exposure_pct.toFixed(1)}%`, color: p.exposure_pct > 15 ? 'var(--amber)' : 'var(--text-mid)' },
    { label: 'Fees Paid', value: `$${p.fees_paid.toFixed(2)}`, color: 'var(--text-dim)' },
  ]

  const maxExposure = 20
  const exposurePct = Math.min(p.exposure_pct / maxExposure * 100, 100)

  return (
    <div className="panel">
      <div className="panel-title">Risk Management</div>
      <div className="kv-grid">
        {rows.map(r => (
          <div key={r.label} className="kv-row">
            <span className="kv-label">{r.label}</span>
            <span className="kv-value" style={{ color: r.color }}>{r.value}</span>
          </div>
        ))}
      </div>
      <div className="exposure-bar-container">
        <div className="exposure-bar-label">
          <span>EXPOSURE</span>
          <span>{p.exposure_pct.toFixed(1)}% / {maxExposure}%</span>
        </div>
        <div className="exposure-bar-track">
          <div
            className="exposure-bar-fill"
            style={{
              width: `${exposurePct}%`,
              background: exposurePct > 80 ? 'var(--rose)' : exposurePct > 50 ? 'var(--amber)' : 'var(--green)',
            }}
          />
        </div>
      </div>
      <div className="safeguards">
        <div className="safeguard-row">
          <span className="safeguard-icon ok">&#10003;</span>
          <span>Max Position: $30.00</span>
        </div>
        <div className="safeguard-row">
          <span className={`safeguard-icon ${p.exposure_pct < maxExposure ? 'ok' : 'warn'}`}>
            {p.exposure_pct < maxExposure ? '\u2713' : '\u26A0'}
          </span>
          <span>Portfolio Cap: {maxExposure}%</span>
        </div>
        <div className="safeguard-row">
          <span className="safeguard-icon ok">&#10003;</span>
          <span>Min Edge: 5.0%</span>
        </div>
        <div className="safeguard-row">
          <span className="safeguard-icon ok">&#10003;</span>
          <span>Min Signals: 3</span>
        </div>
        <div className="safeguard-row">
          <span className="safeguard-icon ok">&#10003;</span>
          <span>Kelly Fraction: 0.25x</span>
        </div>
      </div>
    </div>
  )
}
