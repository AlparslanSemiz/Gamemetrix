import { Database, Eye, Monitor, Network, ShieldCheck, UserCheck, Users } from 'lucide-react'

import type { AdminDashboard } from '../../../services/admin'
import { formatAdminNumber } from '../format'

export function AdminMetrics({ dashboard }: { dashboard: AdminDashboard | null }) {
  const metrics = [
    [Database, 'Total games', dashboard?.catalog.total_games ?? 0],
    [Eye, 'Page views all time', dashboard?.traffic.total_visits_all_time ?? 0],
    [Monitor, 'Browser IDs all time', dashboard?.traffic.total_unique_visitors ?? 0],
    [Network, 'Network IDs all time', dashboard?.traffic.total_unique_ips ?? 0],
    [Users, 'Sessions all time', dashboard?.traffic.total_sessions_all_time ?? 0],
    [Eye, 'Page views today', dashboard?.traffic.visits_today ?? 0],
    [UserCheck, 'Known account visitors', dashboard?.traffic.known_account_visitors ?? 0],
    [Users, 'Registered accounts', dashboard?.accounts.registered ?? 0],
    [ShieldCheck, 'Game pages in sitemap', dashboard?.catalog.sitemap_game_pages ?? 0],
    [Eye, 'Google-referrer sessions', dashboard?.acquisition.organic_sessions ?? 0],
  ] as const

  return (
    <>
      <section className="admin-metric-grid" aria-label="Key metrics">
        {metrics.map(([Icon, label, value]) => (
          <article className="admin-metric" key={label}>
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
            <strong>{formatAdminNumber(value)}</strong>
          </article>
        ))}
      </section>
      <p className="admin-identity-note">
        Browser IDs approximate browser profiles; network IDs are hashed IP addresses
        that can be shared or change. Neither metric is an exact person count.
        Bot filtering applies to newly collected traffic.
      </p>
    </>
  )
}
