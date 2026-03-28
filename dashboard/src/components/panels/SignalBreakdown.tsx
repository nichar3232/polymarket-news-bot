import { useAgent } from '../../context/AgentContext'
import { SIGNAL_DEFS } from '../../data/signalDefinitions'

export function SignalBreakdown() {
  const { state } = useAgent()
  const selected = state.analyses.find(a => a.market_id === state.selectedMarketId)

  if (!selected) return (
    <div className="panel">
      <div className="panel-title">Signal Breakdown</div>
      <div className="no-data">Select a market to view signals</div>
    </div>
  )

  const sorted = [...selected.signals].sort((a, b) => Math.abs(b.eff_lr - 1) - Math.abs(a.eff_lr - 1))

  return (
    <div className="panel">
      <div className="panel-title">
        Confidence Scoring &mdash; {selected.signal_count} Signals
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-mid)', marginBottom: 8, lineHeight: 1.4 }}>
        <span style={{ color: 'var(--text-dim)' }}>Market:</span>{' '}
        <span style={{ color: 'var(--text)' }}>{selected.question}</span>
      </div>

      {/* Model summary */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 10 }}>
          <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-label)', fontSize: 9, letterSpacing: '0.5px' }}>MODEL EST. </span>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{(selected.posterior * 100).toFixed(1)}%</span>
        </div>
        <div style={{ fontSize: 10 }}>
          <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-label)', fontSize: 9, letterSpacing: '0.5px' }}>MARKET </span>
          <span style={{ fontWeight: 600 }}>{(selected.prior * 100).toFixed(1)}%</span>
        </div>
        <div style={{ fontSize: 10 }}>
          <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-label)', fontSize: 9, letterSpacing: '0.5px' }}>EDGE </span>
          <span style={{
            fontWeight: 700, fontSize: 14,
            color: selected.effective_edge >= 0.05 ? 'var(--green)' : selected.effective_edge > 0 ? 'var(--amber)' : 'var(--text-dim)',
          }}>
            {selected.effective_edge >= 0 ? '+' : ''}{(selected.effective_edge * 100).toFixed(1)}%
          </span>
        </div>
        <div style={{ fontSize: 10 }}>
          <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-label)', fontSize: 9, letterSpacing: '0.5px' }}>90% CI </span>
          <span style={{ color: 'var(--text-mid)' }}>
            [{(selected.ci_lower * 100).toFixed(0)}%, {(selected.ci_upper * 100).toFixed(0)}%]
          </span>
        </div>
      </div>

      {/* Signal bars */}
      {sorted.map((sig, i) => {
        const def = SIGNAL_DEFS[sig.source] ?? { label: sig.source, color: '#888', short: sig.source }
        const lr = sig.eff_lr
        const isYes = lr >= 1
        const magnitude = Math.min(Math.abs(lr - 1) / 0.5, 1) * 50
        return (
          <div key={i}>
            <div className="signal-row">
              <span className="signal-source" style={{ color: def.color }}>{def.label}</span>
              <div className="signal-lr-bar">
                <div style={{
                  position: 'absolute', top: 0, left: '50%', width: 1, bottom: 0,
                  background: 'rgba(255,255,255,0.08)',
                }} />
                <div
                  className="signal-lr-fill"
                  style={{
                    left: isYes ? '50%' : `${50 - magnitude}%`,
                    width: `${magnitude}%`,
                    background: def.color,
                    opacity: 0.6,
                  }}
                />
              </div>
              <span className="signal-lr-value" style={{ color: isYes ? 'var(--green)' : 'var(--rose)' }}>
                {lr.toFixed(3)}
              </span>
              <span className="signal-conf">{(sig.confidence * 100).toFixed(0)}%</span>
            </div>
            {sig.notes && <div className="signal-notes">{sig.notes}</div>}
          </div>
        )
      })}

      {/* Explainability section */}
      <div style={{ marginTop: 14, padding: '8px 0', borderTop: '1px solid var(--border)' }}>
        <div className="panel-title" style={{ marginBottom: 6 }}>Why This Trade</div>
        <div style={{ fontSize: 10, color: 'var(--text-mid)', lineHeight: 1.5 }}>
          {selected.trade_direction !== 'NONE' ? (
            <>
              <p style={{ marginBottom: 4 }}>
                <strong style={{ color: 'var(--amber)' }}>Thesis:</strong>{' '}
                Market priced at {(selected.prior * 100).toFixed(0)}% but model estimates{' '}
                {(selected.posterior * 100).toFixed(0)}% after fusing {selected.signal_count} signals.{' '}
                {selected.effective_edge >= 0.10
                  ? 'High-confidence mispricing detected.'
                  : 'Moderate edge above execution threshold.'}
              </p>
              <p style={{ marginBottom: 4 }}>
                <strong style={{ color: 'var(--amber)' }}>Key Drivers:</strong>{' '}
                {sorted.slice(0, 3).map(s => SIGNAL_DEFS[s.source]?.label ?? s.source).join(', ')}
              </p>
              <p>
                <strong style={{ color: 'var(--amber)' }}>Invalidation:</strong>{' '}
                Edge drops below 5% threshold or contradictory signal emerges from{' '}
                {sorted.length > 0 ? (SIGNAL_DEFS[sorted[sorted.length - 1].source]?.label ?? 'opposing source') : 'new data'}.
              </p>
            </>
          ) : (
            <p style={{ color: 'var(--text-dim)' }}>
              Edge below execution threshold ({(selected.effective_edge * 100).toFixed(1)}% &lt; 5.0%).
              Signal quality insufficient for trade.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
