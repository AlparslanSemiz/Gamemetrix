import { RefreshCw } from 'lucide-react'

import type { DataFillStatus, PrimaryScoreCoverage } from '../../../services/admin'
import { formatAdminDateTime } from '../format'
import { AdminRow, Panel, RowList, TextRow } from './Panel'
import { percent, ratio } from './math'

const MINIMUM_BUDGET_BAR_PERCENT = 4

export interface DataFillPanelProps {
  dataFill: DataFillStatus | null
  dataGaps: readonly (readonly [string, number])[]
  isStartingDataFill: boolean
  isStartingPrimaryScores: boolean
  primaryScoreRows: [string, PrimaryScoreCoverage['sources'][string]][]
  rateLimitRows: [string, { remaining: number; limit: number }][]
  onStartDataFill: () => void
  onStartPrimaryScores: () => void
}

export function DataFillPanel({
  dataFill,
  dataGaps,
  isStartingDataFill,
  isStartingPrimaryScores,
  primaryScoreRows,
  rateLimitRows,
  onStartDataFill,
  onStartPrimaryScores,
}: DataFillPanelProps) {
  const totalGames = dataFill?.primary_scores.total_games ?? 0
  return (
    <Panel
      title="Data Fill"
      width="wide"
      action={
        <DataFillActions
          isRunning={dataFill?.running ?? false}
          isStartingDataFill={isStartingDataFill}
          isStartingPrimaryScores={isStartingPrimaryScores}
          onStartDataFill={onStartDataFill}
          onStartPrimaryScores={onStartPrimaryScores}
        />
      }
    >
      <div className="admin-data-fill-grid">
        <RowList>
          <AdminRow label="Total games" value={dataFill?.catalog.total_games ?? 0} />
          <TextRow
            label="4-source complete"
            value={ratio(dataFill?.primary_scores.complete_games ?? 0, totalGames)}
          />
          {dataGaps.map(([label, value]) => (
            <AdminRow key={label} label={label} value={value} />
          ))}
        </RowList>
        <DataFillBudgets
          totalGames={totalGames}
          primaryScoreRows={primaryScoreRows}
          rateLimitRows={rateLimitRows}
        />
      </div>
      <div className="admin-inline-stats">
        <span>Last run: {dataFill?.last_run?.status ?? 'none'}</span>
        {dataFill?.last_run?.finished_at ? (
          <span>{formatAdminDateTime(dataFill.last_run.finished_at)}</span>
        ) : null}
      </div>
    </Panel>
  )
}

function DataFillActions({
  isRunning,
  isStartingDataFill,
  isStartingPrimaryScores,
  onStartDataFill,
  onStartPrimaryScores,
}: {
  isRunning: boolean
  isStartingDataFill: boolean
  isStartingPrimaryScores: boolean
  onStartDataFill: () => void
  onStartPrimaryScores: () => void
}) {
  return (
    <div className="admin-panel-actions">
      <JobButton
        idleLabel="Fill 4 scores"
        isStarting={isStartingPrimaryScores}
        isRunning={isRunning}
        onClick={onStartPrimaryScores}
      />
      <JobButton
        idleLabel="Run fill"
        isStarting={isStartingDataFill}
        isRunning={isRunning}
        onClick={onStartDataFill}
      />
    </div>
  )
}

function JobButton({
  idleLabel,
  isStarting,
  isRunning,
  onClick,
}: {
  idleLabel: string
  isStarting: boolean
  isRunning: boolean
  onClick: () => void
}) {
  const label = isStarting ? 'Starting' : isRunning ? 'Running' : idleLabel
  return (
    <button type="button" onClick={onClick} disabled={isStarting || isRunning}>
      <RefreshCw size={15} aria-hidden="true" />
      <span>{label}</span>
    </button>
  )
}

function DataFillBudgets({
  totalGames,
  primaryScoreRows,
  rateLimitRows,
}: {
  totalGames: number
  primaryScoreRows: DataFillPanelProps['primaryScoreRows']
  rateLimitRows: DataFillPanelProps['rateLimitRows']
}) {
  return (
    <div className="admin-budget-list">
      {primaryScoreRows.map(([source, coverage]) => (
        <TextRow
          key={`coverage-${source}`}
          label={`${source} live`}
          value={ratio(coverage.live, totalGames)}
        />
      ))}
      {rateLimitRows.map(([source, budget]) => (
        <div className="admin-budget-row" key={source}>
          <span>{source}</span>
          <div className="admin-budget-track">
            <i
              style={{
                width: `${Math.max(
                  MINIMUM_BUDGET_BAR_PERCENT,
                  percent(budget.remaining, budget.limit),
                )}%`,
              }}
            />
          </div>
          <strong>
            {budget.remaining}/{budget.limit}
          </strong>
        </div>
      ))}
    </div>
  )
}
