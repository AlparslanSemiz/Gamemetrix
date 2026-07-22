/* eslint-disable react-hooks/set-state-in-effect */
import { type CSSProperties, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Clock3, ExternalLink, Info } from 'lucide-react'
import {
  getGameBySlug,
  getGameTrailer,
  getSimilarGames,
} from '../services/games'
import { ScoreRing } from '../components/ScoreRing'
import { PlatformIcons } from '../components/PlatformIcons'
import { TrailerModal } from '../components/TrailerModal'
import { scoreColor, scoreColorRgb, sourceScoreColor } from '../utils/scoreColors'
import { steamAppIdFromGame } from '../utils/steam'
import { safeExternalUrl } from '../utils/url'
import { PROTON_TIER_LABELS, formatProtonScore, isProtonTier } from '../utils/proton'
import { currentPriceSnapshots } from '../utils/prices'
import { bestCoverUrl } from '../utils/coverImage'
import { isEndlessGame } from '../utils/playtime'
import type { Game, SourceScore } from '../types/game'
import { CollectionActions } from './detail/CollectionActions'
import { DlcSection } from './detail/DlcSection'
import { Gallery } from './detail/Gallery'
import { PricePanel } from './detail/PricePanel'
import { SimilarGamesSection, SIMILAR_DISPLAY_LIMIT } from './detail/SimilarGamesSection'
import { SeriesRow } from '../components/SeriesRow'
import { SysReqBlock } from './detail/SysReqBlock'
import { formatCompactCount, formatCount, formatDate } from './detail/format'
import './GameDetailPage.css'

// The 4 core quality sources shown in the main rating block
const PRIMARY_4 = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB'] as const
// Extra sources shown in the secondary tab
const EXTRA_SOURCES = ['RAWG', 'SteamSpy', 'CheapShark', 'FreeToGame'] as const
const RATING_SOURCES = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB', 'RAWG'] as const

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

function SourceRow({ s, game, secondary = false }: { s: SourceScore; game: Game; secondary?: boolean }) {
  const url = sourceExternalUrl(s.source, game)
  const pct = Math.max(0, Math.min(s.score, 100))
  const unavailable = s.status !== 'live' || s.score <= 0
  const isPrimary = !secondary && (PRIMARY_4 as readonly string[]).includes(s.source)
  const nameEl = url ? (
    <a href={url} target="_blank" rel="noopener noreferrer" className={`dp-src-name dp-src-link${secondary ? ' dp-src-secondary' : ''}`}>
      {s.source} <ExternalLink size={9} />
    </a>
  ) : (
    <span className={`dp-src-name${isPrimary ? '' : ' dp-src-secondary'}`}>{s.source}</span>
  )
  return (
    <div
      className={`dp-src-row${secondary ? ' dp-src-row-secondary' : ''}${unavailable ? ' dp-src-row-unavailable' : ''}`}
      title={s.detail ?? s.source}
      style={{ '--source-color': sourceScoreColor(pct) } as CSSProperties}
    >
      {nameEl}
      <div className="dp-src-bar"><span className="dp-src-fill" style={{ width: unavailable ? '0%' : `${pct}%` }} /></div>
      <strong className="dp-src-score">{unavailable ? '—' : Math.round(s.score)}</strong>
      {s.review_count ? (
        <span className="dp-src-count">{formatCount(s.review_count)}</span>
      ) : null}
    </div>
  )
}

function reliabilityCopy(game: Game, livePrimaryCount: number) {
  const applicableCount = game.applicable_source_count ?? 4
  const missing = Math.max(0, applicableCount - livePrimaryCount)
  if (game.confidence_level === 'Strong') {
    return `${livePrimaryCount}/${applicableCount} primary sources, critic and player signal covered.`
  }
  if (game.confidence_level === 'Solid') {
    return `${livePrimaryCount}/${applicableCount} primary sources. Good signal, still missing ${missing}.`
  }
  if (game.confidence_level === 'Limited') {
    return `${livePrimaryCount}/${applicableCount} primary sources. Score is uncertainty-adjusted.`
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

// Popularity tiers mirror the backend thresholds in models.py (total reviews
// across rating sources). Highest tier first for the hover legend.
const POPULARITY_TIERS: { label: string; threshold: string; color: string }[] = [
  { label: 'Phenomenon', threshold: '500K+ reviews', color: '#f472b6' },
  { label: 'Very High', threshold: '100K+ reviews', color: '#c084fc' },
  { label: 'High', threshold: '25K+ reviews', color: '#60a5fa' },
  { label: 'Medium', threshold: '5K+ reviews', color: '#4ade80' },
  { label: 'Niche', threshold: '500+ reviews', color: '#e0b341' },
]

function popularityColor(label: string | null | undefined): string {
  return POPULARITY_TIERS.find((tier) => tier.label === label)?.color ?? '#9ca3af'
}

// Catalog deep links: land on the homepage filtered by developer / publisher / genre / year.
function catalogFilterHref(param: 'developer' | 'publisher' | 'genre' | 'year', value: string | number): string {
  return `/?${param}=${encodeURIComponent(String(value))}`
}

// Renders a release date string with only its year as a catalog link.
function ReleaseValue({ label, year }: { label: string; year: number }) {
  const yearStr = String(year)
  const idx = year > 1970 ? label.indexOf(yearStr) : -1
  if (idx === -1) return <>{label}</>
  return (
    <>
      {label.slice(0, idx)}
      <Link className="dp-info-link" to={catalogFilterHref('year', year)}>{yearStr}</Link>
      {label.slice(idx + yearStr.length)}
    </>
  )
}

function formatGameMode(mode: string): string {
  return mode.charAt(0).toUpperCase() + mode.slice(1)
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
  if (!tier || !isProtonTier(tier)) return null
  const scoreText = formatProtonScore(game.proton_score)
  return scoreText ? `${PROTON_TIER_LABELS[tier]} · ${scoreText}` : PROTON_TIER_LABELS[tier]
}

// The real game description, split into paragraphs. The metadata already lives in
// the info table, so About stays the summary only — no auto-generated recap text.
function buildAboutParagraphs(game: Game): string[] {
  const summary = (game.summary ?? '').trim()
  if (!summary) return []
  return summary
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
}

export function GameDetailPage({ initialGame }: { initialGame?: Game }) {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<Game | null>(initialGame ?? null)
  const [similarCatalogGames, setSimilarCatalogGames] = useState<Game[]>([])
  const [similarLoading, setSimilarLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
    if (!slug) return
    let active = true

    if (initialGame?.slug === slug) {
      setGame(initialGame)
      setError(null)
      return
    }

    setGame(null)
    setSimilarCatalogGames([])
    setError(null)
    getGameBySlug(slug)
      .then((loaded) => {
        if (!active) return
        setGame(loaded)
      })
      .catch(() => {
        if (active) setError('Game not found.')
      })
    return () => {
      active = false
    }
  }, [initialGame, slug])

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

  const bgImage = bestCoverUrl(game)

  const scoreBySource = new Map(game.source_scores.map((s) => [s.source, s]))

  // Live primary 4 scores in priority order
  const livePrimary4: SourceScore[] = PRIMARY_4
    .map((src) => scoreBySource.get(src))
    .filter((s): s is SourceScore => s !== undefined && s.status === 'live' && s.score > 0)

  // Live extra scores
  const liveExtra: SourceScore[] = EXTRA_SOURCES
    .map((src) => scoreBySource.get(src))
    .filter((s): s is SourceScore => s !== undefined && s.status === 'live' && s.score > 0)

  const primaryTabScores: SourceScore[] = PRIMARY_4.map((source) => {
    const score = scoreBySource.get(source)
    return score?.status === 'live' && score.score > 0
      ? score
      : { source, score: 0, scale: 100, status: 'unavailable', detail: 'No live score has been collected yet.' }
  })
  const extraTabScores = liveExtra

  // Source average is shown as context; GameMetrix Score itself is adjusted by backend reliability.
  const sourceAverage = livePrimary4.length > 0
    ? Math.round(livePrimary4.reduce((sum, s) => sum + s.score, 0) / livePrimary4.length)
    : Math.round(game.metrix_score)
  const displayScore = Math.round(game.metrix_score)

  const totalReviews = livePrimary4.reduce((n, s) => n + (s.review_count ?? 0), 0)
  const confidenceLower = (game.confidence_level ?? 'limited').toLowerCase()
  const livePrimaryCount = game.live_primary_source_count ?? livePrimary4.length
  const applicableCount = game.applicable_source_count ?? 4
  const coverageLabel = `${livePrimaryCount}/${applicableCount}`
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
  const primaryReleaseLabel = officialReleaseLabel !== 'Not tracked' ? officialReleaseLabel : releaseLabel
  const earlyAccessSuffix = earlyAccessLabel !== 'Not tracked' && earlyAccessLabel !== primaryReleaseLabel
    ? ` · Early access ${earlyAccessLabel}`
    : ''
  const websiteUrl = safeExternalUrl(game.website_url)
  const steamAppId = steamAppIdFromGame(game)
  const protonText = protonLabel(game)
  const protonUrl = steamAppId ? `https://www.protondb.com/app/${steamAppId}` : 'https://www.protondb.com/'
  const hltbUrl = safeExternalUrl(game.hltb_url)
  const endless = isEndlessGame(game)
  const hltbPrimaryMinutes = game.hltb_main_story_minutes
    || game.playtime_minutes
    || game.hltb_all_styles_minutes
    || game.hltb_completionist_minutes
    || game.hltb_main_extra_minutes
  const hltbDetail: [string, number][] = ([
    ['Extra', game.hltb_main_extra_minutes],
    ['100%', game.hltb_completionist_minutes],
    ['Avg', game.hltb_all_styles_minutes],
  ] as [string, number][]).filter(([, minutes]) => Number(minutes) > 0)
  const hasHltb = hltbPrimaryMinutes > 0 || hltbDetail.length > 0
  const aboutParagraphs = buildAboutParagraphs(game)
  const priceSnapshots = currentPriceSnapshots(game.price_snapshots ?? [])
  const gameModes = (game.game_modes ?? []).filter(Boolean)
  const detailStyle = {
    '--score-color': scoreColor(displayScore),
    '--score-rgb': scoreColorRgb(displayScore),
  } as CSSProperties

  return (
    <main className="dp-shell" style={detailStyle}>
      {/* Blurred background */}
      {bgImage && (
        <div className="dp-bg" style={{ backgroundImage: `url("${bgImage}")` }} />
      )}
      <div className="dp-bg-overlay" />

      <div className="dp-inner">
        {/* Breadcrumb */}
        {/* Real anchors, not buttons: a crawler follows these and they pass link
            equity, which the previous onClick-only version did neither of.
            Two levels only — "/" is the games catalog, so a separate "Games"
            crumb was the same URL twice. The catalog snapshot is restored from
            sessionStorage on mount, so a plain push keeps filters and scroll;
            no history-back handler is needed here. */}
        <nav className="dp-breadcrumb" aria-label="Breadcrumb">
          <Link to="/" className="dp-bc-item dp-bc-link">Home</Link>
          <span className="dp-bc-sep">/</span>
          <span className="dp-bc-item dp-bc-current" aria-current="page">{game.title}</span>
        </nav>

        {/* Main two-column grid */}
        <div className="dp-grid">
          {/* ── LEFT ── */}
          <div className="dp-left">
            {/* Release date · platforms · playtime — the whole "at a glance" line */}
            <div className="dp-header-meta">
              <span className="dp-release-chip">{releaseLabel}</span>
              {game.platforms.length > 0 && (
                <PlatformIcons platforms={game.platforms} mode="detail" maxVisible={6} game={game} />
              )}
              {(endless || hltbPrimaryMinutes > 0) && (
                <span className="dp-header-playtime">
                  <Clock3 size={12} aria-hidden="true" />
                  {endless ? '∞' : formatHours(hltbPrimaryMinutes)}
                </span>
              )}
            </div>

            <h1 className="dp-title">{game.title}</h1>

            {(game.developer || websiteUrl) && (
              <p className="dp-subtitle">
                {game.developer && (
                  <Link className="dp-subtitle-link" to={catalogFilterHref('developer', game.developer)}>{game.developer}</Link>
                )}
                {game.publisher && game.publisher !== game.developer ? ` · ${game.publisher}` : ''}
                {websiteUrl && (
                  <>
                    {game.developer || game.publisher ? ' · ' : ''}
                    <a className="dp-subtitle-link" href={websiteUrl} target="_blank" rel="noopener noreferrer">
                      {websiteLabel(websiteUrl)}
                      <ExternalLink size={11} aria-hidden="true" />
                    </a>
                  </>
                )}
              </p>
            )}

            <CollectionActions slug={game.slug} onOpenTrailer={handleTrailer} />

            {/* Score block */}
            <div className="dp-score-block">
              <div className="dp-score-main">
                <div className="dp-score-ring-wrap">
                  <ScoreRing score={displayScore} size="lg" />
                </div>
                <div className="dp-score-meta">
                  <span
                    className={`dp-confidence dp-confidence-${confidenceLower}`}
                    title={reliabilityCopy(game, livePrimaryCount)}
                  >
                    {game.confidence_level}
                  </span>
                  <span className="dp-score-label">GameMetrix Score</span>
                  {totalReviews > 0 && (
                    <span className="dp-total-reviews">{formatCount(totalReviews)} total reviews</span>
                  )}
                </div>
              </div>
              <div className="dp-score-stats">
                <div title="Plain average of the live primary source scores.">
                  <span>Source avg</span>
                  <strong>{sourceAverage}</strong>
                </div>
                <div title={reliabilityCopy(game, livePrimaryCount)}>
                  <span>Coverage</span>
                  <strong>{coverageLabel}</strong>
                </div>
                <div title="Score used for leaderboard ordering.">
                  <span>Rank score</span>
                  <strong>{Math.round(game.rank_score)}</strong>
                </div>
                <div title={popularity.detail}>
                  <span>Popularity</span>
                  <strong style={{ '--pop-color': popularityColor(popularity.label) } as CSSProperties} className="dp-stat-pop">
                    {popularity.label}
                    <button
                      type="button"
                      className="dp-hltb-info"
                      aria-label="Popularity tiers"
                      aria-describedby="game-popularity-tooltip"
                    >
                      <Info size={12} aria-hidden="true" />
                      <span id="game-popularity-tooltip" className="dp-hltb-tip" role="tooltip">
                        {POPULARITY_TIERS.map((tier) => (
                          <span className="dp-hltb-tip-row" key={tier.label}>
                            <span style={{ color: tier.color }}>{tier.label}</span>
                            <span>{tier.threshold}</span>
                          </span>
                        ))}
                      </span>
                    </button>
                  </strong>
                </div>
                <div className={game.is_rankable ? '' : 'dp-stat-muted'} title={rankDetail}>
                  <span>Ranking</span>
                  <strong>{rankStatus}</strong>
                </div>
              </div>
            </div>

            {/* Ratings with tabs */}
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
                        />
                      ))
                    : extraTabScores.map((s) => (
                        <SourceRow key={s.source} s={s} game={game} secondary />
                      ))
                  }
                </div>
              </div>

            {/* About */}
            {aboutParagraphs.length > 0 && (
              <div className="dp-section">
                <h2 className="dp-section-title">About</h2>
                <div className="dp-description">
                  {aboutParagraphs.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                </div>
              </div>
            )}

            {/* Info table */}
            <div className="dp-section">
              <div className="dp-info-table">
                {game.platforms.length > 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Platforms</span>
                    <span className="dp-info-val">
                      <PlatformIcons platforms={game.platforms} mode="detail" game={game} />
                    </span>
                  </div>
                )}
                {game.developer && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Developer</span>
                    <span className="dp-info-val">
                      <Link className="dp-info-link" to={catalogFilterHref('developer', game.developer)}>{game.developer}</Link>
                    </span>
                  </div>
                )}
                {game.publisher && game.publisher !== game.developer && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Publisher</span>
                    <span className="dp-info-val">
                      <Link className="dp-info-link" to={catalogFilterHref('publisher', game.publisher)}>{game.publisher}</Link>
                    </span>
                  </div>
                )}
                {game.genres.length > 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Genre</span>
                    <span className="dp-info-val">
                      {game.genres.map((genre, index) => (
                        <span key={genre}>
                          {index > 0 ? ', ' : ''}
                          <Link className="dp-info-link" to={catalogFilterHref('genre', genre)}>{genre}</Link>
                        </span>
                      ))}
                    </span>
                  </div>
                )}
                {game.franchise && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Series</span>
                    <span className="dp-info-val">{game.franchise}</span>
                  </div>
                )}
                <div className="dp-info-row">
                  <span className="dp-info-key">Release date</span>
                  <span className="dp-info-val">
                    <ReleaseValue label={primaryReleaseLabel} year={game.release_year} />
                    {earlyAccessSuffix}
                  </span>
                </div>
                {gameModes.length > 0 && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">Game modes</span>
                    <span className="dp-info-val">{gameModes.map(formatGameMode).join(', ')}</span>
                  </div>
                )}
                {(endless || hasHltb) && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">How long to beat</span>
                    <span className="dp-info-val">
                      {endless ? (
                        <span className="dp-hltb-endless" title="Endlessly replayable — no fixed completion time">∞</span>
                      ) : (
                        <span className="dp-hltb">
                          {hltbUrl ? (
                            <a className="dp-info-link" href={hltbUrl} target="_blank" rel="noopener noreferrer">
                              {formatHours(hltbPrimaryMinutes)}
                              <ExternalLink size={11} aria-hidden="true" />
                            </a>
                          ) : (
                            formatHours(hltbPrimaryMinutes)
                          )}
                          {hltbDetail.length > 0 && (
                            <button
                              type="button"
                              className="dp-hltb-info"
                              aria-label="Other playtimes"
                              aria-describedby="game-hltb-tooltip"
                            >
                              <Info size={12} aria-hidden="true" />
                              <span id="game-hltb-tooltip" className="dp-hltb-tip" role="tooltip">
                                {hltbDetail.map(([label, minutes]) => (
                                  <span className="dp-hltb-tip-row" key={label}>
                                    <span>{label}</span>
                                    <span>{formatHours(Number(minutes))}</span>
                                  </span>
                                ))}
                              </span>
                            </button>
                          )}
                        </span>
                      )}
                    </span>
                  </div>
                )}
                {game.goty_year && (
                  <div className="dp-info-row">
                    <span className="dp-info-key">GOTY</span>
                    <span className="dp-info-val">
                      <Link className="dp-info-link" to={catalogFilterHref('year', game.goty_year)}>{game.goty_year}</Link>
                    </span>
                  </div>
                )}
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
              </div>
              <p className="dp-attribution">
                Metadata and imagery may include attributed data from{' '}
                <a href="https://rawg.io/" target="_blank" rel="noopener noreferrer">RAWG</a>.
              </p>
            </div>

            {/* System requirements */}
            {game.system_requirements.length > 0 && (
              <div className="dp-section">
                {game.system_requirements.map((req) => (
                  <div key={req.platform}>
                    <h2 className="dp-section-title">System requirements for {req.platform}</h2>
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
            {priceSnapshots.length > 0 && (
              <div className="dp-side-panel">
                <h2 className="dp-section-title">Where to buy</h2>
                <PricePanel prices={priceSnapshots} game={game} />
              </div>
            )}
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
    </main>
  )
}
