import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  CollectionsContext,
  loadCollections,
  type Collections,
  type CollectionsContextValue,
} from './collections'

export function CollectionsProvider({ children }: { children: ReactNode }) {
  const [collections, setCollections] = useState<Collections>(loadCollections)

  useEffect(() => {
    localStorage.setItem('gamemetrix.collections', JSON.stringify(collections))
  }, [collections])

  const value = useMemo<CollectionsContextValue>(
    () => ({
      collections,
      toggleCollection: (collection, slug) => {
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
      },
    }),
    [collections],
  )

  return (
    <CollectionsContext.Provider value={value}>
      {children}
    </CollectionsContext.Provider>
  )
}
