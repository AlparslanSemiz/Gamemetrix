/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useRef, useState } from 'react'
import {
  getGameBySlug,
  getGameTrailer,
  getSimilarGames,
} from '../../services/games'
import type { Game, SeriesGameItem } from '../../types/game'
import { SIMILAR_DISPLAY_LIMIT } from './SimilarGamesSection'

export function useGameDetailGame(
  slug: string | undefined,
  initialGame: Game | undefined,
) {
  const [game, setGame] = useState<Game | null>(initialGame ?? null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!slug) return
    const previousBehavior = document.documentElement.style.scrollBehavior
    document.documentElement.style.scrollBehavior = 'auto'
    window.scrollTo(0, 0)
    document.documentElement.style.scrollBehavior = previousBehavior
  }, [slug])

  useEffect(() => {
    if (!slug) return
    const controller = new AbortController()
    if (initialGame?.slug === slug) {
      setGame(initialGame)
      setError(null)
      return
    }

    setGame(null)
    setError(null)
    void getGameBySlug(slug, false, controller.signal)
      .then((loaded) => {
        if (!controller.signal.aborted) setGame(loaded)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('Game not found.')
      })
    return () => {
      controller.abort()
    }
  }, [initialGame, slug])

  return { error, game }
}

export function useSimilarGames(
  slug: string | undefined,
  initialGame: Game | undefined,
  enabled: boolean,
) {
  const [games, setGames] = useState<SeriesGameItem[]>([])
  const [loading, setLoading] = useState(false)
  const initialGameSlug = initialGame?.slug

  useEffect(() => {
    if (!slug || !enabled) return
    const controller = new AbortController()
    setLoading(true)
    if (initialGameSlug !== slug) setGames([])
    void getSimilarGames(slug, SIMILAR_DISPLAY_LIMIT, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setGames(response.games)
      })
      .catch(() => {
        if (!controller.signal.aborted) setGames([])
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
    }
  }, [enabled, initialGameSlug, slug])

  return { games, loading }
}

export function useGameTrailer(game: Game | null) {
  const [open, setOpen] = useState(false)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const requestControllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => requestControllerRef.current?.abort(), [])

  const openTrailer = async () => {
    if (!game) return
    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller
    setOpen(true)
    setLoading(true)
    try {
      setVideoId((await getGameTrailer(game.slug, controller.signal)).video_id)
    } catch {
      if (!controller.signal.aborted) setVideoId(null)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  const closeTrailer = () => {
    requestControllerRef.current?.abort()
    requestControllerRef.current = null
    setOpen(false)
    setVideoId(null)
  }

  return { closeTrailer, loading, open, openTrailer, videoId }
}
