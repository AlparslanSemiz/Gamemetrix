import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Award,
  BarChart2,
  Bell,
  CheckCircle2,
  ArrowDown,
  ArrowUp,
  Compass,
  Eye,
  Flag,
  Gamepad2,
  Gem,
  Gift,
  Grid2X2,
  Heart,
  Info,
  List,
  LogIn,
  Medal,
  Search,
  Settings,
  SlidersHorizontal,
  Star,
  Tag,
  Trophy,
  X,
} from 'lucide-react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './App.css'
import { FilterBar } from './components/FilterBar'
import { GameCard } from './components/GameCard'
import { GameDetailPage } from './pages/GameDetailPage'
import {
  getFacets,
  getGameTrailer,
  getGames,
  getIntegrationStatus,
  getRateLimits,
  getScoreWeights,
  recalculateScores,
  refreshAllScores,
  updateScoreWeights,
} from './services/games'
import { CollectionsProvider } from './state/CollectionsProvider'
import type { CollectionKey } from './state/collections'
import { useCollections } from './state/useCollections'
import type { Facets, Game, GameFilters, GameSort, ProviderStatus } from './types/game'

type MainPage = 'catalog' | 'watchlist' | 'playing' | 'seen' | 'completed' | 'liked' | 'favorites' | 'suggestions'
type UtilityPage = 'login' | 'settings' | 'alerts' | 'about'
type ActivePage = MainPage | UtilityPage

const CURRENT_YEAR = new Date().getFullYear()
const PAGE_SIZE = 24

interface CuratedPreset {
  id: string
  label: string
  icon: typeof Search
  filters: Partial<GameFilters>
}

interface SidebarGroup {
  label: string
  items: CuratedPreset[]
}

const SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    label: 'Top Lists',
    items: [
      {
        id: 'best-of-year',
        label: 'Best of the Year',
        icon: Trophy,
        filters: { sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'all-time-top',
        label: 'All-Time Top',
        icon: Star,
        filters: { requireCritic: true, minLiveSources: 2, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'critics-pick',
        label: "Critics' Picks",
        icon: Medal,
        filters: { requireCritic: true, minLiveSources: 1, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'goty-winners',
        label: 'GOTY Winners',
        icon: Award,
        filters: { hasAward: true, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'hidden-gems',
        label: 'Hidden Gems',
        icon: Gem,
        filters: { minScore: 75, maxRatings: 1500, requireCritic: true, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'most-reviewed',
        label: 'Most Reviewed',
        icon: BarChart2,
        filters: { sort: 'review_count', direction: 'desc', minLiveSources: 1 },
      },
    ],
  },
  {
    label: 'Deals',
    items: [
      {
        id: 'best-deals',
        label: 'Best Deals',
        icon: Tag,
        filters: { minScore: 80, minLiveSources: 1, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'free-games',
        label: 'Free Games',
        icon: Gift,
        filters: { sort: 'rank_score', direction: 'desc' },
      },
    ],
  },
]

function findPreset(id: string): CuratedPreset | undefined {
  for (const group of SIDEBAR_GROUPS) {
    const found = group.items.find((p) => p.id === id)
    if (found) return found
  }
  return undefined
}

const BEST_OF_YEAR_RANGE = Array.from(
  { length: CURRENT_YEAR - 2019 },
  (_, i) => CURRENT_YEAR - i,
).reverse()

const DEFAULT_FILTERS: GameFilters = {
  q: '',
  genre: '',
  platform: '',
  developer: '',
  publisher: '',
  yearMin: 1970,
  yearMax: CURRENT_YEAR,
  minScore: 0,
  maxScore: 100,
  minRatings: 0,
  maxRatings: 0,
  minLiveSources: 0,
  requireCritic: false,
  hasAward: false,
  sort: 'rank_score',
  direction: 'desc',
}

const mainNavItems: Array<{ id: MainPage; label: string; icon: typeof Search }> = [
  { id: 'catalog', label: 'Search', icon: Search },
  { id: 'watchlist', label: 'Wishlist', icon: CheckCircle2 },
  { id: 'playing', label: 'Playing', icon: Gamepad2 },
  { id: 'seen', label: 'Played', icon: Eye },
  { id: 'completed', label: 'Completed', icon: Flag },
  { id: 'liked', label: 'Liked', icon: Heart },
  { id: 'favorites', label: 'Favorites', icon: Star },
  { id: 'suggestions', label: 'For You', icon: Compass },
]

const utilityNavItems: Array<{ id: UtilityPage; label: string; icon: typeof Search }> = [
  { id: 'login', label: 'Login', icon: LogIn },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'about', label: 'About', icon: Info },
]

const collectionLabels: Record<CollectionKey, string> = {
  watchlist: 'Wishlist',
  playing: 'Playing',
  seen: 'Played',
  completed: 'Completed',
  liked: 'Liked',
  favorites: 'Favorites',
}

const collectionPageMap: Partial<Record<MainPage, CollectionKey>> = {
  watchlist: 'watchlist',
  playing: 'playing',
  seen: 'seen',
  completed: 'completed',
  liked: 'liked',
  favorites: 'favorites',
}

const sortOptions: Array<{ label: string; value: GameSort }> = [
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

function AppContent() {
  const [activePage, setActivePage] = useState<ActivePage>('catalog')
  const [games, setGames] = useState<Game[]>([])
  const [facets, setFacets] = useState<Facets>({ genres: [], years: [], platforms: [] })
  const [filters, setFilters] = useState<GameFilters>(DEFAULT_FILTERS)
  const [pendingApply, setPendingApply] = useState(0)
  const { collections, toggleCollection } = useCollections()
  const [providerStatuses, setProviderStatuses] = useState<ProviderStatus[]>([])
  const [catalogTotal, setCatalogTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [trailerGame, setTrailerGame] = useState<Game | null>(null)
  const [trailerVideoId, setTrailerVideoId] = useState<string | null>(null)
  const [isTrailerLoading, setIsTrailerLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [fetchKey, setFetchKey] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const loaderRef = useRef<HTMLDivElement>(null)
  // Always up to date with latest filters without being a dep of the load effect
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  useEffect(() => {
    let active = true
    async function loadFacets() {
      try {
        const nextFacets = await getFacets()
        if (active) setFacets(nextFacets)
      } catch {
        if (active) setError('Backend facets could not be loaded.')
      }
    }
    void loadFacets()
    void getIntegrationStatus().then(setProviderStatuses).catch(() => undefined)
    return () => { active = false }
  }, [])

  // Filter deps → reset to page 0 and bump the fetch key
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    setOffset(0)
    setFetchKey((k) => k + 1)
  }, [
    filters.q,
    filters.genre,
    filters.platform,
    filters.developer,
    filters.publisher,
    filters.minRatings,
    filters.minLiveSources,
    filters.requireCritic,
    filters.sort,
    filters.direction,
    pendingApply,
  ])

  // Actual fetch — triggered by fetchKey (filter change) or offset (scroll)
  useEffect(() => {
    let active = true
    const f = filtersRef.current
    const isFirst = offset === 0
    if (isFirst) {
      setIsLoading(true)
      setGames([])
    } else {
      setIsLoadingMore(true)
    }
    setError(null)

    async function loadGames() {
      try {
        const response = await getGames(f, PAGE_SIZE, offset)
        if (active) {
          if (isFirst) {
            setGames(response.games)
          } else {
            setGames((prev) => [...prev, ...response.games])
          }
          setCatalogTotal(response.total)
          setHasMore(offset + response.games.length < response.total)
        }
      } catch {
        if (active) {
          if (isFirst) setGames([])
          setError('GameMetrix API is not reachable yet.')
        }
      } finally {
        if (active) {
          if (isFirst) setIsLoading(false)
          else setIsLoadingMore(false)
        }
      }
    }
    void loadGames()
    return () => { active = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchKey, offset])

  // IntersectionObserver — load next page when sentinel enters viewport
  useEffect(() => {
    const el = loaderRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !isLoadingMore && !isLoading) {
          setOffset((prev) => prev + PAGE_SIZE)
        }
      },
      { rootMargin: '300px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, isLoadingMore, isLoading])

  const visibleGames = useMemo(() => {
    if (activePage === 'suggestions') {
      const excluded = new Set([
        ...collections.seen,
        ...collections.completed,
        ...collections.favorites,
        ...collections.liked,
      ])
      return games
        .filter((g) => !excluded.has(g.slug))
        .sort((a, b) => b.metrix_score - a.metrix_score)
    }
    const collectionKey = collectionPageMap[activePage as MainPage]
    if (!collectionKey) return games
    const allowed = new Set(collections[collectionKey])
    return games.filter((g) => allowed.has(g.slug))
  }, [activePage, collections, games])

  const pageTitle = useMemo(() => {
    if (activePreset === 'best-of-year') {
      const year = filters.yearMin
      return year === CURRENT_YEAR ? `Best of ${year} · So Far` : `Best of ${year}`
    }
    if (activePage in collectionLabels) return collectionLabels[activePage as CollectionKey]
    if (activePage === 'catalog') return 'Catalog'
    if (activePage === 'suggestions') return 'Discover'
    return utilityNavItems.find((item) => item.id === activePage)?.label ?? 'GameMetrix'
  }, [activePage, activePreset, filters.yearMin])

  const readyProviders = providerStatuses.filter((p) => p.status === 'ready').length

  const handleOpenTrailer = async (game: Game) => {
    setTrailerGame(game)
    setTrailerVideoId(null)
    setIsTrailerLoading(true)
    try {
      const trailer = await getGameTrailer(game.slug)
      setTrailerVideoId(trailer.video_id)
    } catch {
      setTrailerVideoId(null)
    } finally {
      setIsTrailerLoading(false)
    }
  }

  const goHome = () => {
    setActivePage('catalog')
    setFilters(DEFAULT_FILTERS)
    setActivePreset(null)
    setPendingApply((n) => n + 1)
  }

  const applyPreset = (preset: CuratedPreset) => {
    setActivePage('catalog')
    setActivePreset(preset.id)
    if (preset.id === 'best-of-year') {
      setFilters({ ...DEFAULT_FILTERS, yearMin: CURRENT_YEAR, yearMax: CURRENT_YEAR, sort: 'rank_score', direction: 'desc' })
    } else {
      setFilters({ ...DEFAULT_FILTERS, ...preset.filters })
    }
    setPendingApply((n) => n + 1)
  }

  const selectBestOfYear = (year: number) => {
    setFilters((prev) => ({ ...prev, yearMin: year, yearMax: year }))
    setPendingApply((n) => n + 1)
  }

  const clearFilter = (key: 'developer' | 'publisher' | 'genre' | 'platform') => {
    setFilters((current) => ({ ...current, [key]: '' }))
  }

  const isUtilityPage = utilityNavItems.some((item) => item.id === activePage)
  const trailerQuery = trailerGame
    ? encodeURIComponent(`${trailerGame.title} official trailer game`)
    : ''

  return (
    <main className="app-shell">
      <aside className="side-rail" aria-label="Workspace navigation">
        <div className="rail-top">
          <div className="rail-group">
            {mainNavItems.map(({ icon: Icon, id, label }) => (
              <button
                type="button"
                className={activePage === id && activePreset === null ? 'is-active' : ''}
                key={id}
                title={label}
                onClick={() => { setActivePage(id); setActivePreset(null) }}
              >
                <Icon size={22} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </div>
          {SIDEBAR_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="rail-divider" />
              <div className="rail-group rail-group-curated">
                <span className="rail-section-label">{group.label}</span>
                {group.items.map((preset) => {
                  const Icon = preset.icon
                  return (
                    <button
                      type="button"
                      className={activePreset === preset.id ? 'is-active' : ''}
                      key={preset.id}
                      title={preset.label}
                      onClick={() => applyPreset(preset)}
                    >
                      <Icon size={18} aria-hidden="true" />
                      <span>{preset.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="rail-group">
          {utilityNavItems.map(({ icon: Icon, id, label }) => (
            <button
              type="button"
              className={activePage === id ? 'is-active' : ''}
              key={id}
              title={label}
              onClick={() => setActivePage(id)}
            >
              <Icon size={22} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </aside>

      <section className="workspace">
        <header className="masthead">
          <button type="button" className="brand" onClick={goHome}>
            <img src="/favicon.svg" alt="" className="brand-icon" aria-hidden="true" />
            <span className="brand-text">
              Game<span className="brand-accent">Metrix</span>
            </span>
          </button>
          <div className="masthead-search">
            <input
              type="search"
              placeholder="Title Search"
              value={filters.q}
              onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))}
              aria-label="Search games by title"
            />
            <Search size={18} aria-hidden="true" />
          </div>
        </header>

        <div className="provider-strip">
          <span>{visibleGames.length} shown</span>
          <span>{games.length} / {catalogTotal || games.length} loaded</span>
          <span>{readyProviders} / {providerStatuses.length || 5} providers ready</span>
        </div>

        {isUtilityPage ? (
          <section className="utility-panel">
            <h1>{pageTitle}</h1>
            {activePage === 'settings' ? (
              <>
                <h2 style={{ fontSize: '0.9rem', color: '#6b7280', marginBottom: '6px', marginTop: '16px' }}>Score Weights</h2>
                <ScoreWeightSettings onSaved={() => { setPendingApply((n) => n + 1) }} />
                <h2 style={{ fontSize: '0.9rem', color: '#6b7280', marginBottom: '6px', marginTop: '24px' }}>Score Data</h2>
                <RefreshAllPanel />
              </>
            ) : activePage === 'about' ? (
              <RatingExplainer />
            ) : (
              <p>
                {activePage === 'login'
                  ? 'Login will connect personal collections across devices. Collections are saved locally for now.'
                  : 'Alerts will notify you about new releases, score changes, and watchlist threshold crossings.'}
              </p>
            )}
          </section>
        ) : (
          <section className="catalog" id="catalog">
            {(activePage !== 'catalog' || activePreset !== null) && (
              <div className="page-heading">
                <h1>
                  {activePreset === 'best-of-year'
                    ? pageTitle
                    : activePreset !== null
                      ? (findPreset(activePreset)?.label ?? pageTitle)
                      : pageTitle}
                </h1>
                {activePreset === 'best-of-year' && (
                  <div className="year-picker" role="group" aria-label="Select year">
                    {BEST_OF_YEAR_RANGE.map((year) => (
                      <button
                        key={year}
                        type="button"
                        className={filters.yearMin === year ? 'is-active' : ''}
                        onClick={() => selectBestOfYear(year)}
                      >
                        {year === CURRENT_YEAR ? `${year} · So Far` : String(year)}
                      </button>
                    ))}
                  </div>
                )}
                <p>
                  {activePreset === 'best-of-year'
                    ? filters.yearMin === CURRENT_YEAR
                      ? `Year in progress — ranked by reliability-weighted score as of ${new Date().toLocaleString('en', { month: 'long', year: 'numeric' })}.`
                      : `Ranked by reliability-weighted score — ${filters.yearMin} full-year results.`
                    : activePreset === 'goty-winners'
                      ? 'Games recognized with Game of the Year or major industry awards — score reflects quality and data strength independently.'
                      : activePreset === 'hidden-gems'
                        ? 'Critic-approved games with fewer than 1,500 reviews — high quality, low visibility.'
                        : activePreset === 'all-time-top'
                          ? 'All-time highest-rated games with critic coverage across multiple primary sources.'
                          : activePreset === 'best-deals'
                            ? 'High-quality games at low prices — score ≥ 80, critic-backed.'
                            : activePreset !== null
                              ? 'Curated from the GameMetrix catalog — sorted by reliability-weighted score.'
                              : activePage === 'suggestions'
                                ? 'Top-rated games you haven\'t played, liked, or saved yet — find your next play.'
                                : `Your local ${pageTitle.toLowerCase()} list.`}
                </p>
              </div>
            )}

            {filters.developer || filters.publisher || filters.genre || filters.platform ? (
              <div className="active-filter-row" aria-label="Active filters">
                {filters.developer ? (
                  <button type="button" onClick={() => clearFilter('developer')}>
                    Developer: {filters.developer} ×
                  </button>
                ) : null}
                {filters.publisher ? (
                  <button type="button" onClick={() => clearFilter('publisher')}>
                    Publisher: {filters.publisher} ×
                  </button>
                ) : null}
                {filters.genre ? (
                  <button type="button" onClick={() => clearFilter('genre')}>
                    Genre: {filters.genre} ×
                  </button>
                ) : null}
                {filters.platform ? (
                  <button type="button" onClick={() => clearFilter('platform')}>
                    Platform: {filters.platform} ×
                  </button>
                ) : null}
              </div>
            ) : null}

            {filtersOpen ? (
              <FilterBar
                key={`${pendingApply}-${facets.years.at(-1) ?? 1970}-${facets.years[0] ?? new Date().getFullYear()}`}
                facets={facets}
                filters={filters}
                onChange={setFilters}
                onApply={() => setPendingApply((n) => n + 1)}
              />
            ) : null}

            <div className="list-toolbar">
              <button
                type="button"
                className={`filter-toggle-button${filtersOpen ? ' is-active' : ''}`}
                onClick={() => setFiltersOpen((o) => !o)}
                title={filtersOpen ? 'Hide filters' : 'Show filters'}
              >
                <SlidersHorizontal size={15} aria-hidden="true" />
                <span>Filters</span>
              </button>
              <div className="sort-label">
                <span>Sort By:</span>
                <select
                  aria-label="Sort games"
                  value={filters.sort}
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      sort: event.target.value as GameSort,
                    }))
                  }
                >
                  {sortOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="sort-direction-button"
                  title={filters.direction === 'desc' ? 'High to low' : 'Low to high'}
                  onClick={() =>
                    setFilters((current) => ({
                      ...current,
                      direction: current.direction === 'desc' ? 'asc' : 'desc',
                    }))
                  }
                >
                  {filters.direction === 'desc' ? (
                    <ArrowDown size={15} aria-hidden="true" />
                  ) : (
                    <ArrowUp size={15} aria-hidden="true" />
                  )}
                </button>
                <span className="sort-direction-text">
                  {filters.direction === 'desc' ? 'High to low' : 'Low to high'}
                </span>
              </div>
              <div className="view-toggle" aria-label="View mode">
                <button
                  type="button"
                  className={viewMode === 'list' ? 'is-active' : ''}
                  onClick={() => setViewMode('list')}
                  title="List view"
                >
                  <List size={17} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className={viewMode === 'grid' ? 'is-active' : ''}
                  onClick={() => setViewMode('grid')}
                  title="Grid view"
                >
                  <Grid2X2 size={16} aria-hidden="true" />
                </button>
              </div>
            </div>

            {error ? <p className="status status-error">{error}</p> : null}
            {isLoading ? <p className="status">Loading games…</p> : null}
            {!isLoading && visibleGames.length === 0 ? (
              <p className="status">No games match this view yet.</p>
            ) : null}

            <div className={`game-list game-list-${viewMode}`}>
              {visibleGames.map((game) => (
                <GameCard
                  key={`${game.id}-${game.slug}`}
                  game={game}
                  compact={viewMode === 'grid'}
                  isFavorite={collections.favorites.includes(game.slug)}
                  isLiked={collections.liked.includes(game.slug)}
                  isPlaying={collections.playing.includes(game.slug)}
                  isSeen={collections.seen.includes(game.slug)}
                  isCompleted={collections.completed.includes(game.slug)}
                  isWatchlisted={collections.watchlist.includes(game.slug)}
                  onOpenTrailer={handleOpenTrailer}
                  onFilterDeveloper={(developer) => {
                    setActivePage('catalog')
                    setFilters((p) => ({ ...p, developer, publisher: '' }))
                  }}
                  onFilterGenre={(genre) => {
                    setActivePage('catalog')
                    setFilters((p) => ({ ...p, genre }))
                  }}
                  onFilterPublisher={(publisher) => {
                    setActivePage('catalog')
                    setFilters((p) => ({ ...p, publisher, developer: '' }))
                  }}
                  onToggleCollection={toggleCollection}
                />
              ))}
            </div>
            <div ref={loaderRef} className="scroll-sentinel" aria-hidden="true">
              {isLoadingMore ? <p className="status">Loading more…</p> : null}
            </div>
          </section>
        )}
      </section>

      {trailerGame ? (
        <div
          className="trailer-modal"
          role="dialog"
          aria-modal="true"
          aria-label={`${trailerGame.title} trailer`}
        >
          <button
            type="button"
            className="modal-backdrop"
            aria-label="Close trailer"
            onClick={() => {
              setTrailerGame(null)
              setTrailerVideoId(null)
            }}
          />
          <div className="modal-panel">
            <div className="modal-heading">
              <h2>{trailerGame.title}</h2>
              <button
                type="button"
                aria-label="Close trailer"
                onClick={() => {
                  setTrailerGame(null)
                  setTrailerVideoId(null)
                }}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            {isTrailerLoading ? (
              <div className="trailer-loading">Loading trailer...</div>
            ) : trailerVideoId ? (
              <iframe
                title={`${trailerGame.title} trailer`}
                src={`https://www.youtube-nocookie.com/embed/${trailerVideoId}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <a
                className="trailer-fallback-link"
                href={`https://www.youtube.com/results?search_query=${trailerQuery}`}
                target="_blank"
                rel="noreferrer"
              >
                Open trailer search on YouTube
              </a>
            )}
          </div>
        </div>
      ) : null}
    </main>
  )
}

function RefreshAllPanel() {
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [rateLimits, setRateLimits] = useState<Record<string, { remaining: number; limit: number }> | null>(null)

  useEffect(() => {
    void getRateLimits().then(setRateLimits).catch(() => {})
  }, [])

  const trigger = async (force: boolean) => {
    setBusy(true)
    setStatus(null)
    try {
      const { message } = await refreshAllScores(force, 3)
      setStatus(message)
      void getRateLimits().then(setRateLimits).catch(() => {})
    } catch {
      setStatus('Failed to start refresh.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="score-weight-panel">
      <p>Scores are fetched automatically every 6 hours. Use the buttons below for manual control.</p>
      <div style={{ display: 'flex', gap: '10px', marginTop: '12px', flexWrap: 'wrap' }}>
        <button type="button" className="apply-button" disabled={busy} onClick={() => trigger(false)}>
          {busy ? 'Starting…' : '⚡ Refresh stale games'}
        </button>
        <button type="button" className="apply-button" disabled={busy} onClick={() => trigger(true)}
          style={{ background: '#dc2626' }}>
          {busy ? 'Starting…' : '🔄 Force refresh ALL'}
        </button>
      </div>
      {status && <p style={{ marginTop: '10px', color: '#9ca3af', fontSize: '0.82rem' }}>{status}</p>}
      {rateLimits && (
        <div style={{ marginTop: '16px' }}>
          <p style={{ color: '#6b7280', fontSize: '0.78rem', marginBottom: '8px' }}>Today's API budget (resets at midnight):</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 20px' }}>
            {Object.entries(rateLimits).map(([source, { remaining, limit }]) => {
              const pct = limit > 0 ? (remaining / limit) * 100 : 0
              const color = remaining === 0 ? '#dc2626' : pct < 20 ? '#f59e0b' : '#22c55e'
              return (
                <div key={source} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.79rem' }}>
                  <span style={{ color: '#9ca3af', minWidth: '88px' }}>{source}</span>
                  <div style={{ flex: 1, height: '3px', background: '#1f2937', borderRadius: '2px' }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: '2px', transition: 'width 0.3s' }} />
                  </div>
                  <span style={{ color, minWidth: '44px', textAlign: 'right' }}>{remaining}/{limit}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function ScoreWeightSettings({ onSaved }: { onSaved: () => void }) {
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [message, setMessage] = useState<string>('Loading score weights…')

  useEffect(() => {
    void getScoreWeights()
      .then((response) => {
        setWeights(response.weights)
        setMessage('Tune how strongly each source contributes to Metrix Score.')
      })
      .catch(() => setMessage('Score weights could not be loaded.'))
  }, [])

  const saveWeights = async () => {
    setMessage('Saving weights and recalculating scores…')
    try {
      await updateScoreWeights(weights)
      const result = await recalculateScores()
      setMessage(`Saved. Recalculated ${result.recalculated} games.`)
      onSaved()
    } catch {
      setMessage('Weights could not be saved.')
    }
  }

  return (
    <div className="score-weight-panel">
      <p>{message}</p>
      <div className="weight-grid">
        {Object.entries(weights).map(([source, value]) => (
          <label key={source}>
            <span>{source}</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={value}
              onChange={(event) =>
                setWeights((current) => ({
                  ...current,
                  [source]: Number(event.target.value),
                }))
              }
            />
            <output>{value.toFixed(2)}</output>
          </label>
        ))}
      </div>
      <button type="button" className="apply-button settings-save" onClick={saveWeights}>
        Save weights
      </button>
    </div>
  )
}

function RatingExplainer() {
  return (
    <div className="about-rating">
      <p className="about-lead">
        GameMetrix pulls scores from multiple independent sources and combines them into one transparent signal.
        Here's exactly how it works.
      </p>

      {/* Sources */}
      <div className="about-block">
        <h3>Rating sources</h3>
        <div className="about-source-list">
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-primary">Metacritic</span>
              <span className="about-badge badge-primary">OpenCritic</span>
            </div>
            <span className="about-source-desc">Professional critic reviews — highest signal quality</span>
          </div>
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-primary">Steam</span>
              <span className="about-badge badge-primary">IGDB</span>
            </div>
            <span className="about-source-desc">Player scores — Steam applies to PC games only</span>
          </div>
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-secondary">RAWG</span>
            </div>
            <span className="about-source-desc">Backup only — fills a missing primary slot at 70% weight</span>
          </div>
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-support">SteamSpy</span>
              <span className="about-badge badge-support">CheapShark</span>
              <span className="about-badge badge-support">FreeToGame</span>
            </div>
            <span className="about-source-desc">Support data only — popularity, pricing, availability. Never affect the score.</span>
          </div>
        </div>
      </div>

      {/* Score */}
      <div className="about-block">
        <h3>GameMetrix Score</h3>
        <p>
          Up to 4 sources averaged with equal weight (25% each). If a primary source
          is unavailable for a game, RAWG can fill the gap at reduced weight.
        </p>
        <div className="about-score-demo">
          {[['Metacritic', 96], ['OpenCritic', 94], ['Steam', 92], ['IGDB', 90]].map(([src, val]) => (
            <div key={src as string} className="about-score-row">
              <span className="about-score-src">{src}</span>
              <div className="about-score-track">
                <div className="about-score-fill" style={{ width: `${val}%` }} />
              </div>
              <strong>{val}</strong>
            </div>
          ))}
          <div className="about-score-result">
            <span>GameMetrix Score</span>
            <span className="about-score-eq">= (96 + 94 + 92 + 90) ÷ 4</span>
            <strong className="about-score-final">93</strong>
          </div>
        </div>
      </div>

      {/* Rank */}
      <div className="about-block">
        <h3>
          GameMetrix Rank
          <span className="about-tag">Default sort</span>
        </h3>
        <p>
          A game showing 96 from one source shouldn't outrank Elden Ring with four.
          Rank shrinks the score toward a neutral baseline (70) based on how much
          reliable data exists. The card score never changes — only the ordering.
        </p>
        <div className="about-strength-table">
          <div className="about-strength-row">
            <span className="about-str-badge str-strong">Strong</span>
            <span className="about-str-desc">3–4 sources, critic + player mix</span>
            <span className="about-str-example">96 → <strong>96.0</strong></span>
          </div>
          <div className="about-strength-row">
            <span className="about-str-badge str-solid">Solid</span>
            <span className="about-str-desc">2+ sources or strong single coverage</span>
            <span className="about-str-example">96 → <strong>93.4</strong></span>
          </div>
          <div className="about-strength-row">
            <span className="about-str-badge str-limited">Limited</span>
            <span className="about-str-desc">1 source or backup-only data</span>
            <span className="about-str-example">96 → <strong>86.9</strong></span>
          </div>
          <div className="about-strength-row">
            <span className="about-str-badge str-catalog">Catalog</span>
            <span className="about-str-desc">No live rating data yet</span>
            <span className="about-str-example">Excluded from top lists</span>
          </div>
        </div>
      </div>

      {/* Platform fairness */}
      <div className="about-block">
        <h3>Platform fairness</h3>
        <p>
          Steam is only counted for PC games. A Nintendo exclusive missing Steam is not penalized —
          its applicable sources are Metacritic, OpenCritic, and IGDB, and full coverage across
          those three still qualifies as <strong>Data Strong</strong>.
        </p>
      </div>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <CollectionsProvider>
        <Routes>
          <Route path="/game/:slug" element={<GameDetailPage />} />
          <Route path="*" element={<AppContent />} />
        </Routes>
      </CollectionsProvider>
    </BrowserRouter>
  )
}

export default App
