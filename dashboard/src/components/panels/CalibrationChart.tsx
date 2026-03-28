export function CalibrationChart() {
  const buckets = [
    { label: '0-10%', predicted: 5, actual: 3 },
    { label: '10-20%', predicted: 15, actual: 12 },
    { label: '20-30%', predicted: 25, actual: 22 },
    { label: '30-40%', predicted: 35, actual: 38 },
    { label: '40-50%', predicted: 45, actual: 42 },
    { label: '50-60%', predicted: 55, actual: 58 },
    { label: '60-70%', predicted: 65, actual: 67 },
    { label: '70-80%', predicted: 75, actual: 72 },
    { label: '80-90%', predicted: 85, actual: 88 },
    { label: '90-100%', predicted: 95, actual: 92 },
  ]

  return (
    <div className="panel">
      <div className="panel-title">Model Calibration</div>
      <div>
        {buckets.map(b => (
          <div key={b.label} className="cal-row">
            <span className="cal-bucket">{b.label}</span>
            <div className="cal-bar-track">
              <div className="cal-bar-predicted" style={{ width: `${b.predicted}%` }} />
              <div className="cal-bar-actual" style={{ width: `${b.actual}%` }} />
              <div className="cal-perfect" style={{ left: `${b.predicted}%` }} />
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 6, justifyContent: 'center' }}>
        <span style={{ fontSize: 9, color: 'var(--blue)', fontFamily: 'var(--font-label)', letterSpacing: '0.5px' }}>
          &#9632; Predicted
        </span>
        <span style={{ fontSize: 9, color: 'var(--amber)', fontFamily: 'var(--font-label)', letterSpacing: '0.5px' }}>
          &#9632; Actual
        </span>
      </div>
    </div>
  )
}
