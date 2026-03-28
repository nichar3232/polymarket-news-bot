export function CalibrationChart() {
  const buckets = [
    { predicted: 10, actual: 7 },
    { predicted: 20, actual: 18 },
    { predicted: 30, actual: 28 },
    { predicted: 40, actual: 42 },
    { predicted: 50, actual: 48 },
    { predicted: 60, actual: 63 },
    { predicted: 70, actual: 72 },
    { predicted: 80, actual: 78 },
    { predicted: 90, actual: 92 },
  ]

  const w = 200
  const h = 200
  const pad = 24

  return (
    <div className="panel">
      <div className="panel-title">Calibration</div>
      <div className="cal-chart">
        <svg viewBox={`0 0 ${w} ${h}`}>
          {/* Grid */}
          {[0, 25, 50, 75, 100].map(v => {
            const x = pad + (v / 100) * (w - pad * 2)
            const y = h - pad - (v / 100) * (h - pad * 2)
            return (
              <g key={v}>
                <line x1={pad} y1={y} x2={w - pad} y2={y} stroke="var(--border)" strokeWidth="0.5" />
                <text x={pad - 4} y={y + 3} fontSize="7" fill="var(--text-dim)" textAnchor="end" fontFamily="var(--font-mono)">{v}</text>
                <text x={x} y={h - pad + 12} fontSize="7" fill="var(--text-dim)" textAnchor="middle" fontFamily="var(--font-mono)">{v}</text>
              </g>
            )
          })}

          {/* Perfect calibration line */}
          <line
            x1={pad} y1={h - pad}
            x2={w - pad} y2={pad}
            stroke="var(--border-hi)" strokeWidth="1" strokeDasharray="3,3"
          />

          {/* Data points */}
          {buckets.map((b, i) => {
            const x = pad + (b.predicted / 100) * (w - pad * 2)
            const y = h - pad - (b.actual / 100) * (h - pad * 2)
            return <circle key={i} cx={x} cy={y} r="3" fill="var(--orange)" opacity="0.9" />
          })}
        </svg>
      </div>
    </div>
  )
}
