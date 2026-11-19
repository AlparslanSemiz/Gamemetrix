import { createContext } from 'react'
import type { CollectionKey } from './collections'
import type { Account, AccountPreferences, AccountState } from '../services/account'

/**
 * What the session endpoint said about the account system: `unknown` until it
 * answers, `enabled`/`disabled` from its `accounts_enabled` flag, `error` when
 * it could not be read (network error, 503 load shedding). Only `disabled` means
 * accounts are switched off; `error` is retryable.
 */
export type AccountsStatus = 'unknown' | 'enabled' | 'disabled' | 'error'

export interface AccountContextValue {
  account: Account | null
  accountState: AccountState | null
  isLoading: boolean
  googleLoginAvailable: boolean
  /** False until the session says accounts are on, so login entry points never flash while they are off. */
  accountsEnabled: boolean
  accountsStatus: AccountsStatus
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  syncCollection: (collection: CollectionKey, slug: string, enabled: boolean) => Promise<void>
  updatePreferences: (preferences: Partial<AccountPreferences>) => Promise<void>
  clearAccount: () => void
}

export const AccountContext = createContext<AccountContextValue | null>(null)
