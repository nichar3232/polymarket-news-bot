import { useAgent } from '../../context/AgentContext'

export function PositionsTable() {
  const { state } = useAgent()
  const positions = state.portfolio.positions

  return (
    <div className="panel">
      <div className="panel-title">
        <span>Positions</span>
        <span className="count">{positions.length}</span>
      </div>
      {positions.length === 0 ? (
        <div className="no-data">No open positions</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Market</th>
              <th>Dir</th>
              <th>Size</th>
              <th>Entry</th>
              <th>Now</th>
              <th className="r">P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(p => (
              <tr key={p.market_id}>
                <td className="truncate">{p.market_id}</td>
                <td><span className={`badge ${p.direction}`}>{p.direction}</span></td>
                <td>${p.size_usd.toFixed(0)}</td>
                <td>{p.entry_price.toFixed(3)}</td>
                <td>{p.current_price.toFixed(3)}</td>
                <td className={`r mono ${p.pnl >= 0 ? 'c-green' : 'c-red'}`}>
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
