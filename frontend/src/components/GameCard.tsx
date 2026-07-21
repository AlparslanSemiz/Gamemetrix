import {
  CheckCircle2,
  Clock3,
  Eye,
  Flag,
  Gamepad2,
  Heart,
  Medal,
  MonitorCheck,
  Play,
  Share2,
  Star,
  Tag,
  Trophy,
} from 'lucide-react'
import { memo, type CSSProperties, type SyntheticEvent } from 'react'
import { Link } from 'react-router-dom'
import type { Game, PriceSnapshot, ProtonTier, SourceScore } from '../types/game'
import type { CollectionKey } from '../state/collections'
import { trackProductEvent } from '../services/analytics'
import { PlatformIcons } from './PlatformIcons'
import { ScoreRing } from './ScoreRing'
import { scoreColor, scoreColorRgb, sourceScoreColor } from '../utils/scoreColors'
import { steamAppIdFromGame } from '../utils/steam'
import { PROTON_TIER_DESCRIPTIONS, formatProtonScore, isProtonTier } from '../utils/proton'
import { currentPriceSnapshots } from '../utils/prices'
import { safeExternalUrl } from '../utils/url'

interface GameCardProps {
  game: Game
  isFavorite: boolean
  isLiked: boolean
  isPlaying: boolean
  isSeen: boolean
  isCompleted: boolean
  isWatchlisted: boolean
  compact?: boolean
  onOpenTrailer: (game: Game) => void
  onFilterDeveloper: (developer: string) => void
  onFilterGenre: (genre: string) => void
  onFilterPublisher: (publisher: string) => void
  onToggleCollection: (
    collection: CollectionKey,
    slug: string,
  ) => void
  onOpenDetail: (game: Game) => void
}

const ALL_PRIMARY_SOURCES = new Set(['Metacritic', 'OpenCritic', 'IGDB', 'Steam'])
const PRIMARY_SOURCE_ORDER = ['Metacritic', 'OpenCritic', 'IGDB', 'Steam'] as const

function sourceUrl(source: string, game: Game): string | null {
  const q = encodeURIComponent(game.title)
  const steamAppId = steamAppIdFromGame(game)
  switch (source) {
    case 'Metacritic':
      return `https://www.metacritic.com/search/${q}/`
    case 'OpenCritic':
      return `https://opencritic.com/search?q=${q}`
    case 'Steam':
      return steamAppId
        ? `https://store.steampowered.com/app/${steamAppId}/`
        : `https://store.steampowered.com/search/?term=${q}`
    case 'IGDB':
      return `https://www.igdb.com/search?type=1&q=${q}`
    case 'RAWG':
      return `https://rawg.io/search?query=${q}`
    case 'SteamSpy':
      return steamAppId
        ? `https://steamspy.com/app/${steamAppId}`
        : null
    default:
      return null
  }
}

function protonReportUrl(game: Game): string | null {
  const steamAppId = steamAppIdFromGame(game)
  return steamAppId ? `https://www.protondb.com/app/${steamAppId}` : null
}

function ProtonBadge({
  game,
  tier,
  compact = false,
}: {
  game: Game
  tier: ProtonTier
  compact?: boolean
}) {
  const reportUrl = protonReportUrl(game)
  const scoreText = formatProtonScore(game.proton_score)
  const title = scoreText
    ? `ProtonDB: ${PROTON_TIER_DESCRIPTIONS[tier]} (${scoreText}/100)`
    : `ProtonDB: ${PROTON_TIER_DESCRIPTIONS[tier]}`
  const className = `proton-badge proton-badge-${tier}${compact ? ' proton-badge-compact' : ''}`
  const content = (
    <>
      <MonitorCheck size={compact ? 10 : 13} aria-hidden="true" />
      <span>Linux</span>
    </>
  )

  if (!reportUrl) {
    return (
      <span className={className} title={title}>
        {content}
      </span>
    )
  }

  return (
    <a className={className} href={reportUrl} target="_blank" rel="noopener noreferrer" title={title}>
      {content}
    </a>
  )
}

function priceAmount(price: PriceSnapshot): number | null {
  if (price.is_free) return 0
  return price.sale_price ?? price.list_price ?? null
}

function bestPriceSnapshot(game: Game): PriceSnapshot | null {
  const priced = currentPriceSnapshots(game.price_snapshots ?? [])
    .filter((price) => priceAmount(price) !== null)
    .sort((a, b) => (priceAmount(a) ?? Infinity) - (priceAmount(b) ?? Infinity))
  return priced[0] ?? null
}

function priceLabel(price: PriceSnapshot): string {
  const amount = priceAmount(price)
  if (amount === 0) return 'Free'
  if (amount === null) return 'Deal'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: price.currency || 'USD',
    maximumFractionDigits: amount >= 10 ? 0 : 2,
  }).format(amount)
}

function DealBadge({ price, compact = false }: { price: PriceSnapshot; compact?: boolean }) {
  const discount = price.discount_percent && price.discount_percent > 0 ? `-${price.discount_percent}%` : null
  return (
    <span
      className={`deal-badge${price.is_free ? ' deal-badge-free' : ''}${compact ? ' deal-badge-compact' : ''}`}
      title={`${price.store}: ${priceLabel(price)}${discount ? ` (${discount})` : ''}`}
    >
      <Tag size={compact ? 10 : 13} aria-hidden="true" />
      <span>{priceLabel(price)}</span>
      {discount && !compact ? <small>{discount}</small> : null}
    </span>
  )
}

function playtimeColor(minutes: number): string {
  const hours = minutes / 60
  let score: number
  if (hours >= 50 && hours <= 60) {
    score = 100
  } else if (hours < 50) {
    score = Math.max(0, (hours / 50) * 100)
  } else {
    score = Math.max(0, 100 - ((hours - 60) / 160) * 100)
  }
  if (score >= 80) return '#16a34a'
  if (score >= 65) return '#22c55e'
  if (score >= 50) return '#84cc16'
  if (score >= 35) return '#eab308'
  if (score >= 20) return '#ea580c'
  return '#dc2626'
}

function formatHours(minutes: number): string {
  return `${Math.max(1, Math.round(minutes / 60))}h`
}

function hltbTooltip(game: Game): string {
  const rows = [
    ['Main', game.hltb_main_story_minutes],
    ['Extra', game.hltb_main_extra_minutes],
    ['100%', game.hltb_completionist_minutes],
    ['Avg', game.hltb_all_styles_minutes],
  ]
    .filter(([, minutes]) => Number(minutes) > 0)
    .map(([label, minutes]) => `${label}: ${formatHours(Number(minutes))}`)
  return rows.length > 0 ? `HowLongToBeat - ${rows.join(' | ')}` : 'HowLongToBeat - click to search'
}

function fallbackCoverUrl(title: string): string {
  const words = title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 4)
    .join(' ')
  const safeTitle = words || 'GameMetrix'
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">
      <defs>
        <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#20242c"/>
          <stop offset="0.55" stop-color="#15171d"/>
          <stop offset="1" stop-color="#22352a"/>
        </linearGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#bg)"/>
      <rect x="64" y="64" width="1472" height="772" rx="28" fill="none" stroke="#3c4642" stroke-width="6"/>
      <text x="120" y="450" fill="#f1f3f7" font-family="Inter, Segoe UI, sans-serif" font-size="86" font-weight="800">${safeTitle}</text>
      <text x="120" y="540" fill="#a78bfa" font-family="Inter, Segoe UI, sans-serif" font-size="34" font-weight="800">GAMEMETRIX</text>
    </svg>`
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
}

export const GameCard = memo(function GameCard({
  game,
  isFavorite,
  isLiked,
  isPlaying,
  isSeen,
  isCompleted,
  isWatchlisted,
  compact = false,
  onOpenTrailer,
  onFilterDeveloper,
  onFilterGenre,
  onFilterPublisher,
  onToggleCollection,
  onOpenDetail,
}: GameCardProps) {
  const ENDLESS_GENRES = new Set([
    'Roguelike', 'Roguelite', 'Rogue-like', 'Rogue-lite', 'Roguelikes', 'Rouge-like',
    'roguelike', 'roguelite', 'rogue-like',
    'Massively Multiplayer', 'MMO', 'MMORPG', 'Battle Royale',
    'Sports', 'Racing', 'Sandbox', 'Party', 'Pinball',
  ])
  const isEndless = game.genres.some((g) => ENDLESS_GENRES.has(g))
  const hltbMinutes = game.hltb_main_story_minutes > 0
    ? game.hltb_main_story_minutes
    : game.playtime_minutes
  const playtimeFmt = isEndless
    ? '∞'
    : hltbMinutes > 0
      ? formatHours(hltbMinutes)
      : null
  const protonTier = game.proton_tier && isProtonTier(game.proton_tier)
    ? game.proton_tier
    : null
  const bestPrice = bestPriceSnapshot(game)
  const hltbHref = safeExternalUrl(game.hltb_url) ?? `https://howlongtobeat.com/?q=${encodeURIComponent(game.title)}`
  const coverSrc = game.cover_url || fallbackCoverUrl(game.title)
  const displayScore = Math.round(game.metrix_score)
  const cardStyle = {
    '--score-color': scoreColor(displayScore),
    '--score-rgb': scoreColorRgb(displayScore),
    '--cover-image': `url("${coverSrc.replaceAll('"', '\\"')}")`,
  } as CSSProperties
  const handleCoverError = (event: SyntheticEvent<HTMLImageElement>) => {
    const fallback = fallbackCoverUrl(game.title)
    if (event.currentTarget.src !== fallback) {
      event.currentTarget.src = fallback
    }
  }

  const handleShare = () => {
    void navigator.clipboard.writeText(`${window.location.origin}/game/${game.slug}`).catch(() => undefined)
    trackProductEvent('share', { game_slug: game.slug, surface: 'game_card' })
  }

  const applicableSources = new Set(
    game.applicable_sources?.length ? game.applicable_sources : Array.from(ALL_PRIMARY_SOURCES),
  )
  const applicableSourceCount = game.applicable_source_count ?? applicableSources.size

  const scoreBySource = new Map(game.source_scores.map((s) => [s.source, s]))

  const displayedSources: SourceScore[] = PRIMARY_SOURCE_ORDER.map((source) => (
    scoreBySource.get(source) ?? {
      source,
      score: 0,
      scale: 100,
      status: 'unavailable',
      detail: applicableSources.has(source) ? 'Rating pending.' : 'Not applicable to this platform.',
    }
  ))
  const livePrimary = displayedSources.filter((source) => source.status === 'live' && source.score > 0)

  const confidenceLevel = game.confidence_level ?? 'Limited'
  const primarySourceCount = game.live_primary_source_count ?? livePrimary.length
  const scoreProfile = game.score_profile ?? 'sparse'

  const isRankedLower =
    game.content_type === 'game' &&
    game.is_rankable === false &&
    confidenceLevel !== 'Catalog'

  const confidenceTitle = isRankedLower
    ? 'Score based on limited source coverage. Ranked lower in default lists until more sources confirm this rating.'
    : 'Confidence is based on live Metacritic, OpenCritic, IGDB, and Steam coverage.'

  const actionButtons = (
    <>
      <button
        type="button"
        className={isWatchlisted ? 'is-active' : ''}
        title="Add to wishlist"
        onClick={() => onToggleCollection('watchlist', game.slug)}
      >
        <CheckCircle2 size={20} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isPlaying ? 'is-active' : ''}
        title="Currently playing"
        onClick={() => onToggleCollection('playing', game.slug)}
      >
        <Gamepad2 size={20} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isSeen ? 'is-active' : ''}
        title="Mark as played"
        onClick={() => onToggleCollection('seen', game.slug)}
      >
        <Eye size={20} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isCompleted ? 'is-active' : ''}
        title="Mark as completed"
        onClick={() => onToggleCollection('completed', game.slug)}
      >
        <Flag size={20} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isLiked ? 'is-active' : ''}
        title="Like"
        onClick={() => onToggleCollection('liked', game.slug)}
      >
        <Heart size={20} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isFavorite ? 'is-active' : ''}
        title="Add to favorites"
        onClick={() => onToggleCollection('favorites', game.slug)}
      >
        <Star size={20} aria-hidden="true" />
      </button>
      <button type="button" title="Copy link" onClick={handleShare}>
        <Share2 size={20} aria-hidden="true" />
      </button>
    </>
  )

  // ── Compact (grid) card ───────────────────────────────────────────
  if (compact) {
    return (
      <article className="game-card-compact" style={cardStyle} data-game-slug={game.slug}>
        <div
          className="compact-cover"
          role="button"
          tabIndex={0}
          onClick={() => onOpenTrailer(game)}
          onKeyDown={(e) => e.key === 'Enter' && onOpenTrailer(game)}
        >
          <img
            src={coverSrc}
            alt={`${game.title} cover`}
            loading="lazy"
            onError={handleCoverError}
          />
          <div className="compact-play-hint">
            <Play size={20} aria-hidden="true" />
          </div>
          <div className={`compact-score compact-score-${confidenceLevel.toLowerCase()}`}>
            <ScoreRing score={game.metrix_score} size="sm" />
          </div>
        </div>
        <div className="compact-body">
          <h2 className="compact-title">
            <Link
              to={`/game/${game.slug}`}
              className="game-title-link"
              onClick={() => onOpenDetail(game)}
            >
              {game.title}
            </Link>
          </h2>
          <p className="compact-meta">{game.release_year} · {game.genres.slice(0, 2).join(' · ')}</p>
          {game.developer ? <p className="compact-dev">{game.developer}</p> : null}
          {(playtimeFmt || protonTier || bestPrice) ? (
            <div className="compact-meta-badges">
              {bestPrice ? <DealBadge price={bestPrice} compact /> : null}
              {playtimeFmt ? (
                <span className="compact-hltb">
                  <Clock3 size={10} aria-hidden="true" /> {playtimeFmt}
                </span>
              ) : null}
              {protonTier ? <ProtonBadge game={game} tier={protonTier} compact /> : null}
            </div>
          ) : null}
          {(game.goty_year || (game.award_count ?? 0) > 0) ? (
            <div className="compact-award">
              <Trophy size={9} aria-hidden="true" />
              {game.goty_year ? ` GOTY ${game.goty_year}` : ` ${game.award_count} awards`}
              <div className="award-tooltip">
                {game.awards?.length > 0
                  ? game.awards.map((a) => (
                      <div key={a} className="award-tooltip-item">
                        <Trophy size={10} aria-hidden="true" />
                        {a}
                      </div>
                    ))
                  : (
                      <>
                        {game.goty_year ? (
                          <div className="award-tooltip-item">
                            <Trophy size={10} aria-hidden="true" />
                            Game of the Year {game.goty_year}
                          </div>
                        ) : null}
                        {game.award_count > 0 ? (
                          <div className="award-tooltip-item">
                            <Medal size={10} aria-hidden="true" />
                            {game.award_count} major awards
                          </div>
                        ) : null}
                        {game.award_nominations > 0 ? (
                          <div className="award-tooltip-item">
                            <Medal size={10} aria-hidden="true" />
                            {game.award_nominations} nominations
                          </div>
                        ) : null}
                      </>
                    )
                }
              </div>
            </div>
          ) : null}
        </div>
        <div className="compact-actions" aria-label={`${game.title} actions`}>
          {/* Primary: always visible */}
          <button
            type="button"
            className={isWatchlisted ? 'is-active' : ''}
            title="Add to wishlist"
            onClick={() => onToggleCollection('watchlist', game.slug)}
          >
            <CheckCircle2 size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={isPlaying ? 'is-active' : ''}
            title="Currently playing"
            onClick={() => onToggleCollection('playing', game.slug)}
          >
            <Gamepad2 size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={isSeen ? 'is-active' : ''}
            title="Mark as played"
            onClick={() => onToggleCollection('seen', game.slug)}
          >
            <Eye size={17} aria-hidden="true" />
          </button>
          {/* Secondary: revealed on card hover */}
          <button
            type="button"
            className={`compact-secondary${isCompleted ? ' is-active' : ''}`}
            title="Mark as completed"
            onClick={() => onToggleCollection('completed', game.slug)}
          >
            <Flag size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`compact-secondary${isLiked ? ' is-active' : ''}`}
            title="Like"
            onClick={() => onToggleCollection('liked', game.slug)}
          >
            <Heart size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`compact-secondary${isFavorite ? ' is-active' : ''}`}
            title="Add to favorites"
            onClick={() => onToggleCollection('favorites', game.slug)}
          >
            <Star size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="compact-secondary"
            title="Copy link"
            onClick={handleShare}
          >
            <Share2 size={17} aria-hidden="true" />
          </button>
        </div>
      </article>
    )
  }

  // ── Full (list) card ──────────────────────────────────────────────
  return (
    <article className="game-card" style={cardStyle} data-game-slug={game.slug}>
      {/* Cover — click opens trailer */}
      <div className="cover" onClick={() => onOpenTrailer(game)} title="Watch trailer">
        <img
          src={coverSrc}
          alt={`${game.title} cover`}
          loading="lazy"
          onError={handleCoverError}
        />
        <div className="cover-play-hint">
          <Play size={16} aria-hidden="true" />
        </div>
        <div className="mobile-cover-score">
          <ScoreRing score={game.metrix_score} size="sm" />
        </div>
      </div>

      {/* Body */}
      <div className="card-body">
        <div className="card-heading">
          <h2>
            <Link
              to={`/game/${game.slug}`}
              className="game-title-link"
              onClick={() => onOpenDetail(game)}
            >
              {game.title}
            </Link>
          </h2>
          <span className="card-year">{game.release_year}</span>
          <div className="genre-links" aria-label={`${game.title} genres`}>
            {game.genres.slice(0, 4).map((genre, i, arr) => (
              <span key={genre} className="genre-item">
                <button type="button" onClick={() => onFilterGenre(genre)}>{genre}</button>
                {i < arr.length - 1 && <span className="genre-comma">,</span>}
              </span>
            ))}
          </div>
        </div>

        <div className="summary-block">
          <p className="summary">
            {game.summary_short ?? game.summary}
          </p>
        </div>

        {/* Developer / Publisher */}
        {(game.developer || game.publisher) ? (
          <div className="dev-pub-row">
            {game.developer ? (
              <span className="dev-pub-field">
                <span className="dev-pub-label">Dev:</span>
                <button
                  type="button"
                  className="dev-pub-link"
                  onClick={() => onFilterDeveloper(game.developer ?? '')}
                >
                  {game.developer}
                </button>
              </span>
            ) : null}
            {game.publisher && game.publisher !== game.developer ? (
              <span className="dev-pub-field">
                <span className="dev-pub-label">Pub:</span>
                <button
                  type="button"
                  className="dev-pub-link"
                  onClick={() => onFilterPublisher(game.publisher ?? '')}
                >
                  {game.publisher}
                </button>
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="meta-lines">
          {(playtimeFmt || protonTier || bestPrice) ? (
            <div className="meta-badge-row">
              {bestPrice ? <DealBadge price={bestPrice} /> : null}
              {playtimeFmt ? (
                isEndless ? (
                  <span className="playtime-badge playtime-badge-endless" title="Endlessly replayable — no fixed completion time">
                    <Clock3 size={13} aria-hidden="true" />
                    {playtimeFmt}
                  </span>
                ) : (
                  <a
                    className="playtime-badge"
                    href={hltbHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: playtimeColor(hltbMinutes) }}
                    title={hltbTooltip(game)}
                  >
                    <Clock3 size={13} aria-hidden="true" />
                    {playtimeFmt}
                  </a>
                )
              ) : null}
              {protonTier ? <ProtonBadge game={game} tier={protonTier} /> : null}
            </div>
          ) : null}
          <PlatformIcons platforms={game.platforms} mode="list" game={game} />
        </div>
      </div>

      {/* Score column */}
      <div className="score-column">
        <ScoreRing score={game.metrix_score} />

        <div
          className={`score-confidence score-confidence-${confidenceLevel.toLowerCase()}${isRankedLower ? ' score-confidence-ranked-lower' : ''}`}
          title={confidenceTitle}
        >
          <span>Data {confidenceLevel}</span>
          <small>{primarySourceCount}/{applicableSourceCount} applicable · {scoreProfile}</small>
          {isRankedLower ? <small className="ranked-lower-hint">↓ ranked lower</small> : null}
        </div>

        {(game.goty_year || (game.award_count ?? 0) > 0) ? (
          <div className="award-badge">
            <Trophy size={11} aria-hidden="true" />
            <span>
              {game.goty_year ? `GOTY ${game.goty_year}` : `${game.award_count} awards`}
            </span>
            <div className="award-tooltip">
              {game.awards?.length > 0
                ? game.awards.map((a) => (
                    <div key={a} className="award-tooltip-item">
                      <Trophy size={11} aria-hidden="true" />
                      {a}
                    </div>
                  ))
                : (
                    <>
                      {game.goty_year ? (
                        <div className="award-tooltip-item">
                          <Trophy size={11} aria-hidden="true" />
                          Game of the Year {game.goty_year}
                        </div>
                      ) : null}
                      {game.award_count > 0 ? (
                        <div className="award-tooltip-item">
                          <Medal size={11} aria-hidden="true" />
                          {game.award_count} major awards
                        </div>
                      ) : null}
                      {game.award_nominations > 0 ? (
                        <div className="award-tooltip-item">
                          <Medal size={11} aria-hidden="true" />
                          {game.award_nominations} nominations
                        </div>
                      ) : null}
                    </>
                  )
              }
            </div>
          </div>
        ) : null}

        <div className="sources" aria-label={`${game.title} source scores`}>
          {displayedSources.map((source) => {
            const url = sourceUrl(source.source, game)
            const unavailable = source.status !== 'live' || source.score <= 0
            const nameEl = url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="source-name source-name-link"
              >
                {source.source}
              </a>
            ) : (
              <span className="source-name">{source.source}</span>
            )

            const pct = Math.max(0, Math.min(source.score, 100))
            return (
              <div
                className={`source-row${unavailable ? ' source-row-unavailable' : ''}`}
                key={source.source}
                title={source.detail ?? source.refreshed_at ?? source.source}
                style={{ '--source-color': sourceScoreColor(pct) } as CSSProperties}
              >
                {nameEl}
                <div className="source-bar">
                  <span className="source-fill" style={{ width: unavailable ? '0%' : `${pct}%` }} />
                </div>
                <strong>{unavailable ? '—' : Math.round(source.score)}</strong>
              </div>
            )
          })}
        </div>
      </div>

      {/* Action icon strip */}
      <div className="action-column" aria-label={`${game.title} actions`}>
        {actionButtons}
      </div>
    </article>
  )
})
