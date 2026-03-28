import { SummaryStrip } from './SummaryStrip'
import { PortfolioPanel } from './panels/PortfolioPanel'
import { PnLChart } from './panels/PnLChart'
import { PositionsTable } from './panels/PositionsTable'
import { MarketsTable } from './panels/MarketsTable'
import { SignalBreakdown } from './panels/SignalBreakdown'
import { DecisionPanel } from './panels/DecisionPanel'
import { RadarChart } from './panels/RadarChart'
import { NewsFeed } from './panels/NewsFeed'
import { ActivityLog } from './panels/ActivityLog'
import './DashboardGrid.css'

export function DashboardGrid() {
  return (
    <>
      <SummaryStrip />
      <div className="grid">
        {/* Left sidebar: portfolio + risk */}
        <div className="col col-left">
          <PortfolioPanel />
          <PnLChart />
          <PositionsTable />
        </div>

        {/* Center: markets table + signal detail below */}
        <div className="col col-center">
          <MarketsTable />
          <DecisionPanel />
          <SignalBreakdown />
          <RadarChart />
        </div>

        {/* Activity feed */}
        <div className="col col-activity">
          <ActivityLog />
        </div>

        {/* News feed */}
        <div className="col col-news">
          <NewsFeed />
        </div>
      </div>
    </>
  )
}
