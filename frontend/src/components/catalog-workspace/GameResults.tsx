import { PAGE_SIZE } from '../../catalog/config'
import { CatalogEmptyState } from '../CatalogEmptyState'
import { GameCard } from '../GameCard'
import type { WorkspaceProps } from './types'

const SKELETON_CARD_COUNT = PAGE_SIZE / 3

type GameResultsProps = WorkspaceProps<
  | 'activePage'
  | 'collectionSets'
  | 'error'
  | 'isLoading'
  | 'isLoadingMore'
  | 'loadMoreError'
  | 'loaderRef'
  | 'pageTitle'
  | 'viewMode'
  | 'visibleGames'
  | 'onBrowseCatalog'
  | 'onFilterDeveloper'
  | 'onFilterGenre'
  | 'onFilterPublisher'
  | 'onOpenDetail'
  | 'onOpenTrailer'
  | 'onRetryLoadMore'
  | 'onToggleCollection'
>

export function GameResults({
  activePage,
  collectionSets,
  error,
  isLoading,
  isLoadingMore,
  loadMoreError,
  loaderRef,
  pageTitle,
  viewMode,
  visibleGames,
  onBrowseCatalog,
  onFilterDeveloper,
  onFilterGenre,
  onFilterPublisher,
  onOpenDetail,
  onOpenTrailer,
  onRetryLoadMore,
  onToggleCollection,
}: GameResultsProps) {
  const listClass = `game-list game-list-${viewMode}`

  return (
    <>
      {error ? <p className="status status-error">{error}</p> : null}
      {isLoading ? (
        <div className={listClass} aria-hidden="true">
          {Array.from({ length: SKELETON_CARD_COUNT }, (_, index) => (
            <div key={index} className="skeleton-card" />
          ))}
        </div>
      ) : null}
      {!isLoading && visibleGames.length === 0 ? (
        <CatalogEmptyState
          activePage={activePage}
          pageTitle={pageTitle}
          onBrowseCatalog={onBrowseCatalog}
        />
      ) : null}
      <div className={listClass}>
        {visibleGames.map((game, index) => (
          <GameCard
            key={`${game.id}-${game.slug}`}
            game={game}
            compact={viewMode === 'grid'}
            priority={index === 0}
            isFavorite={collectionSets.favorites.has(game.slug)}
            isLiked={collectionSets.liked.has(game.slug)}
            isPlaying={collectionSets.playing.has(game.slug)}
            isSeen={collectionSets.seen.has(game.slug)}
            isCompleted={collectionSets.completed.has(game.slug)}
            isOnHold={collectionSets.on_hold.has(game.slug)}
            isDropped={collectionSets.dropped.has(game.slug)}
            isWatchlisted={collectionSets.watchlist.has(game.slug)}
            onOpenDetail={onOpenDetail}
            onOpenTrailer={onOpenTrailer}
            onFilterDeveloper={onFilterDeveloper}
            onFilterGenre={onFilterGenre}
            onFilterPublisher={onFilterPublisher}
            onToggleCollection={onToggleCollection}
          />
        ))}
      </div>
      <div ref={loaderRef} className="scroll-sentinel" aria-live="polite">
        {isLoadingMore ? <p className="status">Loading more…</p> : null}
        {!isLoadingMore && loadMoreError ? (
          <div className="status status-error load-more-error">
            <span>{loadMoreError}</span>
            <button
              type="button"
              className="ghost-button"
              aria-label="Retry loading games"
              onClick={onRetryLoadMore}
            >
              Retry
            </button>
          </div>
        ) : null}
      </div>
    </>
  )
}
