/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from 'react'
import {
  getGameBySlug,
  getGameTrailer,
  getSimilarGames,
} from '../../services/games'
import type { Game } from '../../types/game'
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
    let active = true
    if (initialGame?.slug === slug) {
      setGame(initialGame)
      setError(null)
      return
    }

    setGame(null)
    setError(null)
    void getGameBySlug(slug)
      .then((loaded) => {
        if (active) setGame(loaded)
      })
      .catch(() => {
        if (active) setError('Game not found.')
      })
    return () => {
      active = false
    }
  }, [initialGame, slug])

  return { error, game }
}

export function useSimilarGames(
  slug: string | undefined,
  initialGame: Game | undefined,
) {
  const [games, setGames] = useState<Game[]>([])
  const [loading, setLoading] = useState(false)
  const initialGameSlug = initialGame?.slug

  useEffect(() => {
    if (!slug) return
    let active = true
    setLoading(true)
    if (initialGameSlug !== slug) setGames([])
    void getSimilarGames(slug, SIMILAR_DISPLAY_LIMIT)
      .then((response) => {
        if (active) setGames(response.games)
      })
      .catch(() => {
        if (active) setGames([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [initialGameSlug, slug])

  return { games, loading }
}

export function useGameTrailer(game: Game | null) {
  const [open, setOpen] = useState(false)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const openTrailer = async () => {
    if (!game) return
    setOpen(true)
    setLoading(true)
    try {
      setVideoId((await getGameTrailer(game.slug)).video_id)
    } catch {
      setVideoId(null)
    } finally {
      setLoading(false)
    }
  }

  const closeTrailer = () => {
    setOpen(false)
    setVideoId(null)
  }

  return { closeTrailer, loading, open, openTrailer, videoId }
}
