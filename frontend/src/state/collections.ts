import { createContext } from 'react'

export type CollectionKey = 'watchlist' | 'playing' | 'seen' | 'completed' | 'liked' | 'favorites'

export type Collections = Record<CollectionKey, string[]>

export interface CollectionsContextValue {
  collections: Collections
  toggleCollection: (collection: CollectionKey, slug: string) => void
}

export const emptyCollections: Collections = {
  watchlist: [],
  playing: [],
  seen: [],
  completed: [],
  liked: [],
  favorites: [],
}

export const CollectionsContext =
  createContext<CollectionsContextValue | null>(null)

export function loadCollections(): Collections {
  const stored = localStorage.getItem('gamemetrix.collections')
  if (!stored) {
    return emptyCollections
  }

  try {
    return { ...emptyCollections, ...JSON.parse(stored) }
  } catch {
    return emptyCollections
  }
}
