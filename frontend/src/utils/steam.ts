import type { Game } from '../types/game'

// Fallback only: recovering the id from a CDN URL fails whenever the cover came
// from IGDB/GOG/PlayStation rather than Steam. game.steam_app_id is authoritative.
const STEAM_APP_URL_RE = /steam\/apps\/(\d+)\//

export function steamAppIdFromGame(game: Game): string | null {
  if (game.steam_app_id) return String(game.steam_app_id)
  return game.cover_url?.match(STEAM_APP_URL_RE)?.[1]
    ?? game.image_url?.match(STEAM_APP_URL_RE)?.[1]
    ?? null
}
