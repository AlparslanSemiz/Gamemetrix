import {
  Bell,
  Bookmark,
  CirclePause,
  CircleX,
  Compass,
  Gamepad2,
  Gift,
  Heart,
  History,
  Home,
  Info,
  Search,
  Settings,
  Star,
  Tag,
  Trophy,
} from 'lucide-react'
import type { CollectionKey } from '../state/collections'
import type { GameFilters, GameSort } from '../types/game'

export type MainPage =
  | 'catalog' | 'watchlist' | 'playing' | 'seen' | 'completed' | 'on_hold' | 'dropped'
  | 'liked' | 'favorites' | 'suggestions'
export type UtilityPage = 'alerts' | 'settings' | 'about'
export type ActivePage = MainPage | UtilityPage

export type NavIcon = typeof Search

export interface NavItem<Id extends string> {
  id: Id
  label: string
  icon: NavIcon
}

export interface CuratedPreset {
  id: string
  label: string
  icon: NavIcon
  filters: Partial<GameFilters>
}

export interface SidebarGroup {
  label: string
  items: CuratedPreset[]
}

export const CURRENT_YEAR = new Date().getFullYear()
export const PAGE_SIZE = 24
export const EARLIEST_YEAR = 1970

export const ROUTABLE_MAIN_PAGES = new Set<MainPage>([
  'watchlist', 'playing', 'seen', 'completed', 'on_hold', 'dropped',
  'liked', 'favorites', 'suggestions',
])

export const DEFAULT_FILTERS: GameFilters = {
  q: '',
  genre: '',
  platform: '',
  developer: '',
  publisher: '',
  yearMin: EARLIEST_YEAR,
  yearMax: CURRENT_YEAR,
  minScore: 0,
  maxScore: 100,
  minRatings: 0,
  maxRatings: 0,
  minLiveSources: 0,
  requireCritic: false,
  hasAward: false,
  dealMode: 'all',
  playerMode: '',
  playtimeMinHours: null,
  playtimeMaxHours: null,
  sort: 'rank_score',
  direction: 'desc',
}

export const SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    label: 'Deals',
    items: [
      {
        id: 'best-deals',
        label: 'Best Deals',
        icon: Tag,
        filters: { dealMode: 'best', minScore: 75, minLiveSources: 1, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'free-games',
        label: 'Free Games',
        icon: Gift,
        filters: { dealMode: 'free', sort: 'rank_score', direction: 'desc' },
      },
    ],
  },
]

export function findPreset(id: string): CuratedPreset | undefined {
  for (const group of SIDEBAR_GROUPS) {
    const found = group.items.find((preset) => preset.id === id)
    if (found) return found
  }
  return undefined
}

const BEST_OF_YEAR_FIRST_YEAR = 2020

export const BEST_OF_YEAR_RANGE = Array.from(
  { length: CURRENT_YEAR - BEST_OF_YEAR_FIRST_YEAR + 1 },
  (_, i) => BEST_OF_YEAR_FIRST_YEAR + i,
)

export const mainNavItems: Array<NavItem<MainPage>> = [
  { id: 'catalog', label: 'Home', icon: Home },
  { id: 'suggestions', label: 'For You', icon: Compass },
]

// One dedicated list entry per card action, each with its own accent colour
// (mirrors the per-action hover colours on the game cards).
export const collectionNavItems: Array<NavItem<CollectionKey>> = [
  { id: 'watchlist', label: 'Wishlist', icon: Bookmark },
  { id: 'playing', label: 'Playing', icon: Gamepad2 },
  { id: 'seen', label: 'Played', icon: History },
  { id: 'completed', label: 'Completed', icon: Trophy },
  { id: 'on_hold', label: 'On Hold', icon: CirclePause },
  { id: 'dropped', label: 'Dropped', icon: CircleX },
  { id: 'liked', label: 'Liked', icon: Heart },
  { id: 'favorites', label: 'Favorites', icon: Star },
]

export const utilityNavItems: Array<NavItem<UtilityPage>> = [
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'about', label: 'About', icon: Info },
]

export const mobileNavItems: Array<NavItem<MainPage | 'alerts'>> = [
  { id: 'catalog', label: 'Home', icon: Home },
  { id: 'watchlist', label: 'Wishlist', icon: Bookmark },
  { id: 'suggestions', label: 'For You', icon: Compass },
  { id: 'alerts', label: 'Alerts', icon: Bell },
]

export const collectionLabels: Record<CollectionKey, string> = {
  watchlist: 'Wishlist',
  playing: 'Playing',
  seen: 'Played',
  completed: 'Completed',
  on_hold: 'On Hold',
  dropped: 'Dropped',
  liked: 'Liked',
  favorites: 'Favorites',
}

export const collectionPageMap: Partial<Record<MainPage, CollectionKey>> = {
  watchlist: 'watchlist',
  playing: 'playing',
  seen: 'seen',
  completed: 'completed',
  on_hold: 'on_hold',
  dropped: 'dropped',
  liked: 'liked',
  favorites: 'favorites',
}

export const sortOptions: Array<{ label: string; value: GameSort }> = [
  { label: 'GameMetrix Rank', value: 'rank_score' },
  { label: 'Raw Score', value: 'metrix_score' },
  { label: 'Date Released', value: 'release_year' },
  { label: 'Critic Rating', value: 'critic_score' },
  { label: 'User Rating', value: 'user_score' },
  { label: 'Metacritic Rating', value: 'metacritic_score' },
  { label: 'OpenCritic Rating', value: 'opencritic_score' },
  { label: 'Steam Rating', value: 'steam_score' },
  { label: 'No. Ratings', value: 'review_count' },
  { label: 'Title', value: 'title' },
]

const PRESET_DESCRIPTIONS: Record<string, string> = {
  'goty-winners': 'Games recognized with Game of the Year or major industry awards — score reflects quality and data strength independently.',
  'hidden-gems': 'Critic-approved games with fewer than 1,500 reviews — high quality, low visibility.',
  'all-time-top': 'All-time highest-rated games with critic coverage across multiple primary sources.',
  'best-deals': 'Discounted, high-signal games with tracked store prices.',
  'free-games': 'Games currently tracked as free through store or FreeToGame data.',
}

const GENERIC_PRESET_DESCRIPTION = 'Curated from the GameMetrix catalog — sorted by reliability-weighted score.'
const SUGGESTIONS_DESCRIPTION = "Top-rated games you haven't played, liked, or saved yet — find your next play."

function bestOfYearDescription(year: number): string {
  if (year !== CURRENT_YEAR) return `Ranked by reliability-weighted score — ${year} full-year results.`
  const asOf = new Date().toLocaleString('en', { month: 'long', year: 'numeric' })
  return `Year in progress — ranked by reliability-weighted score as of ${asOf}.`
}

export function describeCatalogPage(
  activePreset: string | null,
  activePage: ActivePage,
  yearMin: number,
  pageTitle: string,
): string {
  if (activePreset === 'best-of-year') return bestOfYearDescription(yearMin)
  if (activePreset !== null) return PRESET_DESCRIPTIONS[activePreset] ?? GENERIC_PRESET_DESCRIPTION
  if (activePage === 'suggestions') return SUGGESTIONS_DESCRIPTION
  return `Your local ${pageTitle.toLowerCase()} list.`
}

// Deep-link support: developer / genre / year passed as URL query params on the
// catalog land on a pre-filtered homepage (used by the game detail page links).
export function readUrlFilters(search: string): Partial<GameFilters> {
  const params = new URLSearchParams(search)
  const next: Partial<GameFilters> = {}
  const genre = params.get('genre')?.trim()
  const developer = params.get('developer')?.trim()
  const publisher = params.get('publisher')?.trim()
  const year = Number(params.get('year'))
  if (genre) next.genre = genre
  if (developer) next.developer = developer
  if (publisher) next.publisher = publisher
  if (Number.isInteger(year) && year > EARLIEST_YEAR && year <= CURRENT_YEAR) {
    next.yearMin = year
    next.yearMax = year
  }
  return next
}

const THOUSAND = 1000

export function formatRoundedThousands(value: number): string {
  if (value >= THOUSAND) return `${Math.round(value / THOUSAND)}K`
  return new Intl.NumberFormat('en-US').format(value)
}
