export const RATING_SOURCE_NAMES = {
  metacritic: 'Metacritic',
  openCritic: 'OpenCritic',
  steam: 'Steam',
  igdb: 'IGDB',
  rawg: 'RAWG',
  steamSpy: 'SteamSpy',
  cheapShark: 'CheapShark',
  freeToGame: 'FreeToGame',
} as const

export const CARD_PRIMARY_SOURCE_ORDER = [
  RATING_SOURCE_NAMES.metacritic,
  RATING_SOURCE_NAMES.openCritic,
  RATING_SOURCE_NAMES.igdb,
  RATING_SOURCE_NAMES.steam,
] as const

export const DETAIL_PRIMARY_SOURCE_ORDER = [
  RATING_SOURCE_NAMES.metacritic,
  RATING_SOURCE_NAMES.openCritic,
  RATING_SOURCE_NAMES.steam,
  RATING_SOURCE_NAMES.igdb,
] as const

export const DETAIL_EXTRA_SOURCE_ORDER = [
  RATING_SOURCE_NAMES.rawg,
  RATING_SOURCE_NAMES.steamSpy,
  RATING_SOURCE_NAMES.cheapShark,
  RATING_SOURCE_NAMES.freeToGame,
] as const

export const REVIEW_VOLUME_SOURCES = new Set<string>([
  ...DETAIL_PRIMARY_SOURCE_ORDER,
  RATING_SOURCE_NAMES.rawg,
])
