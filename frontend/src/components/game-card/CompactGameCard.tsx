import { Clock3, Play } from 'lucide-react'
import { Link } from 'react-router'
import { ScoreRing } from '../ScoreRing'
import { GameAwardBadge } from './GameAwardBadge'
import { GameCardActions } from './GameCardActions'
import { ProtonBadge } from './ProtonBadge'
import type { GameCardViewProps } from './types'

export function CompactGameCard({
  game,
  model,
  onCoverError,
  onOpenDetail,
  onOpenTrailer,
  onShare,
  onToggleCollection,
  ...collectionState
}: GameCardViewProps) {
  return (
    <article
      className="game-card-compact"
      style={model.cardStyle}
      data-game-slug={game.slug}
    >
      <div
        className="compact-cover"
        role="button"
        tabIndex={0}
        onClick={() => onOpenTrailer(game)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') onOpenTrailer(game)
        }}
      >
        <img
          src={model.coverSrc}
          alt={`${game.title} cover`}
          loading="lazy"
          onError={onCoverError}
        />
        <div className="compact-play-hint">
          <Play size={20} aria-hidden="true" />
        </div>
        <div
          className={
            `compact-score compact-score-${model.confidenceLevel.toLowerCase()}`
          }
        >
          <ScoreRing score={game.metrix_score} size="sm" />
        </div>
      </div>

      <div className="compact-body">
        <h2 className="compact-title">
          <Link
            to={`/game/${game.slug}`}
            prefetch="intent"
            className="game-title-link"
            onClick={() => onOpenDetail(game)}
          >
            {game.title}
          </Link>
        </h2>
        <p className="compact-meta">
          {game.release_year > 1970 ? (
            <Link
              className="card-year-link"
              to={`/?year=${game.release_year}`}
              title={`Show all ${game.release_year} games`}
            >
              {game.release_year}
            </Link>
          ) : 'TBA'} · {game.genres.slice(0, 2).join(' · ')}
        </p>
        {game.developer ? (
          <p className="compact-dev">{game.developer}</p>
        ) : null}
        {model.playtimeLabel || model.protonTier ? (
          <div className="compact-meta-badges">
            {model.playtimeLabel ? (
              <span className="compact-hltb">
                <Clock3 size={10} aria-hidden="true" /> {model.playtimeLabel}
              </span>
            ) : null}
            {model.protonTier ? (
              <ProtonBadge game={game} tier={model.protonTier} compact />
            ) : null}
          </div>
        ) : null}
        <GameAwardBadge game={game} compact />
      </div>

      <div className="compact-actions" aria-label={`${game.title} actions`}>
        <GameCardActions
          {...collectionState}
          compact
          slug={game.slug}
          onShare={onShare}
          onToggleCollection={onToggleCollection}
        />
      </div>
    </article>
  )
}
