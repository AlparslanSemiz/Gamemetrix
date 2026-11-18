import { createContext } from 'react'
import type { CollectionKey } from './collections'
import type { Account, AccountPreferences, AccountState } from '../services/account'

export interface AccountContextValue {
  account: Account | null
  accountState: AccountState | null
  isLoading: boolean
  googleLoginAvailable: boolean
  /** False until the session says accounts are on, so login entry points never flash while they are off. */
  accountsEnabled: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  syncCollection: (collection: CollectionKey, slug: string, enabled: boolean) => Promise<void>
  updatePreferences: (preferences: Partial<AccountPreferences>) => Promise<void>
  clearAccount: () => void
}

export const AccountContext = createContext<AccountContextValue | null>(null)
