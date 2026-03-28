import { useAgent } from '../../context/AgentContext'
import { SIGNAL_DEFS } from '../../data/signalDefinitions'

export function DecisionPanel() {
  const { state } = useAgent()
  const selected = state.analyses.find(a => a.market_id === state.selectedMarketId)

  if (!selected) return (
    <div className="panel">
      <div className="panel-title">Decision Engine</div>
      <div className="no-data">Select a market</div>
    </div>
  )

  const dir = selected.trade_direction
  const actionLabel = dir === 'NONE' ? 'HOLD' : `BUY ${dir}`
  const actionClass = dir === 'YES' ? 'BUY-YES' : dir === 'NO' ? 'BUY-NO' : 'HOLD'

  const topSignals = [...selected.signals]
    .sort((a, b) => Math.abs(b.eff_lr - 1) - Math.abs(a.eff_lr - 1))
    .slice(0, 3)

  const rationale = dir !== 'NONE'
    ? selected.effective_edge >= 0.10
      ? 'High confidence mispricing detected'
      : 'Edge above execution threshold'
    : selected.effective_edge < 0.05
      ? 'Edge below execution threshold'
      : 'Signal quality insufficient'

  return (
    <div className="panel">
      <div className="panel-title">Decision Engine</div>
      <div className="decision-flow">
        <div className="decision-node">
          <span className="decision-node-label">PRIOR</span>
          <span className="decision-node-value" style={{ color: 'var(--text-mid)' }}>
            {(selected.prior * 100).toFixed(1)}%
          </span>
        </div>
        <span className="decision-arrow">&rarr;</span>

        {topSignals.map((s, i) => {
          const def = SIGNAL_DEFS[s.source]
          return (
            <div key={i} className="decision-node" style={{ borderColor: def?.color ?? 'var(--border)', borderWidth: 1 }}>
              <span className="decision-node-label">{def?.short ?? s.source}</span>
              <span className="decision-node-value" style={{
                fontSize: 12, color: s.eff_lr >= 1 ? 'var(--green)' : 'var(--rose)'
              }}>
                {s.eff_lr.toFixed(2)}
              </span>
            </div>
          )
        })}

        <span className="decision-arrow">&rarr;</span>
        <div className="decision-node">
          <span className="decision-node-label">POST</span>
          <span className="decision-node-value" style={{ color: 'var(--amber)' }}>
            {(selected.posterior * 100).toFixed(1)}%
          </span>
        </div>
        <span className="decision-arrow">&rarr;</span>
        <div className={`decision-action ${actionClass}`}>
          <span className="decision-action-label">{actionLabel}</span>
        </div>
      </div>
      <div className="decision-rationale">&quot;{rationale}&quot;</div>
    </div>
  )
}
