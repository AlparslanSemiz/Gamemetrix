import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bell,
  CheckCircle2,
  ArrowDown,
  ArrowUp,
  Eye,
  Grid2X2,
  Heart,
  Info,
  List,
  LogIn,
  Search,
  Settings,
  Sparkles,
  Star,
  X,
} from 'lucide-react'
import './App.css'
import { FilterBar } from './components/FilterBar'
import { GameCard } from './components/GameCard'
import {
  getFacets,
  getGames,
  getIntegrationStatus,
  refreshGameScores,
  getScoreWeights,
  recalculateScores,
  updateScoreWeights,
} from './services/games'
import { CollectionsProvider } from './state/CollectionsProvider'
import type { CollectionKey } from './state/collections'
import { useCollections } from './state/useCollections'
import type { Facets, Game, GameFilters, GameSort, ProviderStatus } from './types/game'

type MainPage = 'catalog' | 'watchlist' | 'seen' | 'liked' | 'favorites' | 'suggestions'
type UtilityPage = 'login' | 'settings' | 'alerts' | 'about'
type ActivePage = MainPage | UtilityPage

const CURRENT_YEAR = new Date().getFullYear()
const PAGE_SIZE = 24

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
  minLiveSources: 0,
  requireCritic: false,
  sort: 'metrix_score',
  direction: 'desc',
}

const mainNavItems: Array<{ id: MainPage; label: string; icon: typeof Search }> = [
  { id: 'catalog', label: 'Search', icon: Search },
  { id: 'watchlist', label: 'Watchlist', icon: CheckCircle2 },
  { id: 'seen', label: 'Seen', icon: Eye },
  { id: 'liked', label: 'Liked', icon: Heart },
  { id: 'favorites', label: 'Favorites', icon: Star },
  { id: 'suggestions', label: 'Suggestions', icon: Sparkles },
]

const utilityNavItems: Array<{ id: UtilityPage; label: string; icon: typeof Search }> = [
  { id: 'login', label: 'Login', icon: LogIn },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'about', label: 'About', icon: Info },
]

const collectionLabels: Record<CollectionKey, string> = {
  watchlist: 'Watchlist',
  seen: 'Seen',
  liked: 'Liked',
  favorites: 'Favorites',
}

const collectionPageMap: Partial<Record<MainPage, CollectionKey>> = {
  watchlist: 'watchlist',
  seen: 'seen',
  liked: 'liked',
  favorites: 'favorites',
}

const sortOptions: Array<{ label: string; value: GameSort }> = [
  { label: 'Average Rating', value: 'metrix_score' },
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
  const [refreshingSlug, setRefreshingSlug] = useState<string | null>(null)
  const [trailerGame, setTrailerGame] = useState<Game | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
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
    if (activePage in collectionLabels) return collectionLabels[activePage as CollectionKey]
    if (activePage === 'catalog') return 'Catalog'
    if (activePage === 'suggestions') return 'Suggestions'
    return utilityNavItems.find((item) => item.id === activePage)?.label ?? 'GameMetrix'
  }, [activePage])

  const readyProviders = providerStatuses.filter((p) => p.status === 'ready').length

  const handleRefreshScores = async (slug: string) => {
    setRefreshingSlug(slug)
    setError(null)
    try {
      const refreshed = await refreshGameScores(slug)
      setGames((prev) => prev.map((g) => (g.slug === slug ? refreshed : g)))
    } catch {
      setError('Scores could not be refreshed for this game.')
    } finally {
      setRefreshingSlug(null)
    }
  }

  const goHome = () => {
    setActivePage('catalog')
    setFilters(DEFAULT_FILTERS)
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
        <div className="rail-group">
          {mainNavItems.map(({ icon: Icon, id, label }) => (
            <button
              type="button"
              className={activePage === id ? 'is-active' : ''}
              key={id}
              title={label}
              onClick={() => setActivePage(id)}
            >
              <Icon size={26} aria-hidden="true" />
              <span>{label}</span>
            </button>
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
              <Icon size={26} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </aside>

      <section className="workspace">
        <header className="masthead">
          <button type="button" className="brand" onClick={goHome}>
            G A M E&nbsp;&nbsp;M E T R I X
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
              <ScoreWeightSettings
                onSaved={() => {
                  setPendingApply((n) => n + 1)
                }}
              />
            ) : (
              <p>
                {activePage === 'login'
                  ? 'Login will connect personal collections across devices. Collections are saved locally for now.'
                  : activePage === 'alerts'
                    ? 'Alerts will notify you about new releases, score changes, and watchlist threshold crossings.'
                    : 'GameMetrix normalizes critic, player, and platform signals into one Bayesian-weighted discovery score.'}
              </p>
            )}
          </section>
        ) : (
          <section className="catalog" id="catalog">
            {activePage !== 'catalog' && (
              <div className="page-heading">
                <h1>{pageTitle}</h1>
                <p>
                  {activePage === 'suggestions'
                    ? 'High-scoring games you have not marked as seen, liked, or favorite yet.'
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

            <FilterBar
              key={`${pendingApply}-${facets.years.at(-1) ?? 1970}-${facets.years[0] ?? new Date().getFullYear()}`}
              facets={facets}
              filters={filters}
              onChange={setFilters}
              onApply={() => setPendingApply((n) => n + 1)}
            />

            <div className="list-toolbar">
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
                  key={game.id}
                  game={game}
                  compact={viewMode === 'grid'}
                  isFavorite={collections.favorites.includes(game.slug)}
                  isLiked={collections.liked.includes(game.slug)}
                  isRefreshing={refreshingSlug === game.slug}
                  isSeen={collections.seen.includes(game.slug)}
                  isWatchlisted={collections.watchlist.includes(game.slug)}
                  onOpenTrailer={setTrailerGame}
                  onRefresh={handleRefreshScores}
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
            onClick={() => setTrailerGame(null)}
          />
          <div className="modal-panel">
            <div className="modal-heading">
              <h2>{trailerGame.title}</h2>
              <button type="button" aria-label="Close trailer" onClick={() => setTrailerGame(null)}>
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <iframe
              title={`${trailerGame.title} trailer`}
              src={`https://www.youtube-nocookie.com/embed?listType=search&list=${trailerQuery}`}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        </div>
      ) : null}
    </main>
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

function App() {
  return (
    <CollectionsProvider>
      <AppContent />
    </CollectionsProvider>
  )
}

export default App
