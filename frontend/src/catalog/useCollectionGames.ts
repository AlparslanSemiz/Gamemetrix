import { useEffect, useMemo, useState } from 'react'

import { getGamesBySlugs } from '../services/games'
import type { Collections } from '../state/collections'
import type { Game } from '../types/game'
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
  catalogGames: Game[],
) {
  const collectionKey = collectionPageMap[activePage as MainPage]
  const [resolvedGames, setResolvedGames] = useState<Record<string, Game | null>>({})
  const [loadError, setLoadError] = useState<LoadError | null>(null)

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
    if (!collectionKey || !missingSignature) return

    let active = true
    const missing = missingSignature.split(SIGNATURE_SEPARATOR)

    void (async () => {
      try {
        const loaded: Game[] = []
        for (let index = 0; index < missing.length; index += COLLECTION_BATCH_SIZE) {
          loaded.push(...await getGamesBySlugs(
            missing.slice(index, index + COLLECTION_BATCH_SIZE),
          ))
        }
        if (!active) return

        const next: Record<string, Game | null> = Object.fromEntries(
          missing.map((slug) => [slug, null]),
        )
        for (const game of loaded) next[game.slug] = game
        setResolvedGames((current) => ({ ...current, ...next }))
      } catch {
        if (active) {
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
  }, [collectionKey, collectionSignature, missingSignature])

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
