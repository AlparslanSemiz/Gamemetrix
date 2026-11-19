/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AccountApiError,
  getAccountSession,
  getAccountState,
  loginAccount,
  logoutAccount,
  mergeAccountState,
  patchAccountPreferences,
  syncCollection as persistCollection,
  type Account,
  type AccountPreferences,
  type AccountState,
} from '../services/account'
import { emptyCollections, loadCollections, type CollectionKey } from './collections'
import { AccountContext, type AccountsStatus } from './account'
import { enqueueSync } from './syncQueue'
import { useCollections } from './useCollections'

const READ_KEY = 'gamemetrix.alerts.read.v1'
const DISMISSED_KEY = 'gamemetrix.alerts.dismissed.v1'
const PREFERENCES_KEY = 'gamemetrix.alerts.preferences.v1'

function stringList(key: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').slice(0, 5000) : []
  } catch {
    return []
  }
}

function guestPreferences(): AccountPreferences {
  try {
    const value = JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? '{}') as Record<string, unknown>
    return {
      min_discount: Math.min(90, Math.max(1, Number(value.minDiscount) || 20)),
      min_score: Math.min(100, Math.max(1, Number(value.minScore) || 80)),
      upcoming_days: Math.min(365, Math.max(1, Number(value.upcomingDays) || 45)),
      email_digest_enabled: false,
      marketing_enabled: false,
      settings: {},
    }
  } catch {
    return { min_discount: 20, min_score: 80, upcoming_days: 45, email_digest_enabled: false, marketing_enabled: false, settings: {} }
  }
}

function persistAlertState(state: AccountState) {
  localStorage.setItem(READ_KEY, JSON.stringify(state.read_alerts))
  localStorage.setItem(DISMISSED_KEY, JSON.stringify(state.dismissed_alerts))
  localStorage.setItem(PREFERENCES_KEY, JSON.stringify({
    minDiscount: state.preferences.min_discount,
    minScore: state.preferences.min_score,
    upcomingDays: state.preferences.upcoming_days,
  }))
}

function clearPersistedAlertState() {
  localStorage.removeItem(READ_KEY)
  localStorage.removeItem(DISMISSED_KEY)
  localStorage.removeItem(PREFERENCES_KEY)
}

function useAccountHydration(
  replaceCollections: ReturnType<typeof useCollections>['replaceCollections'],
) {
  const [account, setAccount] = useState<Account | null>(null)
  const [accountState, setAccountState] = useState<AccountState | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [googleLoginAvailable, setGoogleLoginAvailable] = useState(false)
  const [accountsStatus, setAccountsStatus] = useState<AccountsStatus>('unknown')
  const accountsEnabled = accountsStatus === 'enabled'

  const applyState = useCallback((state: AccountState) => {
    setAccount(state.account)
    setAccountState(state)
    replaceCollections(state.collections)
    persistAlertState(state)
  }, [replaceCollections, setAccount, setAccountState])

  const hydrate = useCallback(async (mergeGuest: boolean) => {
    let current: Awaited<ReturnType<typeof getAccountSession>>
    try {
      current = await getAccountSession()
    } catch (error) {
      // Not knowing is not the same as "switched off": keep it retryable.
      setAccountsStatus('error')
      throw error
    }
    setGoogleLoginAvailable(current.google_login === true)
    setAccountsStatus(current.accounts_enabled === true ? 'enabled' : 'disabled')
    if (!current.account) {
      setAccount(null)
      setAccountState(null)
      return
    }
    setAccount(current.account)
    if (mergeGuest) {
      const merged = await mergeAccountState({
        collections: loadCollections(),
        preferences: guestPreferences(),
        read_alerts: stringList(READ_KEY),
        dismissed_alerts: stringList(DISMISSED_KEY),
      })
      applyState(merged)
      return
    }
    applyState(await getAccountState())
  }, [applyState])

  useEffect(() => {
    let active = true
    hydrate(true)
      .catch((error: unknown) => {
        // 401: no session. 503: load shedding; the UI shows a retryable
        // message, so neither is worth a console warning.
        const expected = error instanceof AccountApiError
          && (error.status === 401 || error.status === 503)
        if (active && !expected) {
          console.warn('Account state could not be loaded.', error)
        }
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => { active = false }
  }, [hydrate])

  return {
    account,
    accountState,
    accountsEnabled,
    accountsStatus,
    googleLoginAvailable,
    hydrate,
    isLoading,
    setAccount,
    setAccountState,
  }
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const { replaceCollections } = useCollections()
  const state = useAccountHydration(replaceCollections)
  const {
    account,
    accountState,
    accountsEnabled,
    accountsStatus,
    googleLoginAvailable,
    hydrate,
    isLoading,
    setAccount,
    setAccountState,
  } = state

  const login = useCallback(async (email: string, password: string) => {
    await loginAccount({ email, password })
    await hydrate(true)
  }, [hydrate])

  const logout = useCallback(async () => {
    await logoutAccount()
    clearPersistedAlertState()
    setAccount(null)
    setAccountState(null)
    replaceCollections({ ...emptyCollections })
  }, [replaceCollections, setAccount, setAccountState])

  const refresh = useCallback(async () => {
    await hydrate(false)
  }, [hydrate])

  const syncCollection = useCallback(async (collection: CollectionKey, slug: string, enabled: boolean) => {
    if (!account) return
    await enqueueSync(`${slug}:${collection}`, () => persistCollection(collection, slug, enabled))
  }, [account])

  const updatePreferences = useCallback(async (next: Partial<AccountPreferences>) => {
    if (!account) return
    const preferences = await patchAccountPreferences(next)
    setAccountState((current) => current ? { ...current, preferences } : current)
  }, [account, setAccountState])

  const clearAccount = useCallback(() => {
    clearPersistedAlertState()
    setAccount(null)
    setAccountState(null)
    replaceCollections({ ...emptyCollections })
  }, [replaceCollections, setAccount, setAccountState])

  const value = useMemo(() => ({
    account,
    accountState,
    accountsEnabled,
    accountsStatus,
    googleLoginAvailable,
    isLoading,
    login,
    logout,
    refresh,
    syncCollection,
    updatePreferences,
    clearAccount,
  }), [account, accountState, accountsEnabled, accountsStatus, clearAccount, googleLoginAvailable, isLoading, login, logout, refresh, syncCollection, updatePreferences])

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
}
