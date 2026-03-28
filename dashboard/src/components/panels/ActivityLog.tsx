import { useAgent } from '../../context/AgentContext'

function timeAgo(ts: number): string {
  const secs = Math.floor(Date.now() / 1000 - ts)
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  return `${Math.floor(secs / 3600)}h`
}

export function ActivityLog() {
  const { state } = useAgent()

  return (
    <div className="panel" style={{ overflow: 'auto', flex: 1 }}>
      <div className="panel-title">Execution Log ({state.events.length})</div>
      <div className="activity-list">
        {state.events.slice(0, 50).map((e, i) => (
          <div key={i} className="activity-item">
            <span className={`activity-kind ${e.kind}`}>{e.kind}</span>
            <span className="activity-msg">{e.message}</span>
            <span className="activity-time">{timeAgo(e.ts)}</span>
          </div>
        ))}
        {state.events.length === 0 && <div className="no-data">Waiting for events...</div>}
      </div>
    </div>
  )
}
