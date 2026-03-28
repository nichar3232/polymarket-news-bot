import { Component } from 'react'
import type { ReactNode } from 'react'
import { AgentProvider } from './context/AgentContext'
import { useAgent } from './context/AgentContext'
import { TopBar } from './components/TopBar'
import { DashboardGrid } from './components/DashboardGrid'

// Bug 4 fix: ErrorBoundary prevents one crashing component from blanking the whole dashboard
class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', fontFamily: 'monospace', color: 'var(--red)' }}>
          <div style={{ fontSize: 16, marginBottom: 8 }}>Dashboard render error</div>
          <pre style={{ fontSize: 11, opacity: 0.7 }}>{this.state.error?.message}</pre>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{ marginTop: 12, padding: '4px 12px', cursor: 'pointer' }}
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// Bug 16 fix: DemoBanner warns the user that data is synthetic, not live
function DemoBanner() {
  const { state } = useAgent()
  if (!state.demoMode) return null
  return (
    <div style={{
      background: '#f59e0b',
      color: '#000',
      textAlign: 'center',
      padding: '4px 0',
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: '0.08em',
      fontFamily: 'monospace',
      zIndex: 100,
    }}>
      ⚠ DEMO MODE — backend not connected. Showing synthetic data.
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <AgentProvider>
        <DemoBanner />
        <TopBar />
        <DashboardGrid />
      </AgentProvider>
    </ErrorBoundary>
  )
}
