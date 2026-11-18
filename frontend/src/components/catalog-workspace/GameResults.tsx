import { PAGE_SIZE } from '../../catalog/config'
import { CatalogEmptyState } from '../CatalogEmptyState'
import { GameCard } from '../GameCard'
import type { WorkspaceProps } from './types'

const SKELETON_CARD_COUNT = PAGE_SIZE / 3

type GameResultsProps = { query: string; onClearSearch: () => void } & WorkspaceProps<
  | 'activePage'
  | 'collectionSets'
  | 'deferredCardCount'
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
  | 'onRetryError'
  | 'onRetryLoadMore'
  | 'onToggleCollection'
>

export function GameResults({
  activePage,
  collectionSets,
  deferredCardCount,
  error,
  isLoading,
  isLoadingMore,
  loadMoreError,
  loaderRef,
  pageTitle,
  query,
  viewMode,
  visibleGames,
  onBrowseCatalog,
  onClearSearch,
  onFilterDeveloper,
  onFilterGenre,
  onFilterPublisher,
  onOpenDetail,
  onOpenTrailer,
  onRetryError,
  onRetryLoadMore,
  onToggleCollection,
}: GameResultsProps) {
  const listClass = `game-list game-list-${viewMode}`
  // While a new page loads the old list stays (dimmed) so the page does not
  // jump to empty and back on every keystroke.
  const refreshing = isLoading && visibleGames.length > 0
  const skeletonsVisible = isLoading && visibleGames.length === 0

  return (
    <>
      {error ? (
        <div className="status status-error load-more-error" role="alert">
          <span>{error}</span>
          {onRetryError ? (
            <button type="button" className="ghost-button" onClick={onRetryError}>
              Try again
            </button>
          ) : null}
        </div>
      ) : null}
      {skeletonsVisible ? (
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
          query={query}
          onBrowseCatalog={onBrowseCatalog}
          onClearSearch={onClearSearch}
        />
      ) : null}
      <div className={`${listClass}${refreshing ? ' is-refreshing' : ''}`} aria-busy={refreshing}>
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
        {Array.from({ length: deferredCardCount }, (_, index) => (
          <div key={`deferred-${index}`} className="skeleton-card skeleton-card-static" aria-hidden="true" />
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
