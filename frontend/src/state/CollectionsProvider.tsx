/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  CollectionsContext,
  emptyCollections,
  loadCollections,
  type CollectionKey,
  type Collections,
  type CollectionsContextValue,
} from './collections'

export function CollectionsProvider({ children }: { children: ReactNode }) {
  const [collections, setCollections] = useState<Collections>({ ...emptyCollections })
  const [isHydrated, setIsHydrated] = useState(false)

  useEffect(() => {
    setCollections(loadCollections())
    setIsHydrated(true)
  }, [])

  useEffect(() => {
    if (isHydrated && typeof window !== 'undefined') {
      localStorage.setItem('gamemetrix.collections', JSON.stringify(collections))
    }
  }, [collections, isHydrated])

  const replaceCollections = useCallback((next: Collections) => {
    setCollections(next)
  }, [])

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
    () => ({ collections, replaceCollections, toggleCollection }),
    [collections, replaceCollections, toggleCollection],
  )

  return (
    <CollectionsContext.Provider value={value}>
      {children}
    </CollectionsContext.Provider>
  )
}
