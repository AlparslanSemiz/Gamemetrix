import { RefreshCw } from 'lucide-react'

import type { DataFillStatus, PrimaryScoreCoverage } from '../../../services/admin'
import { formatAdminDateTime } from '../format'
import { Panel, RowList } from './Panel'
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
  const topTarget = dataFill?.primary_scores.top_target
  const topTotal = topTarget?.total_games ?? 0
  const topFourScores = topTarget?.four_score_games ?? 0
  const topApplicableComplete = topTarget?.complete_games ?? 0
  const openCriticSearchLimit = dataFill?.rate_limits['OpenCritic:search']?.limit ?? 0
  return (
    <Panel
      title="Data coverage & fill"
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
      <div className="admin-fill-summary">
        <CoverageStat
          label="Catalog"
          value={dataFill?.catalog.total_games ?? 0}
          detail="searchable games"
        />
        <CoverageStat
          label="Top 10k — four scores"
          value={percent(topFourScores, topTotal)}
          detail={ratio(topFourScores, topTotal)}
          percentage
        />
        <CoverageStat
          label="Top 10k — all applicable"
          value={percent(topApplicableComplete, topTotal)}
          detail={ratio(topApplicableComplete, topTotal)}
          percentage
        />
        <CoverageStat
          label="Top 10k — non-PC"
          value={topTarget?.non_pc_games ?? 0}
          detail="Steam is not applicable"
        />
      </div>
      <p className="admin-fill-guidance">
        The queue now prioritizes the top 10,000 and games closest to completion.
        Four scores means four independent named providers; unavailable reviews are never
        duplicated or invented. “All applicable” is the honest platform-aware ceiling.
      </p>
      <p className="admin-fill-eta">
        {openCriticSearchLimit > 0 && openCriticSearchLimit <= 2
          ? `ETA blocked: OpenCritic search is capped at ${openCriticSearchLimit}/day. Raise or replace this provider before a completion date is credible.`
          : 'ETA becomes reliable after one full source-check cycle records the provider hit rates.'}
      </p>
      <div className="admin-data-fill-grid">
        <div>
          <h3 className="admin-fill-subtitle">Work queue indicators</h3>
          <RowList>
            {dataGaps.map(([label, value]) => (
              <GapRow key={label} label={label} total={totalGames} value={value} />
            ))}
          </RowList>
        </div>
        <DataFillBudgets
          totalGames={totalGames}
          primaryScoreRows={primaryScoreRows}
          rateLimitRows={rateLimitRows}
        />
      </div>
      <div className="admin-inline-stats">
        <span>Last pipeline run: {dataFill?.last_run?.status ?? 'none'}</span>
        {dataFill?.last_run?.finished_at ? (
          <span>{formatAdminDateTime(dataFill.last_run.finished_at)}</span>
        ) : null}
      </div>
      <small className="admin-run-status-note">
        Pipeline status reports whether the workflow ended; it does not mean the catalog is complete.
      </small>
    </Panel>
  )
}

function CoverageStat({
  label,
  value,
  detail,
  percentage = false,
}: {
  label: string
  value: number
  detail: string
  percentage?: boolean
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>{percentage ? `${value.toFixed(1)}%` : value.toLocaleString('en-US')}</strong>
      <small>{detail}</small>
    </div>
  )
}

function GapRow({
  label,
  total,
  value,
}: {
  label: string
  total: number
  value: number
}) {
  return (
    <div className="admin-gap-row">
      <div>
        <span>{label}</span>
        <small>{percent(value, total).toFixed(1)}% of catalog</small>
      </div>
      <strong>{value.toLocaleString('en-US')}</strong>
    </div>
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
    <div>
      <h3 className="admin-fill-subtitle">Top 10k source coverage & daily headroom</h3>
      <div className="admin-budget-list">
        {primaryScoreRows.map(([source, coverage]) => {
          const applicable = coverage.applicable || totalGames
          const coveragePercent = percent(coverage.live, applicable)
          return (
            <div className="admin-source-coverage" key={`coverage-${source}`}>
              <div>
                <span>{source}</span>
                <small>{ratio(coverage.live, applicable)} applicable games</small>
              </div>
              <div className="admin-budget-track">
                <i style={{ width: `${coveragePercent}%` }} />
              </div>
              <strong>{coveragePercent.toFixed(1)}%</strong>
            </div>
          )
        })}
        <div className="admin-budget-divider" />
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
    </div>
  )
}
