import { Link } from 'react-router'

import type { AdminDashboard } from '../../../services/admin'
import {
  formatAdminDateTime,
  formatAdminNumber,
} from '../format'
import { ListOrEmpty, Panel } from './Panel'

export function CatalogAdditionsPanel({
  dashboard,
}: {
  dashboard: AdminDashboard | null
}) {
  const additions = dashboard?.catalog.additions
  const daily = additions?.daily ?? []
  const recent = additions?.recent ?? []
  const maxDaily = Math.max(1, ...daily.map((row) => row.count))

  return (
    <Panel
      title="Catalog Additions"
      width="full"
      action={<span>{additions ? `${additions.days}-day activity` : 'Loading…'}</span>}
    >
      <div className="admin-addition-summary">
        <AdditionMetric label="Last 24 hours" value={additions?.last_24h ?? 0} />
        <AdditionMetric label="Last 7 days" value={additions?.last_7d ?? 0} />
        <AdditionMetric label="Last 30 days" value={additions?.last_30d ?? 0} />
      </div>

      <div
        className={daily.length > 14
          ? 'admin-addition-bars is-dense'
          : 'admin-addition-bars'}
        aria-label="Games added per day"
      >
        {daily.map((row) => (
          <div className="admin-addition-day" key={row.date} title={`${row.date}: ${row.count}`}>
            <span className="admin-addition-track">
              <i style={{ height: `${Math.max(3, (row.count / maxDaily) * 100)}%` }} />
            </span>
            <strong>{formatAdminNumber(row.count)}</strong>
            <small>{shortDate(row.date)}</small>
          </div>
        ))}
      </div>

      <div className="admin-addition-list">
        <ListOrEmpty
          isEmpty={recent.length === 0}
          emptyText="No tracked catalog additions yet."
        >
          {recent.map((game) => (
            <div className="admin-addition-row" key={game.id}>
              <Link to={`/game/${game.slug}`} target="_blank">
                {game.title}
              </Link>
              <span>{game.sources.join(', ') || 'source pending'}</span>
              <time dateTime={game.added_at}>
                {formatAdminDateTime(game.added_at)}
              </time>
            </div>
          ))}
        </ListOrEmpty>
      </div>

      {additions?.untracked_games ? (
        <p className="admin-addition-note">
          {formatAdminNumber(additions.untracked_games)} legacy games have no
          reconstructable addition timestamp and are excluded from these totals.
        </p>
      ) : null}
    </Panel>
  )
}

function AdditionMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{formatAdminNumber(value)}</strong>
    </div>
  )
}

function shortDate(value: string): string {
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: 'short',
  }).format(new Date(`${value}T00:00:00Z`))
}
