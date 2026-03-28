import { useAgent } from '../../context/AgentContext'
import { SIGNAL_DEFS, SIGNAL_SOURCES } from '../../data/signalDefinitions'

export function RadarChart() {
  const { state } = useAgent()
  const selected = state.analyses.find(a => a.market_id === state.selectedMarketId)

  const size = 200
  const cx = size / 2
  const cy = size / 2
  const r = 75
  const n = SIGNAL_SOURCES.length

  const angles = SIGNAL_SOURCES.map((_, i) => (Math.PI * 2 * i) / n - Math.PI / 2)

  function point(angle: number, radius: number) {
    return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }
  }

  const rings = [0.25, 0.5, 0.75, 1.0]

  // Map signal data to radar values (0 = neutral, 1 = max influence)
  const values = SIGNAL_SOURCES.map(source => {
    if (!selected) return 0
    const sig = selected.signals.find(s => s.source === source)
    if (!sig) return 0
    return Math.min(Math.abs(sig.eff_lr - 1) / 0.5, 1)
  })

  const dataPoints = values.map((v, i) => point(angles[i], v * r))

  return (
    <div className="panel">
      <div className="panel-title">Signal Radar</div>
      <div className="radar-container">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Grid rings */}
          {rings.map(scale => (
            <polygon
              key={scale}
              points={angles.map(a => { const p = point(a, r * scale); return `${p.x},${p.y}` }).join(' ')}
              fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5"
            />
          ))}
          {/* Axis lines */}
          {angles.map((a, i) => {
            const p = point(a, r)
            return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" />
          })}
          {/* Data polygon */}
          {selected && (
            <>
              <polygon points={dataPoints.map(p => `${p.x},${p.y}`).join(' ')}
                fill="rgba(245,166,35,0.12)" stroke="var(--amber)" strokeWidth="1.5" />
              {/* Data dots */}
              {dataPoints.map((p, i) => (
                values[i] > 0 && <circle key={i} cx={p.x} cy={p.y} r="3"
                  fill={SIGNAL_DEFS[SIGNAL_SOURCES[i]]?.color ?? '#888'}
                  stroke="var(--bg)" strokeWidth="1" />
              ))}
            </>
          )}
          {/* Labels */}
          {SIGNAL_SOURCES.map((source, i) => {
            const labelR = r + 18
            const p = point(angles[i], labelR)
            const def = SIGNAL_DEFS[source]
            return (
              <text key={i} x={p.x} y={p.y}
                textAnchor="middle" dominantBaseline="middle"
                fill={def?.color ?? 'var(--text-dim)'} fontSize="8"
                fontFamily="var(--font-label)" fontWeight="600" letterSpacing="0.3"
              >
                {def?.short ?? source}
              </text>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
