import {
  CheckCircle2,
  Clock3,
  Eye,
  Flag,
  Gamepad2,
  Heart,
  Play,
  Share2,
  Star,
  Trophy,
  Zap,
} from 'lucide-react'
import { useState, type CSSProperties, type SyntheticEvent } from 'react'
import type { Game } from '../types/game'
import { PlatformIcons } from './PlatformIcons'
import { ScoreRing, scoreColor } from './ScoreRing'

interface GameCardProps {
  game: Game
  isRefreshing: boolean
  isFavorite: boolean
  isLiked: boolean
  isPlaying: boolean
  isSeen: boolean
  isCompleted: boolean
  isWatchlisted: boolean
  compact?: boolean
  onRefresh: (slug: string) => void
  onOpenTrailer: (game: Game) => void
  onFilterDeveloper: (developer: string) => void
  onFilterGenre: (genre: string) => void
  onFilterPublisher: (publisher: string) => void
  onToggleCollection: (
    collection: 'watchlist' | 'seen' | 'liked' | 'favorites',
    slug: string,
  ) => void
}

const ALL_PRIMARY_SOURCES = new Set(['Metacritic', 'OpenCritic', 'IGDB', 'Steam'])

function sourceUrl(source: string, game: Game): string | null {
  const q = encodeURIComponent(game.title)
  const steamAppId = game.cover_url?.match(/steam\/apps\/(\d+)\//)?.[1]
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

function playtimeColor(minutes: number): string {
  const hours = minutes / 60
  // 50-60h is optimal; score degrades as you move away in either direction
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
      <text x="120" y="540" fill="#57d46d" font-family="Inter, Segoe UI, sans-serif" font-size="34" font-weight="800">GAMEMETRIX</text>
    </svg>`
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
}

export function GameCard({
  game,
  isFavorite,
  isLiked,
  isPlaying,
  isRefreshing,
  isSeen,
  isCompleted,
  isWatchlisted,
  compact = false,
  onRefresh,
  onOpenTrailer,
  onFilterDeveloper,
  onFilterGenre,
  onFilterPublisher,
  onToggleCollection,
}: GameCardProps) {
  const [expanded, setExpanded] = useState(false)

  const ENDLESS_GENRES = new Set([
    'Roguelike', 'Roguelite', 'Rogue-like', 'Rogue-lite', 'Roguelikes', 'Rouge-like',
    'roguelike', 'roguelite', 'rogue-like',
    'Massively Multiplayer', 'MMO', 'MMORPG', 'Battle Royale',
    'Sports', 'Racing', 'Sandbox', 'Party', 'Pinball',
  ])
  const isEndless = game.genres.some((g) => ENDLESS_GENRES.has(g))
  const playtimeFmt = isEndless
    ? '∞'
    : game.playtime_minutes > 0
      ? `${Math.round(game.playtime_minutes / 60)}h`
      : null
  const coverSrc = game.cover_url || fallbackCoverUrl(game.title)
  const cardStyle = {
    '--score-color': scoreColor(game.metrix_score),
    '--cover-image': `url("${coverSrc.replaceAll('"', '\\"')}")`,
  } as CSSProperties
  const handleCoverError = (event: SyntheticEvent<HTMLImageElement>) => {
    const fallback = fallbackCoverUrl(game.title)
    if (event.currentTarget.src !== fallback) {
      event.currentTarget.src = fallback
    }
  }

  const handleShare = () => {
    void navigator.clipboard.writeText(`${window.location.origin}/?game=${game.slug}`)
  }

  const applicableSources = new Set(
    game.applicable_sources?.length ? game.applicable_sources : Array.from(ALL_PRIMARY_SOURCES),
  )
  const applicableSourceCount = game.applicable_source_count ?? applicableSources.size
  const primarySourceScores = game.source_scores.filter((source) =>
    applicableSources.has(source.source),
  )
  const auxiliarySources = game.source_scores.filter((source) =>
    !ALL_PRIMARY_SOURCES.has(source.source) && source.status === 'live',
  )
  const auxiliarySourceNames = auxiliarySources
    .map((source) => source.source)
    .filter(Boolean)
    .join(', ')
  const auxiliarySummary = game.popularity_label
    ? `Popularity: ${game.popularity_label}${auxiliarySourceNames ? ` · ${auxiliarySourceNames}` : ''}`
    : auxiliarySourceNames
      ? `Catalog data: ${auxiliarySourceNames}`
      : null
  const confidenceLevel = game.confidence_level ?? 'Limited'
  const primarySourceCount = game.live_primary_source_count ?? primarySourceScores.filter(
    (source) => source.status === 'live' && source.score > 0,
  ).length
  const scoreProfile = game.score_profile ?? 'sparse'

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
      <button
        type="button"
        title="Refresh live scores"
        disabled={isRefreshing}
        onClick={() => onRefresh(game.slug)}
      >
        <Zap size={20} aria-hidden="true" />
      </button>
      <button type="button" title="Copy link" onClick={handleShare}>
        <Share2 size={20} aria-hidden="true" />
      </button>
    </>
  )

  // ── Compact (grid) card ───────────────────────────────────────────
  if (compact) {
    return (
      <article className="game-card-compact" style={cardStyle}>
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
          <h3 className="compact-title">{game.title}</h3>
          <p className="compact-meta">{game.release_year} · {game.genres[0]}</p>
          {game.developer ? <p className="compact-dev">{game.developer}</p> : null}
          {playtimeFmt ? (
            <p className="compact-hltb">
              <Clock3 size={10} aria-hidden="true" /> {playtimeFmt}
            </p>
          ) : null}
          {(game.goty_year || (game.award_count ?? 0) > 0) ? (
            <p className="compact-award">
              <Trophy size={9} aria-hidden="true" />
              {game.goty_year ? ` GOTY ${game.goty_year}` : ` ${game.award_count} awards`}
            </p>
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
            title="Refresh live scores"
            disabled={isRefreshing}
            onClick={() => onRefresh(game.slug)}
          >
            <Zap size={17} aria-hidden="true" />
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
    <article className="game-card" style={cardStyle}>
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
      </div>

      {/* Body */}
      <div className="card-body">
        <div className="card-heading">
          <h3>{game.title}</h3>
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
          <p className={expanded ? 'summary summary-expanded' : 'summary'}>
            {game.summary}
          </p>
          {game.summary.length > 200 ? (
            <button
              type="button"
              className="read-more-button"
              onClick={() => setExpanded((c) => !c)}
            >
              {expanded ? 'Show less' : 'Read more'}
            </button>
          ) : null}
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
          {playtimeFmt ? (
            isEndless ? (
              <span className="playtime-badge playtime-badge-endless" title="Endlessly replayable — no fixed completion time">
                <Clock3 size={13} aria-hidden="true" />
                {playtimeFmt}
              </span>
            ) : (
              <a
                className="playtime-badge"
                href={`https://howlongtobeat.com/?q=${encodeURIComponent(game.title)}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: playtimeColor(game.playtime_minutes) }}
                title="HowLongToBeat — click to search"
              >
                <Clock3 size={13} aria-hidden="true" />
                {playtimeFmt}
              </a>
            )
          ) : null}
          <PlatformIcons platforms={game.platforms} mode="list" />
        </div>
      </div>

      {/* Score column */}
      <div className="score-column">
        <ScoreRing score={game.metrix_score} />

        <div
          className={`score-confidence score-confidence-${confidenceLevel.toLowerCase()}`}
          title="Confidence is based on live Metacritic, OpenCritic, IGDB, and Steam coverage."
        >
          <span>Data {confidenceLevel}</span>
          <small>{primarySourceCount}/{applicableSourceCount} applicable · {scoreProfile}</small>
        </div>

        {(game.goty_year || (game.award_count ?? 0) > 0) ? (
          <div
            className="award-badge"
            title={
              game.award_nominations
                ? `${game.award_count} major awards · ${game.award_nominations} nominations`
                : game.award_count > 0
                  ? `${game.award_count} major awards`
                  : `Game of the Year ${game.goty_year}`
            }
          >
            <Trophy size={11} aria-hidden="true" />
            <span>
              {game.goty_year ? `GOTY ${game.goty_year}` : `${game.award_count} awards`}
            </span>
          </div>
        ) : null}

        <div className="sources" aria-label={`${game.title} source scores`}>
          {primarySourceScores.length === 0 ? (
            <div className="source-empty">Primary ratings pending</div>
          ) : null}
          {primarySourceScores.map((source) => {
            const url = sourceUrl(source.source, game)
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

            if (source.status === 'unavailable') {
              return (
                <div className="source-row source-row-muted" key={source.source}>
                  {nameEl}
                  <div className="source-bar" />
                  <strong>—</strong>
                </div>
              )
            }

            const pct = Math.max(0, Math.min(source.score, 100))
            return (
              <div
                className="source-row"
                key={source.source}
                title={source.detail ?? source.refreshed_at ?? source.source}
              >
                {nameEl}
                <div className="source-bar">
                  <span className="source-fill" style={{ width: `${pct}%` }} />
                </div>
                <strong>{Math.round(source.score)}</strong>
              </div>
            )
          })}
        </div>
        {auxiliarySummary ? (
          <div className="aux-source" title="Auxiliary data is not treated as a primary rating source.">
            {auxiliarySummary}
          </div>
        ) : null}
      </div>

      {/* Action icon strip */}
      <div className="action-column" aria-label={`${game.title} actions`}>
        {actionButtons}
      </div>
    </article>
  )
}
