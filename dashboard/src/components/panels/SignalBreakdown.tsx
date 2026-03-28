import { useAgent } from '../../context/AgentContext'
import { SIGNAL_DEFS } from '../../data/signalDefinitions'

export function SignalBreakdown() {
  const { state } = useAgent()
  const selected = state.analyses.find(a => a.market_id === state.selectedMarketId)

  if (!selected) return (
    <div className="panel">
      <div className="panel-title">Signals</div>
      <div className="no-data">Select a market</div>
    </div>
  )

  const sorted = [...selected.signals].sort((a, b) => Math.abs(b.eff_lr - 1) - Math.abs(a.eff_lr - 1))

  return (
    <div className="panel">
      <div className="panel-title">
        <span>Signals</span>
        <span className="count">{selected.signal_count}</span>
      </div>

      <table className="data-table sig-table">
        <thead>
          <tr>
            <th className="l">Source</th>
            <th>LR</th>
            <th>Conf.</th>
            <th className="l">Notes</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((sig, i) => {
            const def = SIGNAL_DEFS[sig.source] ?? { label: sig.source, color: '#888', short: sig.source }
            return (
              <tr key={i}>
                <td style={{ color: def.color }}>{def.label}</td>
                <td className={`mono ${sig.eff_lr >= 1 ? 'c-green' : 'c-red'}`}>
                  {sig.eff_lr.toFixed(3)}
                </td>
                <td className="mono dim">{(sig.confidence * 100).toFixed(0)}%</td>
                <td className="sig-notes">{sig.notes || '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
