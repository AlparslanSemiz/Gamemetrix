import type { Game } from '../types/game'

const STEAM_APP_URL_RE = /steam\/apps\/(\d+)\//

export function steamAppIdFromGame(game: Game): string | null {
  return game.cover_url?.match(STEAM_APP_URL_RE)?.[1]
    ?? game.image_url?.match(STEAM_APP_URL_RE)?.[1]
    ?? null
}
