import type { CatalogGame, PriceSnapshot, ProtonTier } from '../types/game'
import { ACTIONABLE_PRICE_MAX_AGE_MS, currentPriceSnapshots } from './prices'
import { isProtonTier } from './proton'
import { latestContentUpdate } from './seo'
import { safeExternalUrl } from './url'

/** The four primary score slots a ranking row shows, in display order. */
export const CURATED_PRIMARY_SOURCES = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB'] as const

export interface CuratedCardPrice {
  /** Already formatted ("Free", "$29.99"). */
  label: string
  discountPercent: number
  /** Safe outbound store link, when the snapshot has one. */
  url: string | null
  store: string
}

/**
 * Exactly what one ranking row renders. The loader projects the backend's
 * catalog payload down to this shape before it is serialized into the HTML:
 * a full `CatalogGame` (price history, per-source detail text, summaries,
 * freshness stamps) made 100-row pages ~5x heavier than the markup they feed.
 */
export interface CuratedGameCard {
  slug: string
  title: string
  /** Original cover URL (or null); the page picks the sized variant. */
  cover: string | null
  release_year: number
  developer: string | null
  /** Rounded Metrix score. */
  score: number
  /** Rounded live score per `CURATED_PRIMARY_SOURCES` slot, null when missing. */
  sourceScores: Array<number | null>
  proton_tier: ProtonTier | null
  /** HLTB (or catalog) playtime in whole hours, 0 when unknown. */
  playtimeHours: number
  price: CuratedCardPrice | null
}

function bestPrice(prices: PriceSnapshot[], now: number): PriceSnapshot | undefined {
  return currentPriceSnapshots(prices, ACTIONABLE_PRICE_MAX_AGE_MS, now)
    .filter((price) => price.is_free || price.sale_price != null || price.list_price != null)
    .sort((left, right) => Number(left.sale_price ?? left.list_price ?? Infinity) - Number(right.sale_price ?? right.list_price ?? Infinity))[0]
}

function priceText(price: PriceSnapshot): string | null {
  if (price.is_free || price.sale_price === 0) return 'Free'
  const amount = price.sale_price ?? price.list_price
  if (amount == null) return null
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency: price.currency }).format(amount) }
  catch { return `${amount.toFixed(2)} ${price.currency}` }
}

function cardPrice(prices: PriceSnapshot[], now: number): CuratedCardPrice | null {
  const price = bestPrice(prices, now)
  if (!price) return null
  const label = priceText(price)
  if (!label) return null
  return {
    label,
    discountPercent: price.discount_percent ?? 0,
    url: safeExternalUrl(price.url),
    store: price.store,
  }
}

/** `now` is the loader's clock, so price freshness is decided once, on the server. */
export function toCuratedCard(game: CatalogGame, now: number): CuratedGameCard {
  const scores = new Map(game.source_scores.map((score) => [score.source, score]))
  const playtime = game.hltb_main_story_minutes || game.hltb_all_styles_minutes || game.playtime_minutes
  return {
    slug: game.slug,
    title: game.title,
    cover: game.cover_url || game.image_url || null,
    release_year: game.release_year,
    developer: game.developer || null,
    score: Math.round(game.metrix_score),
    sourceScores: CURATED_PRIMARY_SOURCES.map((source) => {
      const score = scores.get(source)
      return score?.status === 'live' && score.score > 0 ? Math.round(score.score) : null
    }),
    proton_tier: game.proton_tier && isProtonTier(game.proton_tier) ? game.proton_tier : null,
    playtimeHours: playtime > 0 ? Math.max(1, Math.round(playtime / 60)) : 0,
    price: cardPrice(game.price_snapshots ?? [], now),
  }
}

/**
 * Loader helper: freshness stamp from the full rows, then the row projection.
 * Everything else the page needs (title, canonical, genres) is added by the route.
 */
export function curatedListPayload(
  result: { games: CatalogGame[]; total: number },
  now: number,
): { games: CuratedGameCard[]; total: number; updatedAt: string; renderedAt: number } {
  return {
    games: result.games.map((game) => toCuratedCard(game, now)),
    total: result.total,
    updatedAt: latestContentUpdate(result.games),
    renderedAt: now,
  }
}
