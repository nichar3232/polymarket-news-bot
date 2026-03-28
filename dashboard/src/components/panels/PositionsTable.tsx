import { useAgent } from '../../context/AgentContext'

export function PositionsTable() {
  const { state } = useAgent()
  const positions = state.portfolio.positions

  return (
    <div className="panel">
      <div className="panel-title">Open Positions ({positions.length})</div>
      {positions.length === 0 ? (
        <div className="no-data">No open positions</div>
      ) : (
        <table className="pos-table">
          <thead>
            <tr>
              <th>Market</th>
              <th>Dir</th>
              <th>Size</th>
              <th>Entry</th>
              <th>Now</th>
              <th style={{ textAlign: 'right' }}>P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(p => (
              <tr key={p.market_id}>
                <td style={{ maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.market_id}
                </td>
                <td><span className={`pos-dir ${p.direction}`}>{p.direction}</span></td>
                <td>${p.size_usd.toFixed(0)}</td>
                <td>{p.entry_price.toFixed(2)}</td>
                <td>{p.current_price.toFixed(2)}</td>
                <td className={p.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'} style={{ textAlign: 'right', fontWeight: 600 }}>
                  {p.pnl >= 0 ? '+' : ''}{p.pnl.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
