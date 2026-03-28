import { useAgent } from '../../context/AgentContext'

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function ActivityLog() {
  const { state } = useAgent()

  return (
    <div className="panel" style={{ overflow: 'auto', flex: 1 }}>
      <div className="panel-title">
        <span>Activity</span>
        <span className="count">{state.events.length}</span>
      </div>
      <div className="log-list">
        {state.events.slice(0, 50).map((e, i) => (
          <div key={i} className={`log-item ${e.kind}`}>
            <span className="log-time">{fmtTime(e.ts)}</span>
            <span className="log-msg">{e.message}</span>
          </div>
        ))}
        {state.events.length === 0 && <div className="no-data">Waiting for events…</div>}
      </div>
    </div>
  )
}
