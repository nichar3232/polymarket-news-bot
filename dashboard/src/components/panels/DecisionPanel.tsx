import { useAgent } from '../../context/AgentContext'

export function DecisionPanel() {
  const { state } = useAgent()
  const selected = state.analyses.find(a => a.market_id === state.selectedMarketId)

  if (!selected) return (
    <div className="panel">
      <div className="panel-title">Decision</div>
      <div className="no-data">Select a market</div>
    </div>
  )

  const dir = selected.trade_direction
  const actionLabel = dir === 'NONE' ? 'HOLD' : dir
  const edgeColor = selected.effective_edge >= 0.05 ? 'var(--green)' : selected.effective_edge > 0 ? 'var(--yellow)' : 'var(--text-dim)'

  return (
    <div className="panel">
      <div className="panel-title">Decision</div>
      <div className="dec-market">{selected.question}</div>

      <div className="dec-row">
        <div className="dec-metric">
          <span className="dec-label">Prior</span>
          <span className="dec-val dim">{(selected.prior * 100).toFixed(1)}%</span>
        </div>
        <span className="dec-arrow">→</span>
        <div className="dec-metric">
          <span className="dec-label">Posterior</span>
          <span className="dec-val">{(selected.posterior * 100).toFixed(1)}%</span>
        </div>
        <span className="dec-arrow">→</span>
        <div className="dec-metric">
          <span className="dec-label">Edge</span>
          <span className="dec-val" style={{ color: edgeColor }}>
            {selected.effective_edge >= 0 ? '+' : ''}{(selected.effective_edge * 100).toFixed(1)}%
          </span>
        </div>
        <span className="dec-arrow">→</span>
        <span className={`badge lg ${dir}`}>{actionLabel}</span>
      </div>

      <div className="dec-meta">
        <span>90% CI: [{(selected.ci_lower * 100).toFixed(0)}%, {(selected.ci_upper * 100).toFixed(0)}%]</span>
        <span>{selected.signal_count} signals</span>
      </div>
    </div>
  )
}
