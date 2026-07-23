import { useMemo, useState } from 'react'

import type { Account, AccountPreferences, AccountState } from '../../services/account'
import { useAccount } from '../../state/useAccount'
import { AlertList } from './AlertList'
import { AlertPreferencesForm, AlertsStatus, AlertsToolbar } from './AlertsChrome'
import { buildAlerts } from './buildAlerts'
import { useAlertPreferenceSync, useAlertReadActions, useWatchlistAlertGames } from './hooks'
import { loadPreferences, loadStringSet } from './storage'
import { DISMISSED_KEY, READ_KEY, type AlertPreferences } from './types'

export function AlertsPanel({ watchlistSlugs }: { watchlistSlugs: string[] }) {
  const accountContext = useAccount()
  // Remounting on identity change resets locally-held read/dismissed state so a
  // sign-in never shows the previous user's alerts.
  const stateKey = accountContext.accountState
    ? `account:${accountContext.accountState.account.id}`
    : accountContext.isLoading
      ? 'loading'
      : 'guest'

  return (
    <AlertsPanelContent
      key={stateKey}
      watchlistSlugs={watchlistSlugs}
      account={accountContext.account}
      accountState={accountContext.accountState}
      updatePreferences={accountContext.updatePreferences}
    />
  )
}

function initialPreferences(accountState: AccountState | null): AlertPreferences {
  if (!accountState) return loadPreferences()
  return {
    minDiscount: accountState.preferences.min_discount,
    minScore: accountState.preferences.min_score,
    upcomingDays: accountState.preferences.upcoming_days,
  }
}

function AlertsPanelContent({
  watchlistSlugs,
  account,
  accountState,
  updatePreferences,
}: {
  watchlistSlugs: string[]
  account: Account | null
  accountState: AccountState | null
  updatePreferences: (preferences: Partial<AccountPreferences>) => Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [readIds, setReadIds] = useState(() =>
    accountState ? new Set(accountState.read_alerts) : loadStringSet(READ_KEY),
  )
  const [dismissedIds, setDismissedIds] = useState(() =>
    accountState ? new Set(accountState.dismissed_alerts) : loadStringSet(DISMISSED_KEY),
  )
  const [preferences, setPreferences] = useState<AlertPreferences>(() =>
    initialPreferences(accountState),
  )

  useAlertPreferenceSync(account, accountState, preferences, updatePreferences, setError)
  const { games, isLoading } = useWatchlistAlertGames(watchlistSlugs, refreshKey, setError)

  const alerts = useMemo(
    () => buildAlerts(games, preferences).filter((alert) => !dismissedIds.has(alert.id)),
    [dismissedIds, games, preferences],
  )
  const unreadCount = alerts.filter((alert) => !readIds.has(alert.id)).length
  const actions = useAlertReadActions({
    account,
    alerts,
    dismissedIds,
    readIds,
    setDismissedIds,
    setError,
    setReadIds,
  })

  return (
    <div className="alerts-panel">
      <AlertsToolbar
        isLoading={isLoading}
        onMarkAllRead={actions.markAllRead}
        onRefresh={() => setRefreshKey((value) => value + 1)}
        unreadCount={unreadCount}
        watchlistCount={watchlistSlugs.length}
      />

      <AlertPreferencesForm preferences={preferences} setPreferences={setPreferences} />

      <AlertsStatus
        alertCount={alerts.length}
        error={error}
        isLoading={isLoading}
        watchlistCount={watchlistSlugs.length}
      />

      <AlertList
        alerts={alerts}
        readIds={readIds}
        onDismiss={actions.dismiss}
        onOpen={actions.open}
      />
    </div>
  )
}
