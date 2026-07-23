import { Database, Eye, ShieldCheck, Users } from 'lucide-react'

import type { AdminDashboard } from '../../../services/admin'
import { formatAdminNumber } from '../format'

export function AdminMetrics({ dashboard }: { dashboard: AdminDashboard | null }) {
  const metrics = [
    [Database, 'Total games', dashboard?.catalog.total_games ?? 0],
    [Users, 'Visitors all time', dashboard?.traffic.total_unique_visitors ?? 0],
    [ShieldCheck, 'Unique IPs all time', dashboard?.traffic.total_unique_ips ?? 0],
    [Eye, 'Visits today', dashboard?.traffic.visits_today ?? 0],
    [Users, 'Registered accounts', dashboard?.accounts.registered ?? 0],
    [Database, 'SEO pages ready', dashboard?.catalog.seo_indexable_games ?? 0],
    [Eye, 'Google sessions', dashboard?.acquisition.organic_sessions ?? 0],
  ] as const

  return (
    <section className="admin-metric-grid" aria-label="Key metrics">
      {metrics.map(([Icon, label, value]) => (
        <article className="admin-metric" key={label}>
          <Icon size={18} aria-hidden="true" />
          <span>{label}</span>
          <strong>{formatAdminNumber(value)}</strong>
        </article>
      ))}
    </section>
  )
}
