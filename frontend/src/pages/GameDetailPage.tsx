/* eslint-disable react-hooks/set-state-in-effect */
import { type CSSProperties, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import {
  fetchGamePrices,
  fetchGameScreenshots,
  fetchGameSystemRequirements,
  getGameBySlug,
  getGameTrailer,
  getSimilarGames,
  refreshGameScores,
} from '../services/games'
import { ScoreRing } from '../components/ScoreRing'
import { PlatformIcons } from '../components/PlatformIcons'
import { TrailerModal } from '../components/TrailerModal'
import { scoreColor, scoreColorRgb, sourceScoreColor } from '../utils/scoreColors'
import { steamAppIdFromGame } from '../utils/steam'
import { safeExternalUrl } from '../utils/url'
import { PROTON_TIER_LABELS, isProtonTier } from '../utils/proton'
import type { Game, PriceSnapshot, SourceScore } from '../types/game'
import { DlcSection } from './detail/DlcSection'
import { Gallery } from './detail/Gallery'
import { PricePanel } from './detail/PricePanel'
import { ProtonCompat } from './detail/ProtonCompat'
import { SimilarGamesSection, SIMILAR_DISPLAY_LIMIT } from './detail/SimilarGamesSection'
import { SeriesRow } from '../components/SeriesRow'
import { SysReqBlock } from './detail/SysReqBlock'
import { formatCompactCount, formatDate } from './detail/format'
import './GameDetailPage.css'

// The 4 core quality sources shown in the main rating block
const PRIMARY_4 = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB'] as const
// Extra sources shown in the secondary tab
const EXTRA_SOURCES = ['RAWG', 'SteamSpy', 'CheapShark', 'FreeToGame'] as const
const RATING_SOURCES = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB', 'RAWG'] as const
const SCORE_REFRESH_MAX_AGE_MS = 12 * 60 * 60 * 1000
const PRICE_REFRESH_MAX_AGE_MS = 12 * 60 * 60 * 1000
// Mirrors the backend's _BAD_SYSTEM_REQUIREMENT_MARKERS heuristic
const BAD_SYSTEM_REQUIREMENT_MARKERS = ['windows xp', '1.2ghz', '256mb', '250 mb']

function isOlderThan(value: string | null | undefined, maxAgeMs: number) {
  if (!value) return true
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) || Date.now() - timestamp > maxAgeMs
}

function mergeGameSnapshot(current: Game, incoming: Game): Game {
  return {
    ...current,
    ...incoming,
    screenshots: incoming.screenshots.length > 0 ? incoming.screenshots : current.screenshots,
    system_requirements: incoming.system_requirements.length > 0 ? incoming.system_requirements : current.system_requirements,
    dlcs: incoming.dlcs.length > 0 ? incoming.dlcs : current.dlcs,
    similar_games: incoming.similar_games.length > 0 ? incoming.similar_games : current.similar_games,
    price_snapshots: (incoming.price_snapshots?.length ?? 0) > 0 ? incoming.price_snapshots : current.price_snapshots,
  }
}

function sourceExternalUrl(source: string, game: Game): string | null {
  const q = encodeURIComponent(game.title)
  const steamAppId = steamAppIdFromGame(game)
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

function websiteLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'Official site'
  }
}

function formatHours(minutes: number): string {
  return `${Math.max(1, Math.round(minutes / 60))}h`
}

function protonLabel(game: Game): string | null {
  const tier = game.proton_tier
  return tier && isProtonTier(tier) ? PROTON_TIER_LABELS[tier] : null
}

function shouldFetchPrices(prices: PriceSnapshot[] | undefined): boolean {
  const snapshots = prices ?? []
  if (snapshots.length === 0) return true
  if (snapshots.some((price) => price.store.startsWith('Store '))) return true
  if (!snapshots.some((price) => price.is_free || price.sale_price !== null || price.list_price !== null)) return true
  return snapshots.every((price) => isOlderThan(price.fetched_at, PRICE_REFRESH_MAX_AGE_MS))
}

function shouldFetchSystemRequirements(game: Game): boolean {
  if (!steamAppIdFromGame(game)) return false
  const requirements = game.system_requirements ?? []
  if (requirements.length === 0) return true
  const text = requirements
    .map((req) => `${req.platform} ${req.minimum} ${req.recommended}`)
    .join(' ')
    .toLowerCase()
  return BAD_SYSTEM_REQUIREMENT_MARKERS.some((marker) => text.includes(marker))
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

export function GameDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<Game | null>(null)
  const [similarCatalogGames, setSimilarCatalogGames] = useState<Game[]>([])
  const [similarLoading, setSimilarLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isFetchingScreenshots, setIsFetchingScreenshots] = useState(false)
  const [ratingsTab, setRatingsTab] = useState<'primary' | 'extra'>('primary')
  const [trailerOpen, setTrailerOpen] = useState(false)
  const [trailerVideoId, setTrailerVideoId] = useState<string | null>(null)
  const [trailerLoading, setTrailerLoading] = useState(false)

  useEffect(() => {
    if (!slug) return
    const previousBehavior = document.documentElement.style.scrollBehavior
    document.documentElement.style.scrollBehavior = 'auto'
    window.scrollTo(0, 0)
    document.documentElement.style.scrollBehavior = previousBehavior
  }, [slug])

  useEffect(() => {
    if (!game) return
    const previousTitle = document.title
    document.title = `${game.title} — GameMetrix`
    return () => { document.title = previousTitle }
  }, [game])

  useEffect(() => {
    if (!slug) return
    let active = true
    const timers: number[] = []
    const schedule = (callback: () => void, delay: number) => {
      const timer = window.setTimeout(() => {
        if (active) callback()
      }, delay)
      timers.push(timer)
    }
    const updateGame = (incoming: Game) => {
      if (!active) return
      setGame((current) => {
        if (!current || current.slug !== incoming.slug) return incoming
        return mergeGameSnapshot(current, incoming)
      })
    }

    setGame(null)
    setSimilarCatalogGames([])
    setError(null)
    getGameBySlug(slug)
      .then((loaded) => {
        if (!active) return
        setGame(loaded)
        if (isOlderThan(loaded.ratings_refreshed_at, SCORE_REFRESH_MAX_AGE_MS)) {
          schedule(() => {
            refreshGameScores(loaded.slug)
              .then(updateGame)
              .catch(() => { /* refresh failed silently — stale data still shown */ })
          }, 350)
        }
        if (loaded.screenshots.length === 0) {
          schedule(() => {
            fetchGameScreenshots(loaded.slug)
              .then(updateGame)
              .catch(() => { /* no Steam ID — gallery shows cover only */ })
          }, 700)
        }
        if (shouldFetchSystemRequirements(loaded)) {
          schedule(() => {
            fetchGameSystemRequirements(loaded.slug)
              .then(updateGame)
              .catch(() => { /* no Steam requirements — keep existing metadata */ })
          }, 900)
        }
        if (shouldFetchPrices(loaded.price_snapshots)) {
          schedule(() => {
            fetchGamePrices(loaded.slug)
              .then(updateGame)
              .catch(() => { /* pricing is optional */ })
          }, 1100)
        }
      })
      .catch(() => {
        if (active) setError('Game not found.')
      })
    return () => {
      active = false
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [slug])

  useEffect(() => {
    if (!slug) return
    let active = true
    setSimilarLoading(true)
    getSimilarGames(slug, SIMILAR_DISPLAY_LIMIT)
      .then((response) => {
        if (active) setSimilarCatalogGames(response.games)
      })
      .catch(() => {
        if (active) setSimilarCatalogGames([])
      })
      .finally(() => {
        if (active) setSimilarLoading(false)
      })
    return () => { active = false }
  }, [slug])

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
    catch { setTrailerVideoId(null) }
    finally { setTrailerLoading(false) }
  }

  // navigate(-1) on a fresh tab (deep link) would leave the site or do
  // nothing — fall back to the catalog root in that case. The catalog
  // restores its own state from the session snapshot either way.
  const goBackToCatalog = () => {
    if (window.history.length > 1) navigate(-1)
    else navigate('/')
  }

  if (error) return (
    <div className="dp-shell">
      <div className="dp-inner">
        <button type="button" className="dp-back" onClick={goBackToCatalog}>← Back</button>
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
  const websiteUrl = safeExternalUrl(game.website_url)
  const steamAppId = steamAppIdFromGame(game)
  const protonText = protonLabel(game)
  const protonUrl = steamAppId ? `https://www.protondb.com/app/${steamAppId}` : 'https://www.protondb.com/'
  const hltbUrl = safeExternalUrl(game.hltb_url)
  const hltbRows = [
    ['HLTB main', game.hltb_main_story_minutes || (game.hltb_id ? game.playtime_minutes : 0)],
    ['HLTB extra', game.hltb_main_extra_minutes],
    ['HLTB 100%', game.hltb_completionist_minutes],
    ['HLTB avg', game.hltb_all_styles_minutes],
  ].filter(([, minutes]) => Number(minutes) > 0)
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
          <button type="button" className="dp-bc-item dp-bc-link" onClick={goBackToCatalog}>Home</button>
          <span className="dp-bc-sep">/</span>
          <button type="button" className="dp-bc-item dp-bc-link" onClick={goBackToCatalog}>Games</button>
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
                <PlatformIcons platforms={game.platforms} mode="detail" maxVisible={6} game={game} />
              </div>
            )}

            {/* Action buttons */}
            <div className="dp-actions">
              <button type="button" className="dp-btn dp-btn-primary" onClick={handleTrailer}>
                ▶ Trailer
              </button>
              {websiteUrl ? (
                <a className="dp-btn dp-btn-link" href={websiteUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink size={14} aria-hidden="true" />
                  Official site
                </a>
              ) : null}
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
                {websiteUrl ? (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Website</span>
                    <span className="dp-info-val">
                      <a className="dp-info-link" href={websiteUrl} target="_blank" rel="noopener noreferrer">
                        {websiteLabel(websiteUrl)}
                        <ExternalLink size={11} aria-hidden="true" />
                      </a>
                    </span>
                  </div>
                ) : null}
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
                {game.playtime_minutes > 0 && hltbRows.length === 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Avg playtime</span>
                    <span className="dp-info-val">{formatHours(game.playtime_minutes)}</span>
                  </div>
                )}
                {hltbRows.map(([label, minutes], index) => (
                  <div className="dp-info-row" key={label}>
                    <span className="dp-info-key">{label}</span>
                    <span className="dp-info-val">
                      {index === 0 && hltbUrl ? (
                        <a className="dp-info-link" href={hltbUrl} target="_blank" rel="noopener noreferrer">
                          {formatHours(Number(minutes))}
                          <ExternalLink size={11} aria-hidden="true" />
                        </a>
                      ) : (
                        formatHours(Number(minutes))
                      )}
                    </span>
                  </div>
                ))}
                {protonText && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">ProtonDB</span>
                    <span className="dp-info-val">
                      <a
                        className={`dp-info-link dp-proton-tier dp-proton-${game.proton_tier ?? 'unknown'}`}
                        href={protonUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {protonText}
                        <ExternalLink size={11} aria-hidden="true" />
                      </a>
                    </span>
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

            {game.proton_tier && (
              <div className="dp-section">
                <h3 className="dp-section-title">Linux / Steam Deck compatibility</h3>
                <ProtonCompat game={game} />
              </div>
            )}

            {priceSnapshots.length > 0 && (
              <div className="dp-section">
                <h3 className="dp-section-title">Price & availability</h3>
                <PricePanel prices={priceSnapshots} game={game} />
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
              <Gallery game={game} />
            </div>
          </div>
        </div>

        <SeriesRow slug={game.slug} />

        {(game.dlcs.length > 0 || game.similar_games.length > 0 || similarCatalogGames.length > 0 || similarLoading) && (
          <div className="dp-bottom-related">
            <DlcSection game={game} />
            <SimilarGamesSection game={game} catalogGames={similarCatalogGames} loading={similarLoading} />
          </div>
        )}
      </div>

      {/* Trailer modal */}
      {trailerOpen && (
        <TrailerModal
          title={game.title}
          videoId={trailerVideoId}
          loading={trailerLoading}
          onClose={() => { setTrailerOpen(false); setTrailerVideoId(null) }}
        />
      )}
    </div>
  )
}
