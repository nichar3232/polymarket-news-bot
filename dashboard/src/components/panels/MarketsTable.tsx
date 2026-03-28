import { useAgent } from '../../context/AgentContext'
import type { Analysis } from '../../types'

export function MarketsTable() {
  const { state, selectMarket } = useAgent()
  const analyses = [...state.analyses].sort((a, b) => Math.abs(b.effective_edge) - Math.abs(a.effective_edge))

  return (
    <div className="panel" style={{ padding: 0, overflow: 'auto', height: '100%' }}>
      <table className="markets-table">
        <thead>
          <tr>
            <th className="l">Market</th>
            <th>Prior</th>
            <th>Post.</th>
            <th>Eff Edge</th>
            <th>CI</th>
            <th>Sig.</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {analyses.map((a: Analysis) => {
            const signedEff = (a.edge >= 0 ? 1 : -1) * a.effective_edge
            return (
              <tr
                key={a.market_id}
                className={state.selectedMarketId === a.market_id ? 'selected' : ''}
                onClick={() => selectMarket(a.market_id)}
              >
                <td className="mkt-q" title={a.question}>{a.question}</td>
                <td className="mono dim">{(a.prior * 100).toFixed(1)}%</td>
                <td className="mono">{(a.posterior * 100).toFixed(1)}%</td>
                <td className={`mono fw ${signedEff > 0 ? 'c-green' : signedEff < 0 ? 'c-red' : 'dim'}`}>
                  {signedEff >= 0 ? '+' : ''}{(signedEff * 100).toFixed(1)}%
                </td>
                <td className="mono dim" style={{ fontSize: 10 }}>
                  {(a.ci_lower * 100).toFixed(0)}–{(a.ci_upper * 100).toFixed(0)}%
                </td>
                <td className="c">{a.signal_count}</td>
                <td>
                  <span className={`badge ${a.trade_direction === 'NONE' ? 'HOLD' : a.trade_direction}`}>
                    {a.trade_direction === 'NONE' ? 'HOLD' : a.trade_direction}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {analyses.length === 0 && <div className="no-data">Scanning markets…</div>}
    </div>
  )
}
