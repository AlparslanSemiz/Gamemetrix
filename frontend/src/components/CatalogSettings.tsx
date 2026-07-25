import { BarChart3, Grid2X2, List, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import type { ViewMode } from './CatalogToolbar'
import {
  setAnalyticsConsent,
  setInternalAnalyticsTraffic,
  useAnalyticsPreferences,
} from '../services/analyticsConsent'

interface CatalogSettingsProps {
  filtersOpen: boolean
  viewMode: ViewMode
  onChangeFiltersOpen: (open: boolean) => void
  onChangeViewMode: (mode: ViewMode) => void
}

export function CatalogSettings({
  filtersOpen,
  viewMode,
  onChangeFiltersOpen,
  onChangeViewMode,
}: CatalogSettingsProps) {
  const { consent, internal } = useAnalyticsPreferences()
  return (
    <div className="settings-grid">
      <section className="settings-card">
        <h2>Catalog Layout</h2>
        <div className="settings-segmented" role="group" aria-label="Catalog layout">
          <button
            type="button"
            className={viewMode === 'list' ? 'is-active' : ''}
            onClick={() => onChangeViewMode('list')}
          >
            <List size={16} aria-hidden="true" />
            <span>List</span>
          </button>
          <button
            type="button"
            className={viewMode === 'grid' ? 'is-active' : ''}
            onClick={() => onChangeViewMode('grid')}
          >
            <Grid2X2 size={16} aria-hidden="true" />
            <span>Grid</span>
          </button>
        </div>
      </section>
      <section className="settings-card">
        <h2>Analytics &amp; Privacy</h2>
        <p className="settings-description">
          Pseudonymous browser and session measurement is currently{' '}
          <strong>{consent}</strong>. Google Analytics may be used when configured;
          advertising personalization remains disabled.
        </p>
        <div className="settings-segmented" role="group" aria-label="Analytics consent">
          <button
            type="button"
            className={consent === 'granted' ? 'is-active' : ''}
            onClick={() => setAnalyticsConsent('granted')}
          >
            <BarChart3 size={16} aria-hidden="true" />
            <span>Allow</span>
          </button>
          <button
            type="button"
            className={consent === 'denied' ? 'is-active' : ''}
            onClick={() => setAnalyticsConsent('denied')}
          >
            <ShieldCheck size={16} aria-hidden="true" />
            <span>Decline</span>
          </button>
        </div>
      </section>
      <section className="settings-card">
        <h2>Internal Traffic</h2>
        <p className="settings-description">
          Exclude this browser when you test or administer GameMetrix.
          Admin sign-in enables this automatically.
        </p>
        <div className="settings-segmented" role="group" aria-label="Internal traffic exclusion">
          <button
            type="button"
            className={internal ? 'is-active' : ''}
            onClick={() => setInternalAnalyticsTraffic(true)}
          >
            <ShieldCheck size={16} aria-hidden="true" />
            <span>Exclude</span>
          </button>
          <button
            type="button"
            className={!internal ? 'is-active' : ''}
            onClick={() => setInternalAnalyticsTraffic(false)}
          >
            <BarChart3 size={16} aria-hidden="true" />
            <span>Include</span>
          </button>
        </div>
      </section>
      <section className="settings-card">
        <h2>Filter Panel</h2>
        <div className="settings-segmented" role="group" aria-label="Filter panel">
          <button
            type="button"
            className={filtersOpen ? 'is-active' : ''}
            onClick={() => onChangeFiltersOpen(true)}
          >
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span>Open</span>
          </button>
          <button
            type="button"
            className={!filtersOpen ? 'is-active' : ''}
            onClick={() => onChangeFiltersOpen(false)}
          >
            <List size={16} aria-hidden="true" />
            <span>Compact</span>
          </button>
        </div>
      </section>
    </div>
  )
}
