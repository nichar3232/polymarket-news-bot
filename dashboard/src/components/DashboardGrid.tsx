import { PortfolioPanel } from './panels/PortfolioPanel'
import { PnLChart } from './panels/PnLChart'
import { PositionsTable } from './panels/PositionsTable'
import { CalibrationChart } from './panels/CalibrationChart'
import { MarketsTable } from './panels/MarketsTable'
import { SignalBreakdown } from './panels/SignalBreakdown'
import { DecisionPanel } from './panels/DecisionPanel'
import { RadarChart } from './panels/RadarChart'
import { NewsFeed } from './panels/NewsFeed'
import { ActivityLog } from './panels/ActivityLog'
import './DashboardGrid.css'

export function DashboardGrid() {
  return (
    <div className="grid">
      <div className="col col-left">
        <PortfolioPanel />
        <PnLChart />
        <PositionsTable />
        <CalibrationChart />
      </div>
      <div className="col col-center">
        <MarketsTable />
        <div className="center-bottom">
          <div className="center-bottom-left">
            <SignalBreakdown />
          </div>
          <div className="center-bottom-right">
            <DecisionPanel />
            <RadarChart />
          </div>
        </div>
      </div>
      <div className="col col-right">
        <NewsFeed />
        <ActivityLog />
      </div>
    </div>
  )
}
