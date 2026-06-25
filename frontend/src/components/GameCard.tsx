import {
  CheckCircle2,
  Clock3,
  Eye,
  Heart,
  Play,
  Share2,
  Star,
  Zap,
} from 'lucide-react'
import { useState } from 'react'
import type { Game } from '../types/game'
import { PlatformBadges } from './PlatformBadges'
import { ScoreRing } from './ScoreRing'
import { WhereToPlay } from './WhereToPlay'

interface GameCardProps {
  game: Game
  isRefreshing: boolean
  isFavorite: boolean
  isLiked: boolean
  isSeen: boolean
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

export function GameCard({
  game,
  isFavorite,
  isLiked,
  isRefreshing,
  isSeen,
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
  const playtimeLabel = game.playtime_minutes > 0
    ? `${Math.round(game.playtime_minutes / 60)}h`
    : 'n/a'

  const handleShare = () => {
    void navigator.clipboard.writeText(`${window.location.origin}/?game=${game.slug}`)
  }

  const actionButtons = (
    <>
      <button
        type="button"
        className={isSeen ? 'is-active' : ''}
        title="Mark as seen"
        onClick={() => onToggleCollection('seen', game.slug)}
      >
        <Eye size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isWatchlisted ? 'is-active' : ''}
        title="Add to watchlist"
        onClick={() => onToggleCollection('watchlist', game.slug)}
      >
        <CheckCircle2 size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isLiked ? 'is-active' : ''}
        title="Like"
        onClick={() => onToggleCollection('liked', game.slug)}
      >
        <Heart size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={isFavorite ? 'is-active' : ''}
        title="Add to favorites"
        onClick={() => onToggleCollection('favorites', game.slug)}
      >
        <Star size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        title="Refresh live scores"
        disabled={isRefreshing}
        onClick={() => onRefresh(game.slug)}
      >
        <Zap size={15} aria-hidden="true" />
      </button>
      <button type="button" title="Copy link" onClick={handleShare}>
        <Share2 size={15} aria-hidden="true" />
      </button>
    </>
  )

  // ── Compact (grid) card ───────────────────────────────────────────
  if (compact) {
    return (
      <article className="game-card-compact">
        <div className="compact-cover" onClick={() => onOpenTrailer(game)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onOpenTrailer(game)}>
          <img src={game.cover_url} alt={`${game.title} cover`} loading="lazy" />
          <div className="compact-play-hint">
            <Play size={20} aria-hidden="true" />
          </div>
          <div className="compact-score">
            <ScoreRing score={game.metrix_score} size="sm" />
          </div>
        </div>
        <div className="compact-body">
          <h3 className="compact-title">{game.title}</h3>
          <p className="compact-meta">{game.release_year} · {game.genres[0]}</p>
          {game.developer ? <p className="compact-dev">{game.developer}</p> : null}
          <p className="compact-dev">HLTB {playtimeLabel}</p>
        </div>
        <div className="compact-actions" aria-label={`${game.title} actions`}>
          {actionButtons}
        </div>
      </article>
    )
  }

  // ── Full (list) card ──────────────────────────────────────────────
  return (
    <article className="game-card">
      {/* Cover */}
      <div className="cover">
        <img src={game.cover_url} alt={`${game.title} cover`} loading="lazy" />
        <button type="button" className="trailer-button" onClick={() => onOpenTrailer(game)}>
          <Play size={13} aria-hidden="true" />
          Watch Trailer
        </button>
      </div>

      {/* Body */}
      <div className="card-body">
        <div className="card-heading">
          <h3>{game.title}</h3>
          <span className="card-year">{game.release_year}</span>
          <div className="genre-links" aria-label={`${game.title} genres`}>
            {game.genres.slice(0, 4).map((genre) => (
              <button type="button" key={genre} onClick={() => onFilterGenre(genre)}>
                {genre}
              </button>
            ))}
          </div>
        </div>

        <div className="summary-block">
          <p className={expanded ? 'summary summary-expanded' : 'summary'}>
            {game.summary}
          </p>
          {game.summary.length > 180 ? (
            <button
              type="button"
              className="read-more-button"
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? 'Show less' : 'Read more'}
            </button>
          ) : null}
        </div>

        {/* Developer / Publisher */}
        {(game.developer || game.publisher) ? (
          <div className="dev-pub-row">
            {game.developer ? (
              <button type="button" onClick={() => onFilterDeveloper(game.developer ?? '')}>
                <b>Developer:</b> {game.developer}
              </button>
            ) : null}
            {game.publisher && game.publisher !== game.developer ? (
              <button type="button" onClick={() => onFilterPublisher(game.publisher ?? '')}>
                <b>Publisher:</b> {game.publisher}
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="meta-lines">
          <div className="playtime-badge" title="Estimated main-story / average playtime">
            <Clock3 size={13} aria-hidden="true" />
            HLTB {playtimeLabel}
          </div>
          <PlatformBadges platforms={game.platforms} />
          <WhereToPlay platforms={game.platforms} slug={game.slug} title={game.title} />
        </div>
      </div>

      {/* Score column */}
      <div className="score-column">
        <ScoreRing score={game.metrix_score} />

        <div className="sources" aria-label={`${game.title} source scores`}>
          {game.source_scores.map((source) => {
            if (source.status === 'unavailable') {
              return (
                <div className="source-row source-row-muted" key={source.source}>
                  <div className="source-bar">
                    <span className="source-label">{source.source}</span>
                  </div>
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
                <div className="source-bar">
                  <span className="source-label">{source.source}</span>
                  <span className="source-fill" style={{ width: `${pct}%` }} />
                </div>
                <strong>{Math.round(source.score)}</strong>
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
}
