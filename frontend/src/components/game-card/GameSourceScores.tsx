import type { CSSProperties } from 'react'
import type { Game, SourceScore } from '../../types/game'
import { sourceScoreColor } from '../../utils/scoreColors'
import { sourceScoreUrl } from '../../utils/sourceLinks'

interface GameSourceScoresProps {
  game: Game
  sources: SourceScore[]
}

export function GameSourceScores({
  game,
  sources,
}: GameSourceScoresProps) {
  return (
    <div className="sources" aria-label={`${game.title} source scores`}>
      {sources.map((source) => (
        <GameSourceScore key={source.source} game={game} source={source} />
      ))}
    </div>
  )
}

function GameSourceScore({
  game,
  source,
}: {
  game: Game
  source: SourceScore
}) {
  const url = sourceScoreUrl(source.source, game, 'catalog-card')
  const unavailable = source.status !== 'live' || source.score <= 0
  const percentage = Math.max(0, Math.min(source.score, 100))

  return (
    <div
      className={`source-row${unavailable ? ' source-row-unavailable' : ''}`}
      title={source.detail ?? source.refreshed_at ?? source.source}
      style={{ '--source-color': sourceScoreColor(percentage) } as CSSProperties}
    >
      {url ? (
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
      )}
      <div className="source-bar">
        <span
          className="source-fill"
          style={{ width: unavailable ? '0%' : `${percentage}%` }}
        />
      </div>
      <strong>{unavailable ? '—' : Math.round(source.score)}</strong>
    </div>
  )
}
