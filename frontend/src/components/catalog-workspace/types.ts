import type { Dispatch, RefObject, SetStateAction } from 'react'

import type { ActivePage } from '../../catalog/config'
import type { CollectionKey, Collections } from '../../state/collections'
import type { CollectionSets } from '../../state/useCollectionActions'
import type { CatalogGame, Facets, GameFilters } from '../../types/game'
import type { ClearableFilterKey } from '../ActiveFilterChips'
import type { ViewMode } from '../CatalogToolbar'

export interface CatalogWorkspaceProps {
  activePage: ActivePage
  activePreset: string | null
  catalogTotal: number
  collections: Collections
  collectionSets: CollectionSets
  error: string | null
  facets: Facets
  filters: GameFilters
  filtersOpen: boolean
  games: CatalogGame[]
  isLoading: boolean
  isLoadingMore: boolean
  libraryTotal: number
  loadMoreError: string | null
  loaderRef: RefObject<HTMLDivElement | null>
  mastheadRef: RefObject<HTMLElement | null>
  mastheadVisible: boolean
  pageTitle: string
  pendingApply: number
  providerCount: number
  readyProviders: number
  viewMode: ViewMode
  visibleGames: CatalogGame[]
  onApplyFilters: () => void
  onBrowseCatalog: () => void
  onChangeFilters: Dispatch<SetStateAction<GameFilters>>
  onChangeFiltersOpen: Dispatch<SetStateAction<boolean>>
  onChangeViewMode: Dispatch<SetStateAction<ViewMode>>
  onClearDealMode: () => void
  onClearFilter: (key: ClearableFilterKey) => void
  onFilterDeveloper: (developer: string) => void
  onFilterGenre: (genre: string) => void
  onFilterPublisher: (publisher: string) => void
  onFocusSearch: () => void
  onOpenDetail: (game: CatalogGame) => void
  onOpenTrailer: (game: CatalogGame) => void
  onRetryLoadMore: () => void
  onToggleCollection: (collection: CollectionKey, slug: string) => void
}

export type WorkspaceProps<K extends keyof CatalogWorkspaceProps> = Pick<
  CatalogWorkspaceProps,
  K
>
