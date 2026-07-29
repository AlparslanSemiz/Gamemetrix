import type { CSSProperties, SyntheticEvent } from 'react'
import type { CollectionKey } from '../../state/collections'
import type { CatalogGame, ProtonTier, SourceScore } from '../../types/game'

export interface GameCardCollectionState {
  isFavorite: boolean
  isLiked: boolean
  isPlaying: boolean
  isSeen: boolean
  isCompleted: boolean
  isOnHold: boolean
  isDropped: boolean
  isWatchlisted: boolean
}

export interface GameCardHandlers {
  onOpenTrailer: (game: CatalogGame) => void
  onFilterDeveloper: (developer: string) => void
  onFilterGenre: (genre: string) => void
  onFilterPublisher: (publisher: string) => void
  onToggleCollection: (collection: CollectionKey, slug: string) => void
  onOpenDetail: (game: CatalogGame) => void
}

export interface GameCardProps extends GameCardCollectionState, GameCardHandlers {
  game: CatalogGame
  compact?: boolean
  priority?: boolean
}

export interface GameCardModel {
  cardStyle: CSSProperties
  coverSrc: string
  displayedSources: SourceScore[]
  applicableSourceCount: number
  confidenceLevel: string
  confidenceTitle: string
  hltbHref: string
  hltbMinutes: number
  isEndless: boolean
  isRankedLower: boolean
  playtimeLabel: string | null
  primarySourceCount: number
  protonTier: ProtonTier | null
  scoreProfile: string
}

export interface GameCardViewProps extends GameCardProps {
  model: GameCardModel
  onCoverError: (event: SyntheticEvent<HTMLImageElement>) => void
  onShare: () => void
}
