import { useAgent } from '../../context/AgentContext'
import type { Analysis } from '../../types'

function EdgeBar({ edge }: { edge: number }) {
  const maxEdge = 0.25
  const pct = Math.min(Math.abs(edge) / maxEdge, 1) * 50
  const isPositive = edge >= 0
  return (
    <div className="edge-bar-container">
      <div className="edge-bar-track" />
      <div className="edge-bar-center" />
      <div
        className="edge-bar-fill"
        style={{
          left: isPositive ? '50%' : `${50 - pct}%`,
          width: `${pct}%`,
          background: isPositive ? 'var(--green)' : 'var(--rose)',
          opacity: 0.7,
        }}
      />
    </div>
  )
}

export function MarketsTable() {
  const { state, selectMarket } = useAgent()
  const analyses = [...state.analyses].sort((a, b) => Math.abs(b.effective_edge) - Math.abs(a.effective_edge))

  return (
    <div className="panel" style={{ padding: 0, overflow: 'auto', maxHeight: '45vh' }}>
      <table className="markets-table">
        <thead>
          <tr>
            <th>Market</th>
            <th>Prior</th>
            <th>Posterior</th>
            <th>Edge</th>
            <th style={{ width: 80 }}>Edge</th>
            <th>CI</th>
            <th>Signals</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {analyses.map((a: Analysis) => (
            <tr
              key={a.market_id}
              className={state.selectedMarketId === a.market_id ? 'selected' : ''}
              onClick={() => selectMarket(a.market_id)}
            >
              <td className="market-question" title={a.question}>{a.question}</td>
              <td style={{ color: 'var(--text-mid)' }}>{(a.prior * 100).toFixed(1)}%</td>
              <td style={{ fontWeight: 600 }}>{(a.posterior * 100).toFixed(1)}%</td>
              <td style={{ color: a.effective_edge > 0 ? 'var(--green)' : a.effective_edge < -0.02 ? 'var(--rose)' : 'var(--text-dim)', fontWeight: 600 }}>
                {a.effective_edge >= 0 ? '+' : ''}{(a.effective_edge * 100).toFixed(1)}%
              </td>
              <td><EdgeBar edge={a.effective_edge} /></td>
              <td style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                {(a.ci_lower * 100).toFixed(0)}-{(a.ci_upper * 100).toFixed(0)}%
              </td>
              <td style={{ textAlign: 'center' }}>{a.signal_count}</td>
              <td><span className={`dir-badge ${a.trade_direction}`}>
                {a.trade_direction === 'NONE' ? 'HOLD' : `BUY ${a.trade_direction}`}
              </span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {analyses.length === 0 && <div className="no-data">Scanning markets...</div>}
    </div>
  )
}
