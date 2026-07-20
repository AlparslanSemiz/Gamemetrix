import { createContext } from 'react'

export type CollectionKey = 'watchlist' | 'playing' | 'seen' | 'completed' | 'liked' | 'favorites'

export type Collections = Record<CollectionKey, string[]>

export interface CollectionsContextValue {
  collections: Collections
  toggleCollection: (collection: CollectionKey, slug: string) => void
  replaceCollections: (collections: Collections) => void
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
  if (typeof window === 'undefined') {
    return { ...emptyCollections }
  }
  const stored = localStorage.getItem('gamemetrix.collections')
  if (!stored) {
    return emptyCollections
  }

  try {
    const parsed: unknown = JSON.parse(stored)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ...emptyCollections }
    }
    const source = parsed as Record<string, unknown>
    return Object.fromEntries(
      (Object.keys(emptyCollections) as CollectionKey[]).map((key) => {
        const values = source[key]
        const slugs = Array.isArray(values)
          ? Array.from(new Set(values.filter(
            (value): value is string => typeof value === 'string'
              && value.length <= 180
              && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value),
          ))).slice(0, 5000)
          : []
        return [key, slugs]
      }),
    ) as Collections
  } catch {
    return { ...emptyCollections }
  }
}
