import {
  Activity,
  Bot,
  ChartNoAxesCombined,
  Database,
  Gauge,
  LogOut,
  RefreshCw,
  Workflow,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import {
  ActivityPanels,
  AdminMetrics,
  AiChangesPanel,
  ApiSourcesPanel,
  CatalogAdditionsPanel,
  DataFillPanel,
  PeriodicJobsPanel,
  ScoreAndCatalogPanels,
  SummaryPanels,
  TrafficPanel,
} from './admin/panels'
import { AdminLogin } from './admin/AdminLogin'
import { useAdminDashboard } from './admin/useAdminDashboard'
import './AdminPage.css'

export function AdminPage() {
  const admin = useAdminDashboard()
  const [searchParams] = useSearchParams()
  const section = adminSection(searchParams.get('section'))

  if (!admin.token) {
    return (
      <AdminLogin
        error={admin.error}
        isSigningIn={admin.isSigningIn}
        password={admin.password}
        username={admin.username}
        onChangePassword={admin.setPassword}
        onChangeUsername={admin.setUsername}
        onSubmit={admin.handleLogin}
      />
    )
  }

  return (
    <main className="admin-shell">
      <div className="admin-layout">
        <AdminSidebar active={section} />
        <div className="admin-content">
          <header className="admin-header">
            <div>
              <span className="admin-kicker">Admin · {SECTION_META[section].eyebrow}</span>
              <h1>{SECTION_META[section].title}</h1>
              <p>{SECTION_META[section].description}</p>
            </div>
            <div className="admin-header-actions">
              <small>
                Auto-refresh 60s
                {admin.lastUpdatedAt
                  ? ` · ${admin.lastUpdatedAt.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}`
                  : ''}
              </small>
              <button
                type="button"
                onClick={admin.loadDashboard}
                disabled={admin.isLoading}
              >
                <RefreshCw size={16} aria-hidden="true" />
                <span>{admin.isLoading ? 'Refreshing' : 'Refresh'}</span>
              </button>
              <button type="button" onClick={admin.handleLogout}>
                <LogOut size={16} aria-hidden="true" />
                <span>Logout</span>
              </button>
            </div>
          </header>

          {admin.error ? <p className="admin-error">{admin.error}</p> : null}
          <AdminSection admin={admin} section={section} />
        </div>
      </div>
    </main>
  )
}

type AdminSectionId = 'overview' | 'catalog' | 'automation' | 'traffic' | 'activity'
type AdminState = ReturnType<typeof useAdminDashboard>

const SECTIONS = [
  ['overview', Gauge, 'Overview'],
  ['catalog', Database, 'Catalog'],
  ['automation', Workflow, 'Automation'],
  ['traffic', ChartNoAxesCombined, 'Traffic'],
  ['activity', Activity, 'Activity & AI'],
] as const

const SECTION_META: Record<AdminSectionId, {
  eyebrow: string
  title: string
  description: string
}> = {
  overview: {
    eyebrow: 'Overview',
    title: 'System overview',
    description: 'Health, accounts, acquisition and the key operating metrics.',
  },
  catalog: {
    eyebrow: 'Catalog',
    title: 'Catalog growth',
    description: 'New games, score coverage, indexing and catalog controls.',
  },
  automation: {
    eyebrow: 'Automation',
    title: 'Jobs & data sources',
    description: 'Periodic jobs, provider budgets and controlled data-fill runs.',
  },
  traffic: {
    eyebrow: 'Traffic',
    title: 'Traffic & visitors',
    description: 'Visits, landing pages, browser identities and network activity.',
  },
  activity: {
    eyebrow: 'Activity',
    title: 'Activity & AI changes',
    description: 'AI-driven game changes and the protected admin audit trail.',
  },
}

function adminSection(value: string | null): AdminSectionId {
  return SECTIONS.some(([id]) => id === value) ? value as AdminSectionId : 'overview'
}

function AdminSidebar({ active }: { active: AdminSectionId }) {
  return (
    <aside className="admin-sidebar">
      <Link className="admin-sidebar-brand" to="/">
        Game<span>Metrix</span>
      </Link>
      <nav aria-label="Admin sections">
        {SECTIONS.map(([id, Icon, label]) => (
          <Link
            className={active === id ? 'is-active' : ''}
            key={id}
            to={id === 'overview' ? '/admin' : `/admin?section=${id}`}
          >
            <Icon size={17} aria-hidden="true" />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
      <div className="admin-sidebar-note">
        <Bot size={15} aria-hidden="true" />
        AI changes are stored as before/after audit records.
      </div>
    </aside>
  )
}

function AdminSection({
  admin,
  section,
}: {
  admin: AdminState
  section: AdminSectionId
}) {
  if (section === 'overview') {
    return (
      <>
        <AdminMetrics dashboard={admin.dashboard} />
        <section className="admin-grid">
          <SummaryPanels dashboard={admin.dashboard} health={admin.health} />
        </section>
      </>
    )
  }
  if (section === 'catalog') {
    return (
      <section className="admin-grid">
        <CatalogAdditionsPanel dashboard={admin.dashboard} />
        <ScoreAndCatalogPanels
          dashboard={admin.dashboard}
          token={admin.token}
          onScoreWeightsSaved={() => void admin.loadDashboard()}
        />
      </section>
    )
  }
  if (section === 'automation') {
    return (
      <section className="admin-grid">
        <DataFillPanel
          dataFill={admin.dataFill}
          dataGaps={admin.dataGaps}
          isStartingDataFill={admin.isStartingDataFill}
          isStartingPrimaryScores={admin.isStartingPrimaryScores}
          primaryScoreRows={admin.primaryScoreRows}
          rateLimitRows={admin.rateLimitRows}
          onStartDataFill={admin.handleStartDataFill}
          onStartPrimaryScores={admin.handleStartPrimaryScores}
        />
        <PeriodicJobsPanel periodic={admin.periodic} />
        <ApiSourcesPanel apiSources={admin.apiSources} />
      </section>
    )
  }
  if (section === 'traffic') {
    return (
      <section className="admin-grid">
        <TrafficPanel
          dashboard={admin.dashboard}
          isLoading={admin.isLoading}
          maxDailyVisits={admin.maxDailyVisits}
          trafficDays={admin.trafficDays}
          onChangeDays={admin.setTrafficDays}
        />
        <ActivityPanels
          auditLogs={admin.auditLogs}
          auditOnlyFailures={admin.auditOnlyFailures}
          dashboard={admin.dashboard}
          onToggleAuditFailures={() => undefined}
          section="visitors"
        />
      </section>
    )
  }
  return (
    <section className="admin-grid">
      <AiChangesPanel changes={admin.aiChanges} />
      <ActivityPanels
        auditLogs={admin.auditLogs}
        auditOnlyFailures={admin.auditOnlyFailures}
        dashboard={admin.dashboard}
        onToggleAuditFailures={() => {
          admin.setAuditOnlyFailures((previous) => !previous)
        }}
        section="audit"
      />
    </section>
  )
}
