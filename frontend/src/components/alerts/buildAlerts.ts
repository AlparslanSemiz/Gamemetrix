import type { CatalogGame, PriceSnapshot } from '../../types/game'
import { ACTIONABLE_PRICE_MAX_AGE_MS, currentPriceSnapshots } from '../../utils/prices'
import type { AlertKind, AlertPreferences, GameAlert } from './types'

const MS_PER_DAY = 24 * 60 * 60 * 1000
const KIND_PRIORITY: Record<AlertKind, number> = { free: 0, deal: 1, release: 2, score: 3 }

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

function priceAlert(game: CatalogGame, preferences: AlertPreferences): GameAlert | null {
  const prices = currentPriceSnapshots(game.price_snapshots ?? [], ACTIONABLE_PRICE_MAX_AGE_MS)
  const freePrice = prices.find((price) => price.is_free || price.sale_price === 0)
  if (freePrice) {
    return {
      id: `${game.slug}:free:${freePrice.source}:${freePrice.store}`,
      kind: 'free',
      title: `${game.title} is free`,
      detail: `${freePrice.store || freePrice.source} is currently tracking this game at no cost.`,
      game,
    }
  }

  const discount = bestDiscount(prices)
  if ((discount?.discount_percent ?? 0) < preferences.minDiscount) return null

  const price = formatMoney(discount?.sale_price, discount?.currency ?? 'USD')
  return {
    id: `${game.slug}:deal:${discount?.source}:${discount?.discount_percent}:${discount?.sale_price}`,
    kind: 'deal',
    title: `${game.title} is ${discount?.discount_percent}% off`,
    detail: `${discount?.store || discount?.source}${price ? ` · ${price}` : ''}`,
    game,
  }
}

function releaseAlert(game: CatalogGame, now: Date, cutoff: Date): GameAlert | null {
  if (!game.release_date) return null
  const releaseDate = new Date(`${game.release_date}T12:00:00`)
  if (releaseDate < now || releaseDate > cutoff) return null
  return {
    id: `${game.slug}:release:${game.release_date}`,
    kind: 'release',
    title: `${game.title} releases soon`,
    detail: releaseDate.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }),
    game,
  }
}

function scoreAlert(game: CatalogGame, preferences: AlertPreferences): GameAlert | null {
  if (game.metrix_score < preferences.minScore) return null
  const score = Math.round(game.metrix_score)
  return {
    id: `${game.slug}:score:${score}`,
    kind: 'score',
    title: `${game.title} reached ${score}`,
    detail: `GameMetrix score is at or above your ${preferences.minScore} alert threshold.`,
    game,
  }
}

export function buildAlerts(games: CatalogGame[], preferences: AlertPreferences): GameAlert[] {
  const now = new Date()
  const cutoff = new Date(now.getTime() + preferences.upcomingDays * MS_PER_DAY)

  const alerts = games.flatMap((game) =>
    [
      priceAlert(game, preferences),
      releaseAlert(game, now, cutoff),
      scoreAlert(game, preferences),
    ].filter((alert): alert is GameAlert => alert !== null),
  )

  return alerts.sort(
    (a, b) =>
      KIND_PRIORITY[a.kind] - KIND_PRIORITY[b.kind]
      || b.game.metrix_score - a.game.metrix_score,
  )
}
