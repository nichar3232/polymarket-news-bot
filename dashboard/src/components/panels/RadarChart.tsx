import { useAgent } from '../../context/AgentContext'
import { SIGNAL_DEFS, SIGNAL_SOURCES } from '../../data/signalDefinitions'

export function RadarChart() {
  const { state } = useAgent()
  const selected = state.analyses.find(a => a.market_id === state.selectedMarketId)

  const size = 180
  const cx = size / 2
  const cy = size / 2
  const r = 65
  const n = SIGNAL_SOURCES.length
  const angles = SIGNAL_SOURCES.map((_, i) => (Math.PI * 2 * i) / n - Math.PI / 2)

  function pt(angle: number, radius: number) {
    return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }
  }

  const values = SIGNAL_SOURCES.map(source => {
    if (!selected) return 0
    const sig = selected.signals.find(s => s.source === source)
    if (!sig) return 0
    return Math.min(Math.abs(sig.eff_lr - 1) / 0.5, 1)
  })

  const dataPoints = values.map((v, i) => pt(angles[i], v * r))

  return (
    <div className="panel">
      <div className="panel-title">Radar</div>
      <div className="radar-wrap">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {[0.33, 0.66, 1.0].map(s => (
            <polygon key={s}
              points={angles.map(a => { const p = pt(a, r * s); return `${p.x},${p.y}` }).join(' ')}
              fill="none" stroke="var(--border)" strokeWidth="0.5"
            />
          ))}
          {angles.map((a, i) => {
            const p = pt(a, r)
            return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="var(--border)" strokeWidth="0.5" />
          })}
          {selected && (
            <polygon
              points={dataPoints.map(p => `${p.x},${p.y}`).join(' ')}
              fill="rgba(255,110,38,0.08)" stroke="var(--orange)" strokeWidth="1.2"
            />
          )}
          {dataPoints.map((p, i) => (
            values[i] > 0 && (
              <circle key={i} cx={p.x} cy={p.y} r="2.5"
                fill={SIGNAL_DEFS[SIGNAL_SOURCES[i]]?.color ?? 'var(--text-dim)'}
              />
            )
          ))}
          {SIGNAL_SOURCES.map((source, i) => {
            const p = pt(angles[i], r + 16)
            return (
              <text key={i} x={p.x} y={p.y}
                textAnchor="middle" dominantBaseline="middle"
                fill="var(--text-dim)" fontSize="7.5"
                fontFamily="var(--font-sans)" fontWeight="500"
              >
                {SIGNAL_DEFS[source]?.short ?? source}
              </text>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
