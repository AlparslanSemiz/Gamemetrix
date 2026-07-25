import type { AdminDashboard } from '../../../services/admin'
import { formatAdminNumber } from '../format'
import { TRAFFIC_DAY_OPTIONS } from '../useAdminDashboard'
import { Panel } from './Panel'
import { percent } from './math'

const DENSE_TRAFFIC_THRESHOLD = 10
const MINIMUM_TRAFFIC_BAR_PERCENT = 6

export function TrafficPanel({
  dashboard,
  isLoading,
  maxDailyVisits,
  trafficDays,
  onChangeDays,
}: {
  dashboard: AdminDashboard | null
  isLoading: boolean
  maxDailyVisits: number
  trafficDays: number
  onChangeDays: (days: number) => void
}) {
  const daily = dashboard?.traffic.daily ?? []
  const barsClass = `admin-traffic-bars${
    trafficDays > DENSE_TRAFFIC_THRESHOLD ? ' admin-traffic-dense' : ''
  }`

  return (
    <Panel
      title="Traffic"
      width="wide"
      action={
        <DayPicker
          isLoading={isLoading}
          trafficDays={trafficDays}
          onChangeDays={onChangeDays}
        />
      }
    >
      <div
        className={barsClass}
        style={{
          gridTemplateColumns: `repeat(${daily.length || trafficDays}, minmax(0, 1fr))`,
        }}
      >
        {daily.map((row) => (
          <div
            className="admin-traffic-day"
            key={row.date}
            title={`${row.date}: ${row.visits} page views, ${row.visitors} browser IDs`}
          >
            <div className="admin-bar-track">
              <span
                style={{
                  height: `${Math.max(
                    MINIMUM_TRAFFIC_BAR_PERCENT,
                    percent(row.visits, maxDailyVisits),
                  )}%`,
                }}
              />
            </div>
            <strong>{row.visits}</strong>
            <small>{row.date.slice(5)}</small>
          </div>
        ))}
      </div>
      <TrafficTotals dashboard={dashboard} />
    </Panel>
  )
}

function DayPicker({
  isLoading,
  trafficDays,
  onChangeDays,
}: {
  isLoading: boolean
  trafficDays: number
  onChangeDays: (days: number) => void
}) {
  return (
    <div className="admin-day-picker" role="group" aria-label="Traffic range">
      {TRAFFIC_DAY_OPTIONS.map((option) => (
        <button
          key={option}
          type="button"
          className={option === trafficDays ? 'is-active' : ''}
          onClick={() => onChangeDays(option)}
          disabled={isLoading}
        >
          {option}d
        </button>
      ))}
    </div>
  )
}

function TrafficTotals({ dashboard }: { dashboard: AdminDashboard | null }) {
  const totals: readonly (readonly [number, string])[] = [
    [dashboard?.traffic.total_visits ?? 0, 'page views'],
    [dashboard?.traffic.unique_visitors ?? 0, 'browser IDs'],
    [dashboard?.traffic.unique_ips ?? 0, 'network IDs'],
    [dashboard?.traffic.unique_today ?? 0, 'browser IDs today'],
  ]
  return (
    <div className="admin-inline-stats">
      {totals.map(([value, label]) => (
        <span key={label}>
          {formatAdminNumber(value)} {label}
        </span>
      ))}
    </div>
  )
}
