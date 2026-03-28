import { useAgent } from '../../context/AgentContext'

export function PnLChart() {
  const { state } = useAgent()
  const data = state.pnl_history

  if (data.length < 2) return (
    <div className="panel">
      <div className="panel-title">P&L</div>
      <div className="no-data">Waiting for data…</div>
    </div>
  )

  const values = data.map(d => d.pnl_pct)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const w = 240
  const h = 72
  const pad = 1

  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  })

  // Bug 18 fix: clamp so zero-line stays inside canvas when all values are positive or all negative
  const zeroY = Math.max(pad, Math.min(h - pad, h - pad - ((0 - min) / range) * (h - pad * 2)))
  const lastVal = values[values.length - 1]
  const color = lastVal >= 0 ? 'var(--green)' : 'var(--red)'
  const fill = lastVal >= 0 ? 'rgba(52,211,153,0.06)' : 'rgba(248,113,113,0.06)'
  const areaPoints = `${pad},${h} ${points.join(' ')} ${w - pad},${h}`

  return (
    <div className="panel">
      <div className="panel-title">
        <span>P&L</span>
        <span style={{ color, fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500 }}>
          {lastVal >= 0 ? '+' : ''}{lastVal.toFixed(2)}%
        </span>
      </div>
      <div className="pnl-chart">
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
          <line x1={pad} y1={zeroY} x2={w - pad} y2={zeroY} stroke="var(--border)" strokeWidth="0.5" />
          <polygon points={areaPoints} fill={fill} />
          <polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  )
}
