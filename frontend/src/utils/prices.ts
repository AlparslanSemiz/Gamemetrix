import type { PriceSnapshot } from '../types/game'

// The backfill job runs daily and only reaches part of the catalog, so a single
// 24h window silently deleted the whole "Where to buy" panel whenever a run
// slipped. The panel now tolerates an older price because it shows how old it is.
// Everything that asserts a price is current — structured-data offers, "is free"
// and "% off" alerts, bare list prices — stays on the tight window.
export const PANEL_PRICE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
export const ACTIONABLE_PRICE_MAX_AGE_MS = 48 * 60 * 60 * 1000

export function currentPriceSnapshots(prices: PriceSnapshot[], maxAgeMs: number): PriceSnapshot[] {
  const cutoff = Date.now() - maxAgeMs
  return prices.filter((price) => {
    const fetchedAt = Date.parse(price.fetched_at)
    return Number.isFinite(fetchedAt) && fetchedAt >= cutoff
  })
}

export function newestFetchedAt(prices: PriceSnapshot[]): number | null {
  const timestamps = prices
    .map((price) => Date.parse(price.fetched_at))
    .filter((value) => Number.isFinite(value))
  return timestamps.length > 0 ? Math.max(...timestamps) : null
}
