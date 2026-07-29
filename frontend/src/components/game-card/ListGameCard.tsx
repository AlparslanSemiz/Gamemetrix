import { Clock3, Play } from 'lucide-react'
import { Link } from 'react-router'
import { PlatformIcons } from '../PlatformIcons'
import { ScoreRing } from '../ScoreRing'
import { GameAwardBadge } from './GameAwardBadge'
import { GameCardActions } from './GameCardActions'
import { GameSourceScores } from './GameSourceScores'
import { hltbTooltip, playtimeColor } from './model'
import { ProtonBadge } from './ProtonBadge'
import type { GameCardViewProps } from './types'

function ListCardCover({
  game,
  model,
  onCoverError,
  onOpenTrailer,
  priority,
}: Pick<
  GameCardViewProps,
  'game' | 'model' | 'onCoverError' | 'onOpenTrailer' | 'priority'
>) {
  return (
    <div className="cover" onClick={() => onOpenTrailer(game)} title="Watch trailer">
      <img
        src={model.coverSrc}
        alt={`${game.title} cover`}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        onError={onCoverError}
      />
      <div className="cover-play-hint"><Play size={16} aria-hidden="true" /></div>
      <div className="mobile-cover-score"><ScoreRing score={game.metrix_score} size="sm" /></div>
    </div>
  )
}

function ListCardBody(props: Pick<
  GameCardViewProps,
  | 'game'
  | 'model'
  | 'onFilterDeveloper'
  | 'onFilterGenre'
  | 'onFilterPublisher'
  | 'onOpenDetail'
>) {
  const {
    game,
    model,
    onFilterDeveloper,
    onFilterGenre,
    onFilterPublisher,
    onOpenDetail,
  } = props
  return (
    <div className="card-body">
      <div className="card-heading">
        <h2>
          <Link to={`/game/${game.slug}`} prefetch="intent" className="game-title-link" onClick={() => onOpenDetail(game)}>
            {game.title}
          </Link>
        </h2>
        {game.release_year > 1970 ? (
          <Link
            className="card-year card-year-link"
            to={`/?year=${game.release_year}`}
            title={`Show all ${game.release_year} games`}
          >
            {game.release_year}
          </Link>
        ) : <span className="card-year">TBA</span>}
        <div className="genre-links" aria-label={`${game.title} genres`}>
          {game.genres.slice(0, 4).map((genre, index, genres) => (
            <span key={genre} className="genre-item">
              <button type="button" onClick={() => onFilterGenre(genre)}>{genre}</button>
              {index < genres.length - 1 ? <span className="genre-comma">,</span> : null}
            </span>
          ))}
        </div>
      </div>
      <div className="summary-block"><p className="summary">{game.summary_short ?? ''}</p></div>
      <DeveloperPublisherLinks game={game} onFilterDeveloper={onFilterDeveloper} onFilterPublisher={onFilterPublisher} />
      <div className="meta-lines">
        {model.playtimeLabel || model.protonTier ? (
          <div className="meta-badge-row">
            {model.playtimeLabel ? <PlaytimeBadge model={model} tooltip={hltbTooltip(game)} /> : null}
            {model.protonTier ? <ProtonBadge game={game} tier={model.protonTier} /> : null}
          </div>
        ) : null}
        <PlatformIcons platforms={game.platforms} mode="list" game={game} />
      </div>
    </div>
  )
}

function ListCardScores({ game, model }: Pick<GameCardViewProps, 'game' | 'model'>) {
  return (
    <div className="score-column">
      <ScoreRing score={game.metrix_score} />
      <div className={`score-confidence score-confidence-${model.confidenceLevel.toLowerCase()}${model.isRankedLower ? ' score-confidence-ranked-lower' : ''}`} title={model.confidenceTitle}>
        <span>Data {model.confidenceLevel}</span>
        <small>{model.primarySourceCount}/{model.applicableSourceCount} applicable · {model.scoreProfile}</small>
        {model.isRankedLower ? <small className="ranked-lower-hint">↓ ranked lower</small> : null}
      </div>
      <GameAwardBadge game={game} />
      <GameSourceScores game={game} sources={model.displayedSources} />
    </div>
  )
}

export function ListGameCard({
  game,
  model,
  onCoverError,
  onFilterDeveloper,
  onFilterGenre,
  onFilterPublisher,
  onOpenDetail,
  onOpenTrailer,
  priority,
  onShare,
  onToggleCollection,
  ...collectionState
}: GameCardViewProps) {
  return (
    <article
      className="game-card"
      style={model.cardStyle}
      data-game-slug={game.slug}
    >
      <ListCardCover
        game={game}
        model={model}
        onCoverError={onCoverError}
        onOpenTrailer={onOpenTrailer}
        priority={priority}
      />
      <ListCardBody
        game={game}
        model={model}
        onFilterDeveloper={onFilterDeveloper}
        onFilterGenre={onFilterGenre}
        onFilterPublisher={onFilterPublisher}
        onOpenDetail={onOpenDetail}
      />
      <ListCardScores game={game} model={model} />

      <div className="action-column" aria-label={`${game.title} actions`}>
        <GameCardActions
          {...collectionState}
          slug={game.slug}
          onShare={onShare}
          onToggleCollection={onToggleCollection}
        />
      </div>
    </article>
  )
}

function DeveloperPublisherLinks({
  game,
  onFilterDeveloper,
  onFilterPublisher,
}: Pick<
  GameCardViewProps,
  'game' | 'onFilterDeveloper' | 'onFilterPublisher'
>) {
  if (!game.developer && !game.publisher) return null
  return (
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
  )
}

function PlaytimeBadge({
  model,
  tooltip,
}: Pick<GameCardViewProps, 'model'> & {
  tooltip: string
}) {
  if (model.isEndless) {
    return (
      <span
        className="playtime-badge playtime-badge-endless"
        title="Endlessly replayable — no fixed completion time"
      >
        <Clock3 size={13} aria-hidden="true" />
        {model.playtimeLabel}
      </span>
    )
  }

  return (
    <a
      className="playtime-badge"
      href={model.hltbHref}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: playtimeColor(model.hltbMinutes) }}
      title={tooltip}
    >
      <Clock3 size={13} aria-hidden="true" />
      {model.playtimeLabel}
    </a>
  )
}
