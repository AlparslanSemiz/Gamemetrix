import { useCallback, useEffect, useMemo, useRef } from 'react'
import { trackProductEvent } from '../services/analytics'
import type { CollectionKey, Collections } from './collections'
import { useAccount } from './useAccount'
import { useCollections } from './useCollections'

const SYNC_ERROR_MESSAGE =
  'This collection change is saved locally, but account sync is temporarily unavailable.'

export type CollectionSets = Record<CollectionKey, Set<string>>

export interface CollectionActions {
  collections: Collections
  collectionSets: CollectionSets
  toggle: (collection: CollectionKey, slug: string) => void
}

// Single owner of "user toggled a collection": local state, account sync and the
// wishlist analytics event. Every surface that offers those buttons — catalog
// cards, game detail — goes through here so the three stay in step.
export function useCollectionActions(onSyncError?: (message: string) => void): CollectionActions {
  const { collections, toggleCollection } = useCollections()
  const { syncCollection } = useAccount()

  const collectionSets = useMemo<CollectionSets>(() => ({
    watchlist: new Set(collections.watchlist),
    playing: new Set(collections.playing),
    seen: new Set(collections.seen),
    completed: new Set(collections.completed),
    liked: new Set(collections.liked),
    favorites: new Set(collections.favorites),
  }), [collections])

  // Read the current sets through a ref so `toggle` never has to list
  // `collectionSets` as a dependency. Otherwise its identity would change on
  // every collection change, flipping the onToggleCollection prop on every
  // GameCard and re-rendering the whole catalog on a single button press.
  const collectionSetsRef = useRef(collectionSets)
  useEffect(() => {
    collectionSetsRef.current = collectionSets
  }, [collectionSets])

  const toggle = useCallback((collection: CollectionKey, slug: string) => {
    const enabled = !collectionSetsRef.current[collection].has(slug)
    toggleCollection(collection, slug)
    void syncCollection(collection, slug, enabled).catch(() => {
      onSyncError?.(SYNC_ERROR_MESSAGE)
    })
    if (collection === 'watchlist' && enabled) {
      trackProductEvent('wishlist_add', { game_slug: slug })
    }
  }, [onSyncError, syncCollection, toggleCollection])

  return { collections, collectionSets, toggle }
}
