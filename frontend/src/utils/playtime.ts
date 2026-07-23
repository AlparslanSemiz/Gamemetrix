import type { Game } from '../types/game'

// Genres whose games have no fixed completion time. Kept in sync with the
// backend heuristic in services/endless.py.
const ENDLESS_GENRES = new Set([
  'Roguelike', 'Roguelite', 'Rogue-like', 'Rogue-lite', 'Roguelikes', 'Rouge-like',
  'roguelike', 'roguelite', 'rogue-like',
  'Massively Multiplayer', 'MMO', 'MMORPG', 'Battle Royale',
  'Sports', 'Racing', 'Sandbox', 'Party', 'Pinball',
])

// The backend `is_endless` flag is authoritative once set; fall back to the
// genre heuristic for games it has not classified yet.
export function isEndlessGame(game: Pick<Game, 'is_endless' | 'genres'>): boolean {
  if (game.is_endless) return true
  return (game.genres ?? []).some((g) => ENDLESS_GENRES.has(g))
}

export function formatPlaytimeHours(minutes: number): string {
  return `${Math.max(1, Math.round(minutes / 60))}h`
}
