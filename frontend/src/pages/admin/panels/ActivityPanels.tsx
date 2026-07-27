import { Activity, ScrollText } from 'lucide-react'

import type { AdminAuditLog, AdminDashboard } from '../../../services/admin'
import { formatAdminDateTime, formatAdminNumber } from '../format'
import { ListOrEmpty, Panel } from './Panel'

export function ActivityPanels({
  auditLogs,
  auditOnlyFailures,
  dashboard,
  onToggleAuditFailures,
  section = 'all',
}: {
  auditLogs: AdminAuditLog[]
  auditOnlyFailures: boolean
  dashboard: AdminDashboard | null
  onToggleAuditFailures: () => void
  section?: 'all' | 'visitors' | 'audit'
}) {
  return (
    <>
      {section !== 'audit' ? <RecentVisitsPanel dashboard={dashboard} /> : null}
      {section !== 'audit' ? <RecentIpsPanel dashboard={dashboard} /> : null}
      {section !== 'visitors' ? (
        <AuditPanel
          auditLogs={auditLogs}
          onlyFailures={auditOnlyFailures}
          onToggleFailures={onToggleAuditFailures}
        />
      ) : null}
    </>
  )
}

function RecentVisitsPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  const visits = dashboard?.traffic.recent_visits ?? []
  return (
    <Panel
      title="Recent Visits"
      width="wide"
      action={<Activity size={16} aria-hidden="true" />}
    >
      <div className="admin-visit-table">
        <ListOrEmpty isEmpty={visits.length === 0} emptyText="No visits recorded.">
          {visits.map((visit) => (
            <div
              className="admin-visit-row"
              key={`${visit.created_at}-${visit.visitor}-${visit.path}`}
              title={visit.user_agent ?? visit.referrer ?? undefined}
            >
              <span>{formatAdminDateTime(visit.created_at)}</span>
              <strong title={visit.path}>{visit.path}</strong>
              <em>{visit.ip ?? `#${visit.ip_fingerprint ?? 'unknown'}`}</em>
              <small title={visit.account ?? undefined}>
                {visit.account
                  ?? visit.country
                  ?? visit.timezone
                  ?? visit.language
                  ?? visit.screen
                  ?? 'anonymous'}
              </small>
            </div>
          ))}
        </ListOrEmpty>
      </div>
    </Panel>
  )
}

function RecentIpsPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  const tracking = dashboard?.traffic.tracking
  const ips = dashboard?.traffic.recent_ips ?? []
  const retentionLabel = tracking?.raw_ip_enabled
    ? `${tracking.raw_ip_retention_days}d raw retention`
    : 'Raw IP storage disabled'

  return (
    <Panel title="Visitor IPs" width="full" action={<span>{retentionLabel}</span>}>
      <div className="admin-ip-table">
        <ListOrEmpty isEmpty={ips.length === 0} emptyText="No visitor IPs recorded.">
          {ips.map((entry) => (
            <div className="admin-ip-row" key={entry.fingerprint}>
              <strong>{entry.ip ?? `#${entry.fingerprint}`}</strong>
              <span>{entry.country ?? 'unknown'}</span>
              <em>{formatAdminNumber(entry.visits)} visits</em>
              <small>{formatAdminDateTime(entry.first_seen)}</small>
              <small>{formatAdminDateTime(entry.last_seen)}</small>
            </div>
          ))}
        </ListOrEmpty>
      </div>
    </Panel>
  )
}

function AuditPanel({
  auditLogs,
  onlyFailures,
  onToggleFailures,
}: {
  auditLogs: AdminAuditLog[]
  onlyFailures: boolean
  onToggleFailures: () => void
}) {
  return (
    <Panel
      title="Admin Activity"
      width="full"
      action={
        <button
          type="button"
          className={onlyFailures ? 'admin-audit-filter is-active' : 'admin-audit-filter'}
          onClick={onToggleFailures}
        >
          <ScrollText size={14} aria-hidden="true" />
          <span>{onlyFailures ? 'Failures only' : 'All requests'}</span>
        </button>
      }
    >
      <div className="admin-audit-table">
        <ListOrEmpty
          isEmpty={auditLogs.length === 0}
          emptyText="No admin activity recorded."
        >
          {auditLogs.map((entry) => (
            <div
              className={entry.success ? 'admin-audit-row' : 'admin-audit-row is-failure'}
              key={entry.id}
              title={entry.user_agent ?? undefined}
            >
              <span>{formatAdminDateTime(entry.created_at)}</span>
              <strong>{entry.username ?? 'anonymous'}</strong>
              <em>{entry.action === 'login' ? 'login' : entry.method}</em>
              <small title={entry.query ? `${entry.path}?${entry.query}` : entry.path}>
                {entry.path}
              </small>
              <span className="admin-audit-status">{entry.status_code}</span>
              <small>{entry.ip_address ?? 'unknown'}</small>
            </div>
          ))}
        </ListOrEmpty>
      </div>
    </Panel>
  )
}
