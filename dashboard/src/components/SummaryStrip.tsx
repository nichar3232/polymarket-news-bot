import { useAgent } from '../context/AgentContext'

export function SummaryStrip() {
  const { state, selectMarket } = useAgent()
  const top = [...state.analyses]
    .filter(a => a.trade_direction !== 'NONE')
    .sort((a, b) => Math.abs(b.effective_edge) - Math.abs(a.effective_edge))
    .slice(0, 5)

  if (top.length === 0) return null

  return (
    <div className="strip">
      <span className="strip-label">TOP SIGNALS</span>
      {top.map(a => {
        // Backend defines effective_edge as magnitude after fees (abs(edge) - fee).
        // Use edge sign to render direction correctly for NO trades.
        const signedEff = (a.edge >= 0 ? 1 : -1) * a.effective_edge
        return (
          <button
            key={a.market_id}
            className={`strip-chip ${state.selectedMarketId === a.market_id ? 'active' : ''}`}
            onClick={() => selectMarket(a.market_id)}
          >
            <span className="strip-q">{a.question.length > 40 ? a.question.slice(0, 40) + '…' : a.question}</span>
            <span className={`strip-edge ${signedEff >= 0 ? 'pos' : 'neg'}`}>
              {signedEff >= 0 ? '+' : ''}{(signedEff * 100).toFixed(1)}%
            </span>
            <span className={`strip-dir ${a.trade_direction}`}>
              {a.trade_direction}
            </span>
          </button>
        )
      })}
    </div>
  )
}
