import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

import {
  setAccountAlertState,
  setAccountAlertStates,
  type Account,
  type AccountPreferences,
  type AccountState,
} from '../../services/account'
import { getCatalogGamesBySlugs } from '../../services/games'
import type { CatalogGame } from '../../types/game'
import { persistSet } from './storage'
import {
  DISMISSED_KEY,
  PREFERENCES_KEY,
  READ_KEY,
  type AlertPreferences,
  type GameAlert,
} from './types'

const PREFERENCE_SYNC_DELAY_MS = 500
const WATCHLIST_SLUG_LIMIT = 100
const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

export function useAlertPreferenceSync(
  account: Account | null,
  accountState: AccountState | null,
  preferences: AlertPreferences,
  updatePreferences: (preferences: Partial<AccountPreferences>) => Promise<void>,
  setError: (message: string | null) => void,
) {
  useEffect(() => {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences))
    if (!account) return
    if (
      accountState?.preferences.min_discount === preferences.minDiscount
      && accountState.preferences.min_score === preferences.minScore
      && accountState.preferences.upcoming_days === preferences.upcomingDays
    ) return

    const timer = window.setTimeout(() => {
      void updatePreferences({
        min_discount: preferences.minDiscount,
        min_score: preferences.minScore,
        upcoming_days: preferences.upcomingDays,
      }).catch(() => setError('Alert preferences could not be synchronized.'))
    }, PREFERENCE_SYNC_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [account, accountState, preferences, setError, updatePreferences])
}

export function useWatchlistAlertGames(
  watchlistSlugs: string[],
  refreshKey: number,
  setError: (message: string | null) => void,
) {
  const [games, setGames] = useState<CatalogGame[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const uniqueSlugs = Array.from(new Set(watchlistSlugs))
      .filter((slug) => SLUG_PATTERN.test(slug))
      .slice(0, WATCHLIST_SLUG_LIMIT)

    async function loadWatchlistGames() {
      if (!uniqueSlugs.length) {
        setGames([])
        setError(null)
        setIsLoading(false)
        return
      }
      setIsLoading(true)
      setError(null)

      try {
        const loaded = await getCatalogGamesBySlugs(uniqueSlugs, true)
        if (!cancelled) {
          setGames(loaded)
          setError(loaded.length ? null : 'Wishlist alerts could not be loaded.')
          setIsLoading(false)
        }
      } catch {
        if (!cancelled) {
          setGames([])
          setError('Wishlist alerts could not be loaded.')
          setIsLoading(false)
        }
      }
    }

    void loadWatchlistGames()
    return () => {
      cancelled = true
    }
  }, [refreshKey, setError, watchlistSlugs])

  return { games, isLoading }
}

export interface AlertReadActions {
  dismiss: (id: string) => void
  markAllRead: () => void
  open: (id: string) => void
}

export function useAlertReadActions({
  account,
  alerts,
  dismissedIds,
  readIds,
  setDismissedIds,
  setError,
  setReadIds,
}: {
  account: Account | null
  alerts: GameAlert[]
  dismissedIds: Set<string>
  readIds: Set<string>
  setDismissedIds: Dispatch<SetStateAction<Set<string>>>
  setError: Dispatch<SetStateAction<string | null>>
  setReadIds: Dispatch<SetStateAction<Set<string>>>
}): AlertReadActions {
  const markRead = (ids: string[]) => {
    const next = new Set(readIds)
    ids.forEach((id) => next.add(id))
    setReadIds(next)
    persistSet(READ_KEY, next)
  }

  const markAllRead = () => {
    const unread = alerts.filter((alert) => !readIds.has(alert.id)).map((alert) => alert.id)
    markRead(alerts.map((alert) => alert.id))
    if (account) {
      void setAccountAlertStates(unread, 'read').catch(() =>
        setError('Read status could not be synchronized.'),
      )
    }
  }

  const dismiss = (id: string) => {
    const next = new Set(dismissedIds).add(id)
    setDismissedIds(next)
    persistSet(DISMISSED_KEY, next)
    if (account) {
      void setAccountAlertState(id, 'dismissed').catch(() =>
        setError('Dismissal could not be synchronized.'),
      )
    }
  }

  const open = (id: string) => {
    markRead([id])
    if (account) void setAccountAlertState(id, 'read').catch(() => undefined)
  }

  return { dismiss, markAllRead, open }
}
