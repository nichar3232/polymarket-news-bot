import { AgentProvider } from './context/AgentContext'
import { TopBar } from './components/TopBar'
import { DashboardGrid } from './components/DashboardGrid'

export default function App() {
  return (
    <AgentProvider>
      <TopBar />
      <DashboardGrid />
    </AgentProvider>
  )
}
