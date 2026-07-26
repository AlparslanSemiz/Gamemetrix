import type { CollectionKey, Collections } from '../state/collections'

export interface Account {
  id: string
  email: string
  display_name: string
  email_verified: boolean
  created_at: string
}

export interface AccountPreferences {
  min_discount: number
  min_score: number
  upcoming_days: number
  email_digest_enabled: boolean
  marketing_enabled: boolean
  settings: Record<string, unknown>
}

export interface AccountState {
  account: Account
  collections: Collections
  preferences: AccountPreferences
  read_alerts: string[]
  dismissed_alerts: string[]
}

export class AccountApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'AccountApiError'
    this.status = status
  }
}

function csrfToken(): string {
  if (typeof document === 'undefined') return ''
  const value = document.cookie
    .split('; ')
    .find((part) => part.startsWith('gm_csrf='))
    ?.slice('gm_csrf='.length)
  return value ? decodeURIComponent(value) : ''
}

async function accountFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const mutation = !['GET', 'HEAD', 'OPTIONS'].includes(method)
  const response = await fetch(`/api/account${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(mutation && csrfToken() ? { 'X-CSRF-Token': csrfToken() } : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    let message = 'The account request could not be completed.'
    try {
      const data = await response.json() as { detail?: unknown }
      if (typeof data.detail === 'string') {
        message = data.detail
      } else if (Array.isArray(data.detail)) {
        const validationMessages = data.detail.flatMap((entry) => {
          if (!entry || typeof entry !== 'object') return []
          const value = (entry as { msg?: unknown }).msg
          return typeof value === 'string' ? [value] : []
        })
        if (validationMessages.length) message = validationMessages.slice(0, 3).join(' ')
      }
    } catch {
      // Keep the stable fallback for non-JSON proxy errors.
    }
    throw new AccountApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function getCurrentAccount(): Promise<{ account: Account }> {
  return accountFetch('/me')
}

export function getAccountSession(): Promise<{ account: Account | null }> {
  return accountFetch('/session')
}

export function getAccountState(): Promise<AccountState> {
  return accountFetch('/state')
}

export function registerAccount(payload: { display_name: string; email: string; password: string }) {
  return accountFetch<{ message: string }>('/register', { method: 'POST', body: JSON.stringify(payload) })
}

export function loginAccount(payload: { email: string; password: string }) {
  return accountFetch<{ account: Account }>('/login', { method: 'POST', body: JSON.stringify(payload) })
}

export function logoutAccount() {
  return accountFetch<{ message: string }>('/logout', { method: 'POST' })
}

export function requestPasswordReset(email: string) {
  return accountFetch<{ message: string }>('/password/forgot', { method: 'POST', body: JSON.stringify({ email }) })
}

export function resetAccountPassword(token: string, password: string) {
  return accountFetch<{ message: string }>('/password/reset', { method: 'POST', body: JSON.stringify({ token, password }) })
}

export function verifyAccountEmail(token: string, password: string) {
  return accountFetch<{ message: string }>('/email/verify', { method: 'POST', body: JSON.stringify({ token, password }) })
}

export function unsubscribeEmailDigest(token: string) {
  return accountFetch<{ message: string }>('/email/unsubscribe', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export function mergeAccountState(payload: Omit<AccountState, 'account'>): Promise<AccountState> {
  return accountFetch('/state/merge', { method: 'POST', body: JSON.stringify(payload) })
}

export function syncCollection(collection: CollectionKey, slug: string, enabled: boolean) {
  return accountFetch<void>(`/collections/${collection}/${encodeURIComponent(slug)}`, {
    method: enabled ? 'PUT' : 'DELETE',
  })
}

export function patchAccountPreferences(payload: Partial<AccountPreferences>): Promise<AccountPreferences> {
  return accountFetch('/preferences', { method: 'PATCH', body: JSON.stringify(payload) })
}

export function setAccountAlertState(alertKey: string, state: 'read' | 'dismissed') {
  return accountFetch<void>(`/alert-state/${encodeURIComponent(alertKey)}`, {
    method: 'PUT',
    body: JSON.stringify({ state }),
  })
}

export function setAccountAlertStates(alertKeys: string[], state: 'read' | 'dismissed') {
  return accountFetch<void>('/alert-state', {
    method: 'PUT',
    body: JSON.stringify({ keys: alertKeys.slice(0, 1000), state }),
  })
}

export function exportAccountData(): Promise<AccountState & { exported_at: string }> {
  return accountFetch('/export')
}

export function deleteAccountData(currentPassword?: string) {
  return accountFetch<{ message: string }>('', {
    method: 'DELETE',
    body: JSON.stringify({ confirmation: 'DELETE', current_password: currentPassword || null }),
  })
}
