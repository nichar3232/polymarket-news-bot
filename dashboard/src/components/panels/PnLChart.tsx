import { useAgent } from '../../context/AgentContext'

export function PnLChart() {
  const { state } = useAgent()
  const data = state.pnl_history

  if (data.length < 2) return <div className="panel"><div className="panel-title">P&L History</div><div className="no-data">Waiting for data...</div></div>

  const values = data.map(d => d.pnl_pct)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const w = 252
  const h = 80
  const pad = 2

  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  })

  const zeroY = h - pad - ((0 - min) / range) * (h - pad * 2)
  const lastVal = values[values.length - 1]
  const color = lastVal >= 0 ? 'var(--green)' : 'var(--rose)'

  const areaPoints = `${pad},${h - pad} ${points.join(' ')} ${w - pad},${h - pad}`

  return (
    <div className="panel">
      <div className="panel-title">
        P&L History
        <span style={{ float: 'right', color, fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600 }}>
          {lastVal >= 0 ? '+' : ''}{lastVal.toFixed(2)}%
        </span>
      </div>
      <div className="pnl-chart-container">
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
          <line x1={pad} y1={zeroY} x2={w - pad} y2={zeroY} stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
          <polygon points={areaPoints} fill={lastVal >= 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)'} />
          <polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  )
}
