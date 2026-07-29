import type { CatalogGame } from '../types/game'

export function latestContentUpdate(games: CatalogGame[]): string {
  const timestamps = games.flatMap((game) => [
    game.seo_updated_at,
    game.ratings_refreshed_at,
    game.metadata_refreshed_at,
    game.prices_refreshed_at,
  ]).filter((value): value is string => Boolean(value))
  const latest = Math.max(...timestamps.map((value) => Date.parse(value)).filter(Number.isFinite))
  return Number.isFinite(latest) ? new Date(latest).toISOString() : new Date().toISOString()
}
