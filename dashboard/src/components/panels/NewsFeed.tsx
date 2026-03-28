import { useAgent } from '../../context/AgentContext'

function timeAgo(ts: number): string {
  const secs = Math.floor(Date.now() / 1000 - ts)
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`
  return `${Math.floor(secs / 86400)}d`
}

export function NewsFeed() {
  const { state } = useAgent()

  return (
    <div className="panel" style={{ flex: 1, overflow: 'auto' }}>
      <div className="panel-title">
        <span>News</span>
        <span className="count">{state.news.length}</span>
      </div>
      <div className="news-list">
        {state.news.slice(0, 30).map((n, i) => (
          <div key={i} className="news-item">
            <div className="news-header">
              <span className="news-src">{n.source}</span>
              <span className="news-time">{timeAgo(n.ts)}</span>
            </div>
            <div className="news-title">{n.title}</div>
          </div>
        ))}
        {state.news.length === 0 && <div className="no-data">Monitoring feeds…</div>}
      </div>
    </div>
  )
}
