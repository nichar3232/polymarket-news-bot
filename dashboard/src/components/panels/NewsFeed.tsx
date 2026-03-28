import { useAgent } from '../../context/AgentContext'

function timeAgo(ts: number): string {
  const secs = Math.floor(Date.now() / 1000 - ts)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

function relevanceClass(r: number): string {
  if (r >= 0.75) return 'high'
  if (r >= 0.50) return 'med'
  return 'low'
}

function relevanceLabel(r: number): string {
  if (r >= 0.75) return 'HIGH'
  if (r >= 0.50) return 'MED'
  return 'LOW'
}

export function NewsFeed() {
  const { state } = useAgent()

  return (
    <div className="panel" style={{ maxHeight: '50%', overflow: 'auto' }}>
      <div className="panel-title">News Intelligence ({state.news.length})</div>
      <div className="news-list">
        {state.news.slice(0, 30).map((n, i) => (
          <div key={i} className="news-item">
            <div className="news-item-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="news-source">{n.source}</span>
                <span className={`news-relevance ${relevanceClass(n.relevance)}`}>
                  {relevanceLabel(n.relevance)}
                </span>
              </div>
              <span className="news-time">{timeAgo(n.ts)}</span>
            </div>
            <div className="news-title">{n.title}</div>
          </div>
        ))}
        {state.news.length === 0 && <div className="no-data">Monitoring feeds...</div>}
      </div>
    </div>
  )
}
