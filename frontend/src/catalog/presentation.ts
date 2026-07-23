import type { Collections } from '../state/collections'
import type { Game, GameFilters } from '../types/game'
import {
  CURRENT_YEAR,
  collectionLabels,
  collectionPageMap,
  utilityNavItems,
  type ActivePage,
  type MainPage,
} from './config'

export function visibleCatalogGames(
  activePage: ActivePage,
  collections: Collections,
  games: Game[],
): Game[] {
  if (activePage === 'suggestions') {
    const excluded = new Set([
      ...collections.seen,
      ...collections.completed,
      ...collections.favorites,
      ...collections.liked,
    ])
    return games
      .filter((game) => !excluded.has(game.slug))
      .sort((left, right) => right.metrix_score - left.metrix_score)
  }

  const collectionKey = collectionPageMap[activePage as MainPage]
  if (!collectionKey) return games
  const allowed = new Set(collections[collectionKey])
  return games.filter((game) => allowed.has(game.slug))
}

export function catalogPageTitle(
  activePage: ActivePage,
  activePreset: string | null,
  filters: GameFilters,
): string {
  if (activePreset === 'best-of-year') {
    const year = filters.yearMin
    return year === CURRENT_YEAR ? `Best of ${year} · So Far` : `Best of ${year}`
  }
  if (activePage in collectionLabels) {
    return collectionLabels[activePage as keyof typeof collectionLabels]
  }
  if (activePage === 'catalog') return 'Catalog'
  if (activePage === 'suggestions') return 'Discover'
  return utilityNavItems.find((item) => item.id === activePage)?.label ?? 'GameMetrix'
}
