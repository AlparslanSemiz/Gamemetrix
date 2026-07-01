/* eslint-disable react-hooks/set-state-in-effect */
import { type CSSProperties, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { fetchGamePrices, fetchGameScreenshots, getGameBySlug, getGameTrailer, getGames, refreshGameScores } from '../services/games'
import { ScoreRing } from '../components/ScoreRing'
import { PlatformIcons } from '../components/PlatformIcons'
import { scoreColor, scoreColorRgb, sourceScoreColor } from '../utils/scoreColors'
import type { Game, GameFilters, PriceSnapshot, SourceScore, SystemRequirement } from '../types/game'
import './GameDetailPage.css'

// The 4 core quality sources shown in the main rating block
const CURRENT_YEAR = new Date().getFullYear()
const PRIMARY_4 = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB'] as const
// Extra sources shown in the secondary tab
const EXTRA_SOURCES = ['RAWG', 'SteamSpy', 'CheapShark', 'FreeToGame'] as const
const RATING_SOURCES = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB', 'RAWG'] as const

const SIMILAR_DEFAULT_FILTERS: GameFilters = {
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

function sourceExternalUrl(source: string, game: Game): string | null {
  const q = encodeURIComponent(game.title)
  const steamAppId = game.cover_url?.match(/steam\/apps\/(\d+)\//)?.[1]
  switch (source) {
    case 'Metacritic': return `https://www.metacritic.com/search/${q}/`
    case 'OpenCritic': return `https://opencritic.com/game/search?criteria=${q}`
    case 'Steam': return steamAppId ? `https://store.steampowered.com/app/${steamAppId}/` : null
    case 'IGDB': return `https://www.igdb.com/search?type=1&q=${q}`
    case 'RAWG': return `https://rawg.io/search?query=${q}`
    case 'SteamSpy': return steamAppId ? `https://steamspy.com/app/${steamAppId}` : null
    default: return null
  }
}

function SourceRow({ s, game, filler = false }: { s: SourceScore; game: Game; filler?: boolean }) {
  const url = sourceExternalUrl(s.source, game)
  const pct = Math.max(0, Math.min(s.score, 100))
  const isPrimary = !filler && (PRIMARY_4 as readonly string[]).includes(s.source)
  const nameEl = url ? (
    <a href={url} target="_blank" rel="noopener noreferrer" className={`dp-src-name dp-src-link${filler ? ' dp-src-secondary' : ''}`}>
      {s.source} <ExternalLink size={9} />
    </a>
  ) : (
    <span className={`dp-src-name${isPrimary ? '' : ' dp-src-secondary'}`}>{s.source}</span>
  )
  return (
    <div
      className={`dp-src-row${filler ? ' dp-src-row-secondary' : ''}`}
      title={s.detail ?? s.source}
      style={{ '--source-color': sourceScoreColor(pct) } as CSSProperties}
    >
      {nameEl}
      <div className="dp-src-bar"><span className="dp-src-fill" style={{ width: `${pct}%` }} /></div>
      <strong className="dp-src-score">{Math.round(s.score)}</strong>
      {s.review_count ? (
        <span className="dp-src-count">{s.review_count.toLocaleString()}</span>
      ) : null}
    </div>
  )
}

function formatCompactCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 100_000 ? 0 : 1)}K`
  return value.toLocaleString()
}

function formatDate(value?: string | null): string {
  if (!value) return 'Not tracked'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()) || date.getFullYear() <= 1970) return 'Not tracked'
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: value % 1 === 0 ? 0 : 2,
  }).format(value)
}

function reliabilityCopy(game: Game, livePrimaryCount: number, rawgFillsSlot: boolean) {
  const applicableCount = game.applicable_source_count ?? 4
  const missing = Math.max(0, applicableCount - livePrimaryCount)
  const rawgNote = rawgFillsSlot ? ' RAWG is filling one missing source slot at reduced weight.' : ''
  if (game.confidence_level === 'Strong') {
    return `${livePrimaryCount}/${applicableCount} primary sources, critic and player signal covered.`
  }
  if (game.confidence_level === 'Solid') {
    return `${livePrimaryCount}/${applicableCount} primary sources. Good signal, still missing ${missing}.${rawgNote}`
  }
  if (game.confidence_level === 'Limited') {
    return `${livePrimaryCount}/${applicableCount} primary sources. Score is uncertainty-adjusted.${rawgNote}`
  }
  return 'Catalog entry. Live rating data has not been collected yet.'
}

function popularitySummary(game: Game) {
  const reviewCount = game.source_scores
    .filter((s) => s.status === 'live' && (RATING_SOURCES as readonly string[]).includes(s.source))
    .reduce((sum, s) => sum + (s.review_count ?? 0), 0)

  return {
    label: game.popularity_label ?? 'Untracked',
    count: reviewCount,
    detail: reviewCount > 0 ? `${formatCompactCount(reviewCount)} tracked reviews` : 'No reliable volume signal yet',
  }
}

function sortedPrices(prices: PriceSnapshot[]): PriceSnapshot[] {
  return [...prices].sort((a, b) => {
    const aPrice = a.sale_price ?? a.list_price ?? Number.POSITIVE_INFINITY
    const bPrice = b.sale_price ?? b.list_price ?? Number.POSITIVE_INFINITY
    return aPrice - bPrice
  })
}

function PricePanel({ prices }: { prices: PriceSnapshot[] }) {
  const ordered = sortedPrices(prices)
  if (ordered.length === 0) return null
  const best = ordered[0]
  const current = best.is_free ? 'Free' : formatMoney(best.sale_price ?? best.list_price, best.currency)
  const hasDiscount = Boolean(best.discount_percent && best.discount_percent > 0)

  return (
    <div className="dp-price-panel">
      <div className="dp-price-primary">
        <span>Best current price</span>
        <strong>{current}</strong>
        <small>
          {best.store}
          {hasDiscount ? ` · ${best.discount_percent}% off` : ''}
          {best.region ? ` · ${best.region}` : ''}
        </small>
      </div>
      <div className="dp-price-meta">
        <div>
          <span>List price</span>
          <strong>{formatMoney(best.list_price, best.currency)}</strong>
        </div>
        <div>
          <span>Historical low</span>
          <strong>{formatMoney(best.historical_low, best.currency)}</strong>
          <small>{formatDate(best.historical_low_date)}</small>
        </div>
        {best.is_subscription_included && (
          <div>
            <span>Subscription</span>
            <strong>{best.subscription_service ?? 'Included'}</strong>
          </div>
        )}
      </div>
      <div className="dp-store-list">
        {ordered.slice(0, 4).map((price) => {
          const label = price.is_free ? 'Free' : formatMoney(price.sale_price ?? price.list_price, price.currency)
          const content = (
            <>
              <span>{price.store}</span>
              <strong>{label}</strong>
            </>
          )
          return price.url ? (
            <a key={`${price.source}-${price.store}-${price.fetched_at}`} href={price.url} target="_blank" rel="noreferrer" className="dp-store-row">
              {content}
            </a>
          ) : (
            <div key={`${price.source}-${price.store}-${price.fetched_at}`} className="dp-store-row">
              {content}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function displayDlcTitle(gameTitle: string, dlcTitle: string) {
  const cleaned = dlcTitle
    .replace(new RegExp(`^${escapeRegExp(gameTitle)}\\s*[-:–—]\\s*`, 'i'), '')
    .trim()
  return cleaned || dlcTitle
}

function DlcSection({ game }: { game: Game }) {
  if (game.dlcs.length === 0) return null
  return (
    <section className="dp-dlc-section" aria-labelledby="dlc-title">
      <div className="dp-similar-heading">
        <h2 id="dlc-title">DLCs & expansions</h2>
        <small>{game.dlcs.length} add-ons</small>
      </div>
      <div className="dp-dlc-grid">
        {game.dlcs.slice(0, 12).map((item) => {
          const score = item.metacritic_score ?? (item.rating ? Math.round(item.rating * 20) : null)
          const title = displayDlcTitle(game.title, item.title)
          const accentScore = Math.round(score ?? game.rank_score)
          const cardStyle = {
            '--score-color': scoreColor(accentScore),
            '--score-rgb': scoreColorRgb(accentScore),
          } as CSSProperties
          const body = (
            <>
              <div className="dp-dlc-cover">
                {item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : null}
                {score ? (
                  <span
                    className="dp-similar-score"
                    style={{ '--score-color': scoreColor(Math.round(score)) } as CSSProperties}
                  >
                    {Math.round(score)}
                  </span>
                ) : null}
              </div>
              <div className="dp-dlc-body">
                <span>{item.type ? item.type.toUpperCase() : 'DLC'}</span>
                <strong title={item.title}>{title}</strong>
                <small>{item.release_year && item.release_year > 1970 ? item.release_year : 'Release date not tracked'}</small>
              </div>
            </>
          )
          return item.url ? (
            <a
              key={`${item.title}-${item.id ?? item.slug ?? ''}`}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="dp-dlc-card"
              style={cardStyle}
            >
              {body}
            </a>
          ) : (
            <div key={`${item.title}-${item.id ?? item.slug ?? ''}`} className="dp-dlc-card" style={cardStyle}>
              {body}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function SimilarGamesSection({
  game,
  catalogGames,
}: {
  game: Game
  catalogGames: Game[]
}) {
  const rawgItems = game.similar_games.filter((item) => item.title !== game.title)
  const catalogItems = catalogGames.filter((item) => item.slug !== game.slug)
  const hasItems = rawgItems.length > 0 || catalogItems.length > 0
  if (!hasItems) return null

  return (
    <section className="dp-similar-section" aria-labelledby="similar-games-title">
      <div className="dp-similar-heading">
        <h2 id="similar-games-title">Games like {game.title}</h2>
      </div>
      <div className="dp-similar-grid">
        {catalogItems.slice(0, 10).map((item) => (
          <Link
            key={item.slug}
            to={`/game/${item.slug}`}
            className="dp-similar-card"
          >
            <div className="dp-similar-cover">
              {item.cover_url || item.image_url ? (
                <img src={item.cover_url || item.image_url || ''} alt="" loading="lazy" />
              ) : null}
              <span
                className="dp-similar-score"
                style={{ '--score-color': scoreColor(Math.round(item.metrix_score)) } as CSSProperties}
              >
                {Math.round(item.metrix_score)}
              </span>
            </div>
            <div className="dp-similar-body">
              <PlatformIcons platforms={item.platforms} mode="compact" maxVisible={5} />
              <strong>{item.title}</strong>
              <span>{item.release_year > 1970 ? item.release_year : 'TBA'}</span>
            </div>
          </Link>
        ))}
        {catalogItems.length < 8 && rawgItems.slice(0, 8 - catalogItems.length).map((item) => (
          <a
            key={`${item.title}-${item.id ?? item.slug ?? ''}`}
            href={item.url ?? '#'}
            target={item.url ? '_blank' : undefined}
            rel={item.url ? 'noreferrer' : undefined}
            className="dp-similar-card"
          >
            <div className="dp-similar-cover">
              {item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : null}
              {item.metacritic_score ? (
                <span
                  className="dp-similar-score"
                  style={{ '--score-color': scoreColor(Math.round(item.metacritic_score)) } as CSSProperties}
                >
                  {Math.round(item.metacritic_score)}
                </span>
              ) : null}
            </div>
            <div className="dp-similar-body">
              <strong>{item.title}</strong>
              <span>{item.release_year && item.release_year > 1970 ? item.release_year : 'TBA'}</span>
            </div>
          </a>
        ))}
      </div>
    </section>
  )
}

function buildAboutParagraphs(game: Game): string[] {
  const paragraphs = [game.summary].filter(Boolean)
  const release = game.release_year > 1970 ? `released in ${game.release_year}` : 'released at an unknown date'
  const developer = game.developer ? ` developed by ${game.developer}` : ''
  const publisher = game.publisher && game.publisher !== game.developer ? ` and published by ${game.publisher}` : ''
  const genres = game.genres.length ? ` It sits across ${game.genres.slice(0, 4).join(', ')}.` : ''
  const platforms = game.platforms.length ? ` Current platform coverage includes ${game.platforms.join(', ')}.` : ''
  paragraphs.push(`${game.title} was ${release}${developer}${publisher}.${genres}${platforms}`)

  if (game.playtime_minutes > 0 || game.goty_year || game.award_count > 0) {
    const notes: string[] = []
    if (game.playtime_minutes > 0) notes.push(`average tracked playtime is around ${Math.round(game.playtime_minutes / 60)} hours`)
    if (game.goty_year) notes.push(`it was a Game of the Year winner in ${game.goty_year}`)
    else if (game.award_count > 0) notes.push(`it has ${game.award_count} major award signals`)
    paragraphs.push(`For catalog context, ${notes.join(', ')}.`)
  }

  return paragraphs
}

function SysReqBlock({ req }: { req: SystemRequirement }) {
  const [tab, setTab] = useState<'minimum' | 'recommended'>(
    req.recommended ? 'recommended' : 'minimum',
  )
  const hasRecommended = Boolean(req.recommended)

  function formatReqs(raw: string): string {
    return raw
      .replace(/Minimum:\r?\n?/i, '')
      .replace(/Recommended:\r?\n?/i, '')
      .trim()
  }

  return (
    <div className="dp-sysreq-block">
      <h4 className="dp-sysreq-platform">{req.platform}</h4>
      {hasRecommended && (
        <div className="dp-sysreq-tabs">
          <button
            type="button"
            className={tab === 'minimum' ? 'dp-sysreq-tab is-active' : 'dp-sysreq-tab'}
            onClick={() => setTab('minimum')}
          >
            Minimum
          </button>
          <button
            type="button"
            className={tab === 'recommended' ? 'dp-sysreq-tab is-active' : 'dp-sysreq-tab'}
            onClick={() => setTab('recommended')}
          >
            Recommended
          </button>
        </div>
      )}
      <pre className="dp-sysreq-text">
        {tab === 'minimum' ? formatReqs(req.minimum) : formatReqs(req.recommended)}
      </pre>
    </div>
  )
}

function Gallery({ game }: { game: Game }) {
  const images = [
    game.cover_url || game.image_url,
    ...game.screenshots,
  ].filter(Boolean) as string[]

  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null)

  useEffect(() => {
    if (lightboxIndex === null) return
    setNaturalSize(null)
    document.body.style.overflow = 'hidden'
    const count = images.length
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setLightboxIndex(null)
      else if (e.key === 'ArrowRight') setLightboxIndex((p) => p === null ? null : (p + 1) % count)
      else if (e.key === 'ArrowLeft')  setLightboxIndex((p) => p === null ? null : (p - 1 + count) % count)
    }
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = ''; window.removeEventListener('keydown', onKey) }
  }, [lightboxIndex, images.length])

  useEffect(() => {
    if (lightboxIndex === null) return
    const img = new Image()
    img.onload = () => setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
    img.src = images[lightboxIndex]
  }, [images, lightboxIndex])

  if (images.length === 0) return null

  const [first, ...rest] = images
  const lightbox = lightboxIndex !== null
    ? createPortal(
        <div className="dp-lightbox" role="dialog" aria-modal="true">
          <button
            type="button"
            className="dp-lightbox-backdrop"
            aria-label="Close"
            onClick={() => setLightboxIndex(null)}
          />
          <div className="dp-lightbox-stage">
            <img
              src={images[lightboxIndex]}
              alt={`${game.title} ${lightboxIndex === 0 ? 'cover' : `screenshot ${lightboxIndex}`}`}
              className="dp-lightbox-img"
              style={naturalSize ? {
                '--natural-width': `${naturalSize.width}px`,
                '--natural-height': `${naturalSize.height}px`,
              } as CSSProperties : undefined}
            />
          </div>
          <button type="button" className="dp-lightbox-close" onClick={() => setLightboxIndex(null)}>✕</button>
          {images.length > 1 && (
            <>
              <button
                type="button"
                className="dp-lightbox-nav dp-lightbox-prev"
                onClick={() => setLightboxIndex((lightboxIndex - 1 + images.length) % images.length)}
                aria-label="Previous image"
              >‹</button>
              <button
                type="button"
                className="dp-lightbox-nav dp-lightbox-next"
                onClick={() => setLightboxIndex((lightboxIndex + 1) % images.length)}
                aria-label="Next image"
              >›</button>
            </>
          )}
          <div className="dp-lightbox-counter">{lightboxIndex + 1} / {images.length}</div>
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <div className="dp-gallery">
        <div className="dp-gallery-main" onClick={() => setLightboxIndex(0)}>
          <img
            src={first}
            alt={`${game.title} cover`}
            className="dp-gallery-hero"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
          <div className="dp-gallery-zoom-hint">🔍</div>
        </div>
        {rest.length > 0 && (
          <div className="dp-gallery-rest">
            {rest.map((url, i) => (
              <div key={url} className="dp-gallery-img" onClick={() => setLightboxIndex(i + 1)}>
                <img
                  src={url}
                  alt={`${game.title} screenshot ${i + 2}`}
                  onError={(e) => { e.currentTarget.parentElement!.style.display = 'none' }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {lightbox}
    </>
  )
}

export function GameDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<Game | null>(null)
  const [similarCatalogGames, setSimilarCatalogGames] = useState<Game[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isFetchingScreenshots, setIsFetchingScreenshots] = useState(false)
  const [ratingsTab, setRatingsTab] = useState<'primary' | 'extra'>('primary')
  const [trailerOpen, setTrailerOpen] = useState(false)
  const [trailerVideoId, setTrailerVideoId] = useState<string | null>(null)
  const [trailerLoading, setTrailerLoading] = useState(false)

  useEffect(() => {
    if (!slug) return
    setGame(null)
    setSimilarCatalogGames([])
    setError(null)
    getGameBySlug(slug)
      .then((loaded) => {
        setGame(loaded)
        // Auto-refresh scores in the background on every page load
        refreshGameScores(loaded.slug)
          .then(setGame)
          .catch(() => { /* refresh failed silently — stale data still shown */ })
        // Auto-fetch screenshots from Steam if not yet stored
        if (loaded.screenshots.length === 0) {
          fetchGameScreenshots(loaded.slug)
            .then(setGame)
            .catch(() => { /* no Steam ID — gallery shows cover only */ })
        }
        if ((loaded.price_snapshots?.length ?? 0) === 0) {
          fetchGamePrices(loaded.slug)
            .then(setGame)
            .catch(() => { /* pricing is optional */ })
        }
      })
      .catch(() => setError('Game not found.'))
  }, [slug])

  useEffect(() => {
    if (!game) return
    const genre = game.genres.find((item) => !['Steam', 'PC', 'Mac', 'Linux'].includes(item)) ?? game.genres[0] ?? ''
    if (!genre) return

    const filters = {
      ...SIMILAR_DEFAULT_FILTERS,
      genre,
      sort: 'rank_score',
      direction: 'desc',
    } satisfies GameFilters

    let active = true
    getGames(filters, 18, 0)
      .then((response) => {
        if (!active) return
        setSimilarCatalogGames(
          response.games
            .filter((item) => item.slug !== game.slug)
            .slice(0, 12),
        )
      })
      .catch(() => {
        if (active) setSimilarCatalogGames([])
      })
    return () => { active = false }
  }, [game])

  const handleFetchScreenshots = async () => {
    if (!game) return
    setIsFetchingScreenshots(true)
    try { setGame(await fetchGameScreenshots(game.slug)) }
    catch { /* no Steam ID or network error */ }
    finally { setIsFetchingScreenshots(false) }
  }

  const handleTrailer = async () => {
    if (!game) return
    setTrailerOpen(true)
    setTrailerLoading(true)
    try { setTrailerVideoId((await getGameTrailer(game.slug)).video_id) }
    finally { setTrailerLoading(false) }
  }

  if (error) return (
    <div className="dp-shell">
      <div className="dp-inner">
        <button type="button" className="dp-back" onClick={() => navigate(-1)}>← Back</button>
        <p className="dp-msg">{error}</p>
      </div>
    </div>
  )

  if (!game) return (
    <div className="dp-shell">
      <p className="dp-msg">Loading…</p>
    </div>
  )

  const bgImage = game.cover_url || game.image_url || ''

  const scoreBySource = new Map(game.source_scores.map((s) => [s.source, s]))

  // Live primary 4 scores in priority order
  const livePrimary4: SourceScore[] = PRIMARY_4
    .map((src) => scoreBySource.get(src))
    .filter((s): s is SourceScore => s !== undefined && s.status === 'live' && s.score > 0)

  // Live extra scores
  const liveExtra: SourceScore[] = EXTRA_SOURCES
    .map((src) => scoreBySource.get(src))
    .filter((s): s is SourceScore => s !== undefined && s.status === 'live' && s.score > 0)

  // Fill missing primary slots with best extra sources
  const fillerCount = Math.max(0, 4 - livePrimary4.length)
  const fillerScores = liveExtra.slice(0, fillerCount)
  const fillerNames = new Set(fillerScores.map((s) => s.source))

  // Primary tab = top 4 + fillers; Extra tab = remaining extras
  const primaryTabScores = [...livePrimary4, ...fillerScores]
  const extraTabScores = liveExtra.filter((s) => !fillerNames.has(s.source))

  // Source average is shown as context; GameMetrix Score itself is adjusted by backend reliability.
  const sourceAverage = primaryTabScores.length > 0
    ? Math.round(primaryTabScores.reduce((sum, s) => sum + s.score, 0) / primaryTabScores.length)
    : Math.round(game.metrix_score)
  const displayScore = Math.round(game.metrix_score)

  const totalReviews = primaryTabScores.reduce((n, s) => n + (s.review_count ?? 0), 0)
  const confidenceLower = (game.confidence_level ?? 'limited').toLowerCase()
  const livePrimaryCount = game.live_primary_source_count ?? livePrimary4.length
  const applicableCount = game.applicable_source_count ?? 4
  const rawgFillsSlot = fillerScores.some((s) => s.source === 'RAWG')
  const coverageLabel = rawgFillsSlot
    ? `${livePrimaryCount}/${applicableCount} + RAWG`
    : `${livePrimaryCount}/${applicableCount}`
  const popularity = popularitySummary(game)
  const rankStatus = game.is_rankable ? 'Ranked' : 'Unranked'
  const rankDetail = game.is_rankable
    ? 'Eligible for leaderboard ranking.'
    : game.rank_exclusion_reason === 'catalog_only'
      ? 'Waiting for live rating data.'
      : 'Needs more reliable source coverage.'

  const releaseLabel = game.release_year > 1970
    ? new Date(game.release_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : 'Unknown'
  const earlyAccessLabel = formatDate(game.early_access_date)
  const officialReleaseLabel = formatDate(game.official_release_date ?? game.release_date)
  const aboutParagraphs = buildAboutParagraphs(game)
  const priceSnapshots = game.price_snapshots ?? []
  const detailStyle = {
    '--score-color': scoreColor(displayScore),
    '--score-rgb': scoreColorRgb(displayScore),
  } as CSSProperties

  return (
    <div className="dp-shell" style={detailStyle}>
      {/* Blurred background */}
      {bgImage && (
        <div className="dp-bg" style={{ backgroundImage: `url("${bgImage}")` }} />
      )}
      <div className="dp-bg-overlay" />

      <div className="dp-inner">
        {/* Breadcrumb */}
        <nav className="dp-breadcrumb">
          <button type="button" className="dp-bc-item dp-bc-link" onClick={() => navigate(-1)}>Home</button>
          <span className="dp-bc-sep">/</span>
          <span className="dp-bc-item dp-bc-link" onClick={() => navigate(-1)} role="button" tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && navigate(-1)}>Games</span>
          <span className="dp-bc-sep">/</span>
          <span className="dp-bc-item dp-bc-current">{game.title}</span>
        </nav>

        {/* Main two-column grid */}
        <div className="dp-grid">
          {/* ── LEFT ── */}
          <div className="dp-left">
            {/* Date */}
            <div className="dp-header-meta">
              <span className="dp-release-chip">{releaseLabel}</span>
            </div>

            <h1 className="dp-title">{game.title}</h1>

            {game.developer && (
              <p className="dp-subtitle">{game.developer}{game.publisher && game.publisher !== game.developer ? ` · ${game.publisher}` : ''}</p>
            )}

            {game.platforms.length > 0 && (
              <div className="dp-platform-strip">
                <PlatformIcons platforms={game.platforms} mode="detail" maxVisible={6} />
              </div>
            )}

            {/* Action buttons */}
            <div className="dp-actions">
              <button type="button" className="dp-btn dp-btn-primary" onClick={handleTrailer}>
                ▶ Trailer
              </button>
              {game.screenshots.length === 0 && (
                <button
                  type="button"
                  className={`dp-btn${isFetchingScreenshots ? ' dp-btn-loading' : ''}`}
                  onClick={handleFetchScreenshots}
                  disabled={isFetchingScreenshots}
                >
                  🖼 {isFetchingScreenshots ? 'Fetching…' : 'Get Screenshots'}
                </button>
              )}
            </div>

            {/* Score block */}
            <div className="dp-score-block">
              <div className="dp-score-main">
                <div className="dp-score-ring-wrap">
                  <ScoreRing score={displayScore} size="lg" />
                </div>
                <div className="dp-score-meta">
                  <span
                    className={`dp-confidence dp-confidence-${confidenceLower}`}
                  >
                    {game.confidence_level}
                  </span>
                  <span className="dp-score-label">GameMetrix Score</span>
                  {totalReviews > 0 && (
                    <span className="dp-total-reviews">{totalReviews.toLocaleString()} total reviews</span>
                  )}
                </div>
              </div>
              <div className="dp-score-stats">
                <div>
                  <span>Source avg</span>
                  <strong>{sourceAverage}</strong>
                </div>
                <div>
                  <span>Coverage</span>
                  <strong>{coverageLabel}</strong>
                </div>
                <div>
                  <span>Rank score</span>
                  <strong>{Math.round(game.rank_score)}</strong>
                </div>
              </div>
            </div>

            <div className="dp-signal-grid">
              <div className={`dp-signal-card dp-signal-${confidenceLower}`}>
                <span>Data reliability</span>
                <strong>{game.confidence_level}</strong>
                <small>{reliabilityCopy(game, livePrimaryCount, rawgFillsSlot)}</small>
              </div>
              <div className="dp-signal-card">
                <span>Popularity</span>
                <strong>{popularity.label}</strong>
                <small>{popularity.detail}</small>
              </div>
              <div className={game.is_rankable ? 'dp-signal-card' : 'dp-signal-card dp-signal-muted'}>
                <span>Ranking</span>
                <strong>{rankStatus}</strong>
                <small>{rankDetail}</small>
              </div>
            </div>

            {/* Ratings with tabs */}
            {(primaryTabScores.length > 0 || extraTabScores.length > 0) && (
              <div className="dp-section">
                <div className="dp-ratings-tabs">
                  <button
                    type="button"
                    className={`dp-rtab${ratingsTab === 'primary' ? ' dp-rtab-active' : ''}`}
                    onClick={() => setRatingsTab('primary')}
                  >
                    Ratings
                  </button>
                  {extraTabScores.length > 0 && (
                    <button
                      type="button"
                      className={`dp-rtab${ratingsTab === 'extra' ? ' dp-rtab-active' : ''}`}
                      onClick={() => setRatingsTab('extra')}
                    >
                      Other Sources
                    </button>
                  )}
                </div>
                <div className="dp-src-list">
                  {ratingsTab === 'primary'
                    ? primaryTabScores.map((s) => (
                        <SourceRow
                          key={s.source}
                          s={s}
                          game={game}
                          filler={fillerNames.has(s.source)}
                        />
                      ))
                    : extraTabScores.map((s) => (
                        <SourceRow key={s.source} s={s} game={game} />
                      ))
                  }
                  {ratingsTab === 'primary' && primaryTabScores.length === 0 && (
                    <p className="dp-no-scores">No live scores yet.</p>
                  )}
                </div>
              </div>
            )}

            {/* About */}
            <div className="dp-section">
              <h3 className="dp-section-title">About</h3>
              <div className="dp-description">
                {aboutParagraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
            </div>

            {/* Info table */}
            <div className="dp-section">
              <div className="dp-info-table">
                {game.platforms.length > 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Platforms</span>
                    <span className="dp-info-val">{game.platforms.join(', ')}</span>
                  </div>
                )}
                {game.genres.length > 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Genre</span>
                    <span className="dp-info-val">{game.genres.join(', ')}</span>
                  </div>
                )}
                <div className="dp-info-row">
                  <span className="dp-info-key">Release date</span>
                  <span className="dp-info-val">{releaseLabel}</span>
                </div>
                <div className="dp-info-row">
                  <span className="dp-info-key">Early release</span>
                  <span className="dp-info-val">{earlyAccessLabel}</span>
                </div>
                <div className="dp-info-row">
                  <span className="dp-info-key">Official release</span>
                  <span className="dp-info-val">{officialReleaseLabel}</span>
                </div>
                {game.developer && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Developer</span>
                    <span className="dp-info-val">{game.developer}</span>
                  </div>
                )}
                {game.publisher && game.publisher !== game.developer && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Publisher</span>
                    <span className="dp-info-val">{game.publisher}</span>
                  </div>
                )}
                {game.goty_year && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">GOTY</span>
                    <span className="dp-info-val">{game.goty_year}</span>
                  </div>
                )}
                {game.playtime_minutes > 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Avg playtime</span>
                    <span className="dp-info-val">{Math.round(game.playtime_minutes / 60)}h</span>
                  </div>
                )}
                <div className="dp-info-row">
                  <span className="dp-info-key">Score profile</span>
                  <span className="dp-info-val">{game.score_profile}</span>
                </div>
                {game.popularity_label && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Popularity</span>
                    <span className="dp-info-val">{game.popularity_label} · {popularity.detail}</span>
                  </div>
                )}
              </div>
            </div>

            {priceSnapshots.length > 0 && (
              <div className="dp-section">
                <h3 className="dp-section-title">Price & availability</h3>
                <PricePanel prices={priceSnapshots} />
              </div>
            )}

            {/* System requirements */}
            {game.system_requirements.length > 0 && (
              <div className="dp-section">
                {game.system_requirements.map((req) => (
                  <div key={req.platform}>
                    <h3 className="dp-section-title">System requirements for {req.platform}</h3>
                    <SysReqBlock req={req} />
                  </div>
                ))}
              </div>
            )}

          </div>

          {/* ── RIGHT ── */}
          <div className="dp-right">
            <div className="dp-gallery-panel">
              <div className="dp-gallery-heading">
                <span>Media</span>
                <strong>{Math.max(1, game.screenshots.length + 1)} images</strong>
              </div>
              <Gallery game={game} />
            </div>
          </div>
        </div>

        {(game.dlcs.length > 0 || game.similar_games.length > 0 || similarCatalogGames.length > 0) && (
          <div className="dp-bottom-related">
            <DlcSection game={game} />
            <SimilarGamesSection game={game} catalogGames={similarCatalogGames} />
          </div>
        )}
      </div>

      {/* Trailer modal */}
      {trailerOpen && (
        <div className="dp-modal" role="dialog" aria-modal="true">
          <button
            type="button"
            className="dp-modal-backdrop"
            aria-label="Close trailer"
            onClick={() => { setTrailerOpen(false); setTrailerVideoId(null) }}
          />
          <div className="dp-modal-panel">
            <button
              type="button"
              className="dp-modal-close"
              onClick={() => { setTrailerOpen(false); setTrailerVideoId(null) }}
            >✕</button>
            {trailerLoading ? (
              <div className="dp-modal-msg">Loading trailer…</div>
            ) : trailerVideoId ? (
              <iframe
                title={`${game.title} trailer`}
                src={`https://www.youtube-nocookie.com/embed/${trailerVideoId}?autoplay=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <a
                className="dp-modal-msg"
                href={`https://www.youtube.com/results?search_query=${encodeURIComponent(game.title + ' official trailer game')}`}
                target="_blank"
                rel="noreferrer"
              >
                Open trailer search on YouTube
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
