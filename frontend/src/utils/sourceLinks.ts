import type { Game } from '../types/game'
import { RATING_SOURCE_NAMES } from './ratingSources'
import { steamAppIdFromGame } from './steam'

export type SourceLinkContext = 'catalog-card' | 'game-detail'

export function sourceScoreUrl(
  source: string,
  game: Game,
  context: SourceLinkContext,
): string | null {
  const query = encodeURIComponent(game.title)
  const steamAppId = steamAppIdFromGame(game)

  switch (source) {
    case RATING_SOURCE_NAMES.metacritic:
      return `https://www.metacritic.com/search/${query}/`
    case RATING_SOURCE_NAMES.openCritic:
      return context === 'game-detail'
        ? `https://opencritic.com/game/search?criteria=${query}`
        : `https://opencritic.com/search?q=${query}`
    case RATING_SOURCE_NAMES.steam:
      if (steamAppId) return `https://store.steampowered.com/app/${steamAppId}/`
      return context === 'catalog-card'
        ? `https://store.steampowered.com/search/?term=${query}`
        : null
    case RATING_SOURCE_NAMES.igdb:
      return `https://www.igdb.com/search?type=1&q=${query}`
    case RATING_SOURCE_NAMES.rawg:
      return `https://rawg.io/search?query=${query}`
    case RATING_SOURCE_NAMES.steamSpy:
      return steamAppId ? `https://steamspy.com/app/${steamAppId}` : null
    default:
      return null
  }
}
