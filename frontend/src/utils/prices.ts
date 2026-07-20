import type { PriceSnapshot } from '../types/game'

const CURRENT_PRICE_MAX_AGE_MS = 24 * 60 * 60 * 1000

export function currentPriceSnapshots(prices: PriceSnapshot[]): PriceSnapshot[] {
  const cutoff = Date.now() - CURRENT_PRICE_MAX_AGE_MS
  return prices.filter((price) => {
    const fetchedAt = Date.parse(price.fetched_at)
    return Number.isFinite(fetchedAt) && fetchedAt >= cutoff
  })
}
