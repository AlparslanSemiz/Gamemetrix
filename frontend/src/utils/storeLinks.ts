import type { CatalogGame } from '../types/game'
import { steamAppIdFromGame } from './steam'

// Maps a PlatformIcons group key to the game's store page.
//
// Resolution order:
//   1. An exact store URL from the backend's price_snapshots payload
//      (ITAD/CheapShark give us the game's real store page, not a search).
//   2. A direct Steam app page when the app id is derivable from CDN URLs.
//   3. A store search URL built from the title — always available, never 404s.
//
// Returns null for platform groups with no linkable storefront (e.g. iOS has
// no stable web search URL) so the icon renders as a plain badge.

const SNAPSHOT_STORE_TO_GROUP: Record<string, string> = {
  steam: 'steam',
  gog: 'gog',
  'gog.com': 'gog',
  epic: 'epic',
  'epic game store': 'epic',
  'epic games store': 'epic',
  playstation: 'ps',
  'playstation store': 'ps',
  xbox: 'xbox',
  'microsoft store': 'xbox',
  nintendo: 'switch',
  'nintendo eshop': 'switch',
}

function snapshotUrlForGroup(group: string, game: CatalogGame): string | null {
  for (const snapshot of game.price_snapshots ?? []) {
    if (!snapshot.url) continue
    const snapshotGroup = SNAPSHOT_STORE_TO_GROUP[snapshot.store.toLowerCase().trim()]
    if (snapshotGroup === group) return snapshot.url
  }
  return null
}

export function storeUrlForGroup(group: string, game: CatalogGame): string | null {
  const fromSnapshot = snapshotUrlForGroup(group, game)
  if (fromSnapshot) return fromSnapshot

  const q = encodeURIComponent(game.title)
  const steamAppId = steamAppIdFromGame(game)
  const steamAppUrl = steamAppId ? `https://store.steampowered.com/app/${steamAppId}/` : null

  switch (group) {
    case 'steam':
    case 'pc':
      return steamAppUrl ?? `https://store.steampowered.com/search/?term=${q}`
    case 'macos':
      return steamAppUrl ?? `https://store.steampowered.com/search/?term=${q}&os=mac`
    case 'linux':
      return steamAppUrl ?? `https://store.steampowered.com/search/?term=${q}&os=linux`
    case 'ps':
      return `https://store.playstation.com/search/${q}`
    case 'xbox':
      return `https://www.xbox.com/search?q=${q}`
    case 'switch':
    case 'wii':
    case 'wiiu':
      return `https://www.nintendo.com/us/search/?q=${q}`
    case 'gog':
      return `https://www.gog.com/en/games?query=${q}`
    case 'epic':
      return `https://store.epicgames.com/browse?q=${q}&sortBy=relevancy`
    case 'android':
      return `https://play.google.com/store/search?q=${q}&c=apps`
    default:
      return null
  }
}
