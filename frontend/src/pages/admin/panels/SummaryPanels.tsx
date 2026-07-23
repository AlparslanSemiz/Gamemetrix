import type { AdminApiHealth, AdminDashboard } from '../../../services/admin'
import { adminHealthClass } from '../format'
import { AdminRow, ListOrEmpty, Panel, PathRow, RowList, TextRow } from './Panel'

export function SummaryPanels({
  dashboard,
  health,
}: {
  dashboard: AdminDashboard | null
  health: AdminApiHealth
}) {
  return (
    <>
      <TopPagesPanel dashboard={dashboard} />
      <ApiHealthPanel health={health} />
      <AccountsPanel dashboard={dashboard} />
      <OrganicPanel dashboard={dashboard} />
      <SeoPanel dashboard={dashboard} />
    </>
  )
}

function TopPagesPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  const pages = dashboard?.traffic.top_pages ?? []
  return (
    <Panel title="Top Pages">
      <RowList>
        <ListOrEmpty isEmpty={pages.length === 0} emptyText="No visits yet.">
          {pages.map((page) => (
            <PathRow key={page.path} path={page.path} visits={page.visits} />
          ))}
        </ListOrEmpty>
      </RowList>
    </Panel>
  )
}

function ApiHealthPanel({ health }: { health: AdminApiHealth }) {
  return (
    <Panel title="API Health">
      <div className="admin-health-list">
        {Object.entries(health).map(([source, status]) => (
          <div className="admin-health-row" key={source}>
            <span className={`admin-dot ${adminHealthClass(status)}`} />
            <div>
              <strong>{source}</strong>
              <small title={status.message}>
                {status.message ?? (status.configured ? status.status : 'not configured')}
              </small>
            </div>
            {status.latency_ms ? <em>{Math.round(status.latency_ms)}ms</em> : null}
          </div>
        ))}
      </div>
    </Panel>
  )
}

function AccountsPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  return (
    <Panel title="Accounts">
      <RowList>
        <AdminRow label="Registered" value={dashboard?.accounts.registered ?? 0} />
        <AdminRow label="Verified" value={dashboard?.accounts.verified ?? 0} />
        <AdminRow label="Active in 30 days" value={dashboard?.accounts.active_30d ?? 0} />
        <TextRow
          label="Signup conversion"
          value={`${(dashboard?.acquisition.signup_conversion ?? 0).toFixed(2)}%`}
        />
        <AdminRow
          label="Store outbound"
          value={dashboard?.acquisition.outbound_store_clicks ?? 0}
        />
        {Object.entries(dashboard?.acquisition.events ?? {}).map(([event, count]) => (
          <AdminRow key={event} label={event.replaceAll('_', ' ')} value={count} />
        ))}
      </RowList>
    </Panel>
  )
}

function OrganicPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  const pages = dashboard?.acquisition.organic_landing_pages ?? []
  return (
    <Panel title="Organic Landing Pages">
      <RowList>
        <ListOrEmpty
          isEmpty={pages.length === 0}
          emptyText="No Google referrals in this range."
        >
          {pages.map((page) => (
            <PathRow key={page.path} path={page.path} visits={page.visits} />
          ))}
        </ListOrEmpty>
        <AdminRow
          label="Repeat visitors"
          value={dashboard?.acquisition.repeat_visitors ?? 0}
        />
        <AdminRow
          label="Google visitors"
          value={dashboard?.acquisition.organic_visitors ?? 0}
        />
        <AdminRow
          label="Google signups"
          value={dashboard?.acquisition.organic_signups ?? 0}
        />
        <TextRow
          label="Google conversion"
          value={`${(dashboard?.acquisition.organic_signup_conversion ?? 0).toFixed(2)}%`}
        />
      </RowList>
    </Panel>
  )
}

function SeoPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  const exclusions = Object.entries(dashboard?.catalog.seo_exclusions ?? {}).sort(
    ([, left], [, right]) => right - left,
  )
  return (
    <Panel title="SEO Exclusions">
      <RowList>
        {exclusions.map(([reason, count]) => (
          <AdminRow key={reason} label={reason.replaceAll('_', ' ')} value={count} />
        ))}
      </RowList>
    </Panel>
  )
}
