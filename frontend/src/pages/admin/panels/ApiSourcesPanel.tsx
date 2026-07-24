import type { ApiSource, ApiSources } from '../../../services/admin'
import { formatAdminNumber, formatRelativeTime } from '../format'
import { Panel } from './Panel'

const MINIMUM_BAR_PERCENT = 3
const LOW_REMAINING_RATIO = 0.15

const HEADROOM_TAG: Record<ApiSource['headroom'], { label: string; cls: string }> = {
  headroom: { label: 'room to raise', cls: 'is-on' },
  capped: { label: 'at ceiling', cls: 'is-bad' },
  metered: { label: 'billed', cls: 'is-warn' },
  window: { label: 'windowed', cls: 'is-off' },
  scrape: { label: 'scraped', cls: 'is-off' },
}

export interface ApiSourcesPanelProps {
  apiSources: ApiSources | null
}

export function ApiSourcesPanel({ apiSources }: ApiSourcesPanelProps) {
  const sources = apiSources?.sources ?? []
  return (
    <Panel title="API Sources" width="full">
      <p className="admin-src-note">
        Every source is pulled periodically within its own daily budget (resets at
        midnight). Metered sources bill on overage; Metacritic shares RAWG&apos;s budget.
      </p>
      <div className="admin-src-list">
        {sources.map((source) => (
          <SourceRow key={source.key} source={source} />
        ))}
        {apiSources && sources.length === 0 ? (
          <p className="admin-empty">No sources reported.</p>
        ) : null}
      </div>
    </Panel>
  )
}

function SourceRow({ source }: { source: ApiSource }) {
  const usable = source.usable_limit || source.limit || 1
  const remainingPercent = Math.max(0, Math.min(100, (source.remaining / usable) * 100))
  const exhausted = source.remaining <= 0
  const low = !exhausted && source.remaining < usable * LOW_REMAINING_RATIO
  const budgetClass = exhausted ? 'is-bad' : low ? 'is-warn' : 'is-ok'
  return (
    <div className="admin-src">
      <div className="admin-src-head">
        <span
          className={`admin-dot ${source.configured ? 'is-ok' : 'is-muted'}`}
          aria-hidden="true"
        />
        <div className="admin-src-title">
          <div className="admin-src-name">
            <strong>{source.display_name}</strong>
            {source.is_rating && source.weight != null ? (
              <span className="admin-chip">weight <strong>{source.weight}</strong></span>
            ) : null}
            <span className={`admin-chip ${HEADROOM_TAG[source.headroom].cls}`}>
              {HEADROOM_TAG[source.headroom].label}
            </span>
            {!source.configured ? <span className="admin-chip is-off">no key</span> : null}
          </div>
          <small>{source.role} · {source.driven_by}</small>
        </div>
        <div className="admin-src-budget">
          <div className="admin-budget-track">
            <i
              className={budgetClass}
              style={{ width: `${Math.max(MINIMUM_BAR_PERCENT, remainingPercent)}%` }}
            />
          </div>
          <strong className={exhausted ? 'is-bad-text' : undefined}>
            {formatAdminNumber(source.remaining)}/{formatAdminNumber(source.limit)}
          </strong>
        </div>
      </div>
      <div className="admin-src-meta">
        <span className="admin-src-provider">real limit: {source.provider_limit}</span>
        <span>{formatAdminNumber(source.used)} used today</span>
        <span>reserve {source.reserve_percent}%</span>
        {Object.entries(source.windows).map(([kind, window]) => (
          <span key={kind}>
            {kind} {formatAdminNumber(window.remaining)}/{formatAdminNumber(window.limit)} left
          </span>
        ))}
        <span>last used: {formatRelativeTime(source.last_used_at)}</span>
      </div>
    </div>
  )
}
