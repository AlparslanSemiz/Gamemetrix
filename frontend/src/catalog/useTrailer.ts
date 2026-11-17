import { useCallback, useEffect, useRef, useState } from 'react'
import { getGameTrailer } from '../services/games'
import type { CatalogGame } from '../types/game'

export function useTrailer() {
  const [game, setGame] = useState<CatalogGame | null>(null)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => controllerRef.current?.abort(), [])

  const open = useCallback(async (selectedGame: CatalogGame) => {
    // A slower answer for an earlier game must never replace the one the viewer
    // asked for last, and a closed modal must stay closed.
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setGame(selectedGame)
    setVideoId(null)
    setIsLoading(true)
    try {
      const trailer = await getGameTrailer(selectedGame.slug, controller.signal)
      if (!controller.signal.aborted) setVideoId(trailer.video_id)
    } catch {
      if (!controller.signal.aborted) setVideoId(null)
    } finally {
      if (!controller.signal.aborted) setIsLoading(false)
    }
  }, [])

  const close = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setGame(null)
    setVideoId(null)
    setIsLoading(false)
  }, [])

  return { close, game, isLoading, open, videoId }
}
