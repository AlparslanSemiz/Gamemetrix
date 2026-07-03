import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  CollectionsContext,
  loadCollections,
  type CollectionKey,
  type Collections,
  type CollectionsContextValue,
} from './collections'

export function CollectionsProvider({ children }: { children: ReactNode }) {
  const [collections, setCollections] = useState<Collections>(loadCollections)

  useEffect(() => {
    localStorage.setItem('gamemetrix.collections', JSON.stringify(collections))
  }, [collections])

  const toggleCollection = useCallback((collection: CollectionKey, slug: string) => {
    setCollections((current) => {
      const values = new Set(current[collection])
      if (values.has(slug)) {
        values.delete(slug)
      } else {
        values.add(slug)
      }

      return {
        ...current,
        [collection]: Array.from(values),
      }
    })
  }, [])

  const value = useMemo<CollectionsContextValue>(
    () => ({ collections, toggleCollection }),
    [collections, toggleCollection],
  )

  return (
    <CollectionsContext.Provider value={value}>
      {children}
    </CollectionsContext.Provider>
  )
}
