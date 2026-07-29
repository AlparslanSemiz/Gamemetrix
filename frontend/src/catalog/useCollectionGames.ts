import { useEffect, useMemo, useRef, useState } from 'react'

import { getCatalogGamesBySlugs } from '../services/games'
import type { Collections } from '../state/collections'
import type { CatalogGame } from '../types/game'
import { collectionPageMap, type ActivePage, type MainPage } from './config'

const COLLECTION_BATCH_SIZE = 100
const SIGNATURE_SEPARATOR = '\u0000'

interface LoadError {
  collectionSignature: string
  message: string
}

export function useCollectionGames(
  activePage: ActivePage,
  collections: Collections,
  catalogGames: CatalogGame[],
) {
  const collectionKey = collectionPageMap[activePage as MainPage]
  const [resolvedGames, setResolvedGames] = useState<Record<string, CatalogGame | null>>({})
  const [loadError, setLoadError] = useState<LoadError | null>(null)
  const lastRefreshSignatureRef = useRef<string | null>(null)

  const catalogBySlug = useMemo(
    () => new Map(catalogGames.map((game) => [game.slug, game])),
    [catalogGames],
  )
  const slugs = collectionKey ? collections[collectionKey] : []
  const collectionSignature = slugs.join(SIGNATURE_SEPARATOR)
  const missingSignature = slugs
    .filter((slug) => !catalogBySlug.has(slug) && !Object.hasOwn(resolvedGames, slug))
    .join(SIGNATURE_SEPARATOR)

  useEffect(() => {
    if (
      !collectionKey
      || !collectionSignature
      || lastRefreshSignatureRef.current === collectionSignature
    ) return
    lastRefreshSignatureRef.current = collectionSignature

    let active = true
    const requestedSlugs = collectionSignature.split(SIGNATURE_SEPARATOR)

    void (async () => {
      try {
        const loaded: CatalogGame[] = []
        for (let index = 0; index < requestedSlugs.length; index += COLLECTION_BATCH_SIZE) {
          loaded.push(...await getCatalogGamesBySlugs(
            requestedSlugs.slice(index, index + COLLECTION_BATCH_SIZE),
          ))
        }
        if (!active) return

        const next: Record<string, CatalogGame | null> = Object.fromEntries(
          requestedSlugs.map((slug) => [slug, null]),
        )
        for (const game of loaded) next[game.slug] = game
        setResolvedGames((current) => ({ ...current, ...next }))
      } catch {
        if (active) {
          lastRefreshSignatureRef.current = null
          setLoadError({
            collectionSignature,
            message: 'Saved games could not be loaded. Check your connection and try again.',
          })
        }
      }
    })()

    return () => {
      active = false
    }
  }, [collectionKey, collectionSignature])

  const games = slugs.flatMap((slug) => {
    const game = catalogBySlug.get(slug) ?? resolvedGames[slug]
    return game ? [game] : []
  })

  return {
    collectionKey,
    error: loadError?.collectionSignature === collectionSignature
      ? loadError.message
      : null,
    games,
    isLoading: Boolean(
      collectionKey
      && missingSignature
      && loadError?.collectionSignature !== collectionSignature,
    ),
  }
}
