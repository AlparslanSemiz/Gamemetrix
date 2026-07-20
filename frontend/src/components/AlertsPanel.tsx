import { useEffect, useMemo, useState } from 'react'
import { Bell, CalendarDays, CheckCheck, ExternalLink, Percent, RefreshCw, Sparkles, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  setAccountAlertState,
  setAccountAlertStates,
  type Account,
  type AccountPreferences,
  type AccountState,
} from '../services/account'
import { getGameBySlug } from '../services/games'
import { useAccount } from '../state/useAccount'
import type { Game, PriceSnapshot } from '../types/game'
import { currentPriceSnapshots } from '../utils/prices'

const READ_KEY = 'gamemetrix.alerts.read.v1'
const DISMISSED_KEY = 'gamemetrix.alerts.dismissed.v1'
const PREFERENCES_KEY = 'gamemetrix.alerts.preferences.v1'

interface AlertPreferences {
  minDiscount: number
  minScore: number
  upcomingDays: number
}

interface GameAlert {
  id: string
  kind: 'free' | 'deal' | 'release' | 'score'
  title: string
  detail: string
  game: Game
}

const DEFAULT_PREFERENCES: AlertPreferences = {
  minDiscount: 20,
  minScore: 80,
  upcomingDays: 45,
}

function loadStringSet(key: string): Set<string> {
  if (typeof window === 'undefined') return new Set()
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    return new Set(Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
  } catch {
    return new Set()
  }
}

function loadPreferences(): AlertPreferences {
  if (typeof window === 'undefined') return DEFAULT_PREFERENCES
  try {
    const value = JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? '{}') as Partial<AlertPreferences>
    return {
      minDiscount: Math.min(90, Math.max(1, Number(value.minDiscount) || DEFAULT_PREFERENCES.minDiscount)),
      minScore: Math.min(100, Math.max(1, Number(value.minScore) || DEFAULT_PREFERENCES.minScore)),
      upcomingDays: Math.min(365, Math.max(1, Number(value.upcomingDays) || DEFAULT_PREFERENCES.upcomingDays)),
    }
  } catch {
    return DEFAULT_PREFERENCES
  }
}

function boundedNumber(value: string, min: number, max: number, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback
}

function bestDiscount(prices: PriceSnapshot[]): PriceSnapshot | undefined {
  return prices
    .filter((price) => (price.discount_percent ?? 0) > 0)
    .sort((a, b) => (b.discount_percent ?? 0) - (a.discount_percent ?? 0))[0]
}

function formatMoney(value: number | null | undefined, currency: string): string {
  if (value == null) return ''
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value)
  } catch {
    return `${value.toFixed(2)} ${currency}`
  }
}

function buildAlerts(games: Game[], preferences: AlertPreferences): GameAlert[] {
  const now = new Date()
  const upcomingCutoff = new Date(now.getTime() + preferences.upcomingDays * 24 * 60 * 60 * 1000)
  const alerts: GameAlert[] = []

  games.forEach((game) => {
    const prices = currentPriceSnapshots(game.price_snapshots ?? [])
    const freePrice = prices.find((price) => price.is_free || price.sale_price === 0)
    const discount = bestDiscount(prices)

    if (freePrice) {
      alerts.push({
        id: `${game.slug}:free:${freePrice.source}:${freePrice.store}`,
        kind: 'free',
        title: `${game.title} is free`,
        detail: `${freePrice.store || freePrice.source} is currently tracking this game at no cost.`,
        game,
      })
    } else if ((discount?.discount_percent ?? 0) >= preferences.minDiscount) {
      const price = formatMoney(discount?.sale_price, discount?.currency ?? 'USD')
      alerts.push({
        id: `${game.slug}:deal:${discount?.source}:${discount?.discount_percent}:${discount?.sale_price}`,
        kind: 'deal',
        title: `${game.title} is ${discount?.discount_percent}% off`,
        detail: `${discount?.store || discount?.source}${price ? ` · ${price}` : ''}`,
        game,
      })
    }

    const releaseDate = game.release_date ? new Date(`${game.release_date}T12:00:00`) : null
    if (releaseDate && releaseDate >= now && releaseDate <= upcomingCutoff) {
      alerts.push({
        id: `${game.slug}:release:${game.release_date}`,
        kind: 'release',
        title: `${game.title} releases soon`,
        detail: releaseDate.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }),
        game,
      })
    }

    if (game.metrix_score >= preferences.minScore) {
      alerts.push({
        id: `${game.slug}:score:${Math.round(game.metrix_score)}`,
        kind: 'score',
        title: `${game.title} reached ${Math.round(game.metrix_score)}`,
        detail: `GameMetrix score is at or above your ${preferences.minScore} alert threshold.`,
        game,
      })
    }
  })

  const priority: Record<GameAlert['kind'], number> = { free: 0, deal: 1, release: 2, score: 3 }
  return alerts.sort((a, b) => priority[a.kind] - priority[b.kind] || b.game.metrix_score - a.game.metrix_score)
}

function AlertIcon({ kind }: { kind: GameAlert['kind'] }) {
  if (kind === 'deal') return <Percent size={17} aria-hidden="true" />
  if (kind === 'release') return <CalendarDays size={17} aria-hidden="true" />
  if (kind === 'score') return <Sparkles size={17} aria-hidden="true" />
  return <Bell size={17} aria-hidden="true" />
}

interface AlertsPanelContentProps {
  watchlistSlugs: string[]
  account: Account | null
  accountState: AccountState | null
  updatePreferences: (preferences: Partial<AccountPreferences>) => Promise<void>
}

function AlertsPanelContent({
  watchlistSlugs,
  account,
  accountState,
  updatePreferences,
}: AlertsPanelContentProps) {
  const [games, setGames] = useState<Game[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [readIds, setReadIds] = useState(() => (
    accountState ? new Set(accountState.read_alerts) : loadStringSet(READ_KEY)
  ))
  const [dismissedIds, setDismissedIds] = useState(() => (
    accountState ? new Set(accountState.dismissed_alerts) : loadStringSet(DISMISSED_KEY)
  ))
  const [preferences, setPreferences] = useState<AlertPreferences>(() => accountState ? {
    minDiscount: accountState.preferences.min_discount,
    minScore: accountState.preferences.min_score,
    upcomingDays: accountState.preferences.upcoming_days,
  } : loadPreferences())

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
    }, 500)
    return () => window.clearTimeout(timer)
  }, [account, accountState, preferences, updatePreferences])

  useEffect(() => {
    let cancelled = false
    const uniqueSlugs = Array.from(new Set(watchlistSlugs))
      .filter((slug) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug))
      .slice(0, 100)

    async function loadWatchlistGames() {
      if (!uniqueSlugs.length) {
        setGames([])
        setError(null)
        setIsLoading(false)
        return
      }
      setIsLoading(true)
      setError(null)
      const loaded: Game[] = []
      for (let index = 0; index < uniqueSlugs.length; index += 8) {
        const batch = await Promise.allSettled(
          uniqueSlugs.slice(index, index + 8).map((slug) => getGameBySlug(slug, false)),
        )
        loaded.push(...batch.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []))
        if (cancelled) return
      }
      if (!cancelled) {
        setGames(loaded)
        setError(loaded.length ? null : 'Wishlist alerts could not be loaded.')
        setIsLoading(false)
      }
    }

    void loadWatchlistGames()
    return () => { cancelled = true }
  }, [refreshKey, watchlistSlugs])

  const alerts = useMemo(
    () => buildAlerts(games, preferences).filter((alert) => !dismissedIds.has(alert.id)),
    [dismissedIds, games, preferences],
  )
  const unreadCount = alerts.filter((alert) => !readIds.has(alert.id)).length

  const persistSet = (key: string, values: Set<string>) => {
    localStorage.setItem(key, JSON.stringify(Array.from(values)))
  }

  const markAllRead = () => {
    const next = new Set(readIds)
    alerts.forEach((alert) => next.add(alert.id))
    setReadIds(next)
    persistSet(READ_KEY, next)
    if (account) {
      void setAccountAlertStates(
        alerts.filter((alert) => !readIds.has(alert.id)).map((alert) => alert.id),
        'read',
      ).catch(() => setError('Read status could not be synchronized.'))
    }
  }

  const dismiss = (id: string) => {
    const next = new Set(dismissedIds).add(id)
    setDismissedIds(next)
    persistSet(DISMISSED_KEY, next)
    if (account) void setAccountAlertState(id, 'dismissed').catch(() => setError('Dismissal could not be synchronized.'))
  }

  return (
    <div className="alerts-panel">
      <div className="alerts-toolbar">
        <div className="alerts-summary">
          <strong>{unreadCount} unread</strong>
          <span>{watchlistSlugs.length} wishlist games monitored</span>
        </div>
        <div className="alerts-actions">
          <button type="button" title="Refresh alerts" onClick={() => setRefreshKey((value) => value + 1)} disabled={isLoading}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button type="button" title="Mark all as read" onClick={markAllRead} disabled={!unreadCount}>
            <CheckCheck size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="alerts-preferences">
        <label>
          <span>Deal</span>
          <input type="number" min="1" max="90" value={preferences.minDiscount} onChange={(event) => setPreferences((current) => ({ ...current, minDiscount: boundedNumber(event.target.value, 1, 90, current.minDiscount) }))} />
          <small>%</small>
        </label>
        <label>
          <span>Score</span>
          <input type="number" min="1" max="100" value={preferences.minScore} onChange={(event) => setPreferences((current) => ({ ...current, minScore: boundedNumber(event.target.value, 1, 100, current.minScore) }))} />
        </label>
        <label>
          <span>Release</span>
          <input type="number" min="1" max="365" value={preferences.upcomingDays} onChange={(event) => setPreferences((current) => ({ ...current, upcomingDays: boundedNumber(event.target.value, 1, 365, current.upcomingDays) }))} />
          <small>days</small>
        </label>
      </div>

      {error ? <p className="status status-error">{error}</p> : null}
      {isLoading ? <p className="status">Loading alerts...</p> : null}
      {!isLoading && !alerts.length ? (
        <div className="alerts-empty">
          <Bell size={22} aria-hidden="true" />
          <p>{watchlistSlugs.length ? 'No wishlist games currently match your alert rules.' : 'Add games to your wishlist to start monitoring them.'}</p>
        </div>
      ) : null}

      <div className="alerts-list">
        {alerts.map((alert) => (
          <article className={`alert-item${readIds.has(alert.id) ? ' is-read' : ''}`} key={alert.id}>
            <span className={`alert-kind alert-kind-${alert.kind}`}><AlertIcon kind={alert.kind} /></span>
            <div>
              <strong>{alert.title}</strong>
              <p>{alert.detail}</p>
            </div>
            <div className="alert-item-actions">
              <Link to={`/game/${alert.game.slug}`} title={`Open ${alert.game.title}`} onClick={() => {
                const next = new Set(readIds).add(alert.id)
                setReadIds(next)
                persistSet(READ_KEY, next)
                if (account) void setAccountAlertState(alert.id, 'read').catch(() => undefined)
              }}>
                <ExternalLink size={15} aria-hidden="true" />
              </Link>
              <button type="button" title="Dismiss alert" onClick={() => dismiss(alert.id)}>
                <X size={15} aria-hidden="true" />
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

export function AlertsPanel({ watchlistSlugs }: { watchlistSlugs: string[] }) {
  const accountContext = useAccount()
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
