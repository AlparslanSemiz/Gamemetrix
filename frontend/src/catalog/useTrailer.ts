import { useCallback, useState } from 'react'
import { getGameTrailer } from '../services/games'
import type { Game } from '../types/game'

export function useTrailer() {
  const [game, setGame] = useState<Game | null>(null)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const open = useCallback(async (selectedGame: Game) => {
    setGame(selectedGame)
    setVideoId(null)
    setIsLoading(true)
    try {
      const trailer = await getGameTrailer(selectedGame.slug)
      setVideoId(trailer.video_id)
    } catch {
      setVideoId(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const close = useCallback(() => {
    setGame(null)
    setVideoId(null)
  }, [])

  return { close, game, isLoading, open, videoId }
}
