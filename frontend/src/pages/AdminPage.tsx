import { LogOut, RefreshCw } from 'lucide-react'
import {
  ActivityPanels,
  AdminMetrics,
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
      <header className="admin-header">
        <div>
          <span className="admin-kicker">Admin</span>
          <h1>GameMetrix Dashboard</h1>
        </div>
        <div className="admin-header-actions">
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
      <AdminMetrics dashboard={admin.dashboard} />

      <section className="admin-grid">
        <TrafficPanel
          dashboard={admin.dashboard}
          isLoading={admin.isLoading}
          maxDailyVisits={admin.maxDailyVisits}
          trafficDays={admin.trafficDays}
          onChangeDays={admin.setTrafficDays}
        />
        <SummaryPanels
          dashboard={admin.dashboard}
          health={admin.health}
        />
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
        <ScoreAndCatalogPanels
          dashboard={admin.dashboard}
          token={admin.token}
          onScoreWeightsSaved={() => {
            void admin.loadDashboard()
          }}
        />
        <ActivityPanels
          auditLogs={admin.auditLogs}
          auditOnlyFailures={admin.auditOnlyFailures}
          dashboard={admin.dashboard}
          onToggleAuditFailures={() => {
            admin.setAuditOnlyFailures((previous) => !previous)
          }}
        />
      </section>
    </main>
  )
}
