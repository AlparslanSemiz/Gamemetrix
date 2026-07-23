import { ExternalLink } from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import type { Game, SourceScore } from '../../types/game'
import {
  DETAIL_EXTRA_SOURCE_ORDER,
  DETAIL_PRIMARY_SOURCE_ORDER,
} from '../../utils/ratingSources'
import { sourceScoreColor } from '../../utils/scoreColors'
import { sourceScoreUrl } from '../../utils/sourceLinks'
import { formatCount } from './format'

type RatingsTab = 'primary' | 'extra'

export function GameRatingsPanel({ game }: { game: Game }) {
  const [activeTab, setActiveTab] = useState<RatingsTab>('primary')
  const { extraScores, primaryScores } = ratingScores(game)

  return (
    <div className="dp-section">
      <div className="dp-ratings-tabs">
        <button
          type="button"
          className={`dp-rtab${activeTab === 'primary' ? ' dp-rtab-active' : ''}`}
          onClick={() => setActiveTab('primary')}
        >
          Ratings
        </button>
        {extraScores.length > 0 ? (
          <button
            type="button"
            className={`dp-rtab${activeTab === 'extra' ? ' dp-rtab-active' : ''}`}
            onClick={() => setActiveTab('extra')}
          >
            Other Sources
          </button>
        ) : null}
      </div>
      <div className="dp-src-list">
        {(activeTab === 'primary' ? primaryScores : extraScores).map(
          (source) => (
            <RatingSourceRow
              key={source.source}
              game={game}
              secondary={activeTab === 'extra'}
              source={source}
            />
          ),
        )}
      </div>
    </div>
  )
}

function ratingScores(game: Game) {
  const scoreBySource = new Map(
    game.source_scores.map((source) => [source.source, source]),
  )
  const primaryScores: SourceScore[] = DETAIL_PRIMARY_SOURCE_ORDER.map(
    (source) => {
      const score = scoreBySource.get(source)
      return score?.status === 'live' && score.score > 0
        ? score
        : {
            source,
            score: 0,
            scale: 100,
            status: 'unavailable',
            detail: 'No live score has been collected yet.',
          }
    },
  )
  const extraScores = DETAIL_EXTRA_SOURCE_ORDER
    .map((source) => scoreBySource.get(source))
    .filter((source): source is SourceScore => (
      source !== undefined
      && source.status === 'live'
      && source.score > 0
    ))
  return { extraScores, primaryScores }
}

function RatingSourceRow({
  game,
  secondary,
  source,
}: {
  game: Game
  secondary: boolean
  source: SourceScore
}) {
  const url = sourceScoreUrl(source.source, game, 'game-detail')
  const percentage = Math.max(0, Math.min(source.score, 100))
  const unavailable = source.status !== 'live' || source.score <= 0

  return (
    <div
      className={
        `dp-src-row${secondary ? ' dp-src-row-secondary' : ''}`
        + `${unavailable ? ' dp-src-row-unavailable' : ''}`
      }
      title={source.detail ?? source.source}
      style={{ '--source-color': sourceScoreColor(percentage) } as CSSProperties}
    >
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className={
            `dp-src-name dp-src-link${
              secondary ? ' dp-src-secondary' : ''
            }`
          }
        >
          {source.source} <ExternalLink size={9} />
        </a>
      ) : (
        <span className={`dp-src-name${secondary ? ' dp-src-secondary' : ''}`}>
          {source.source}
        </span>
      )}
      <div className="dp-src-bar">
        <span
          className="dp-src-fill"
          style={{ width: unavailable ? '0%' : `${percentage}%` }}
        />
      </div>
      <strong className="dp-src-score">
        {unavailable ? '—' : Math.round(source.score)}
      </strong>
      {source.review_count ? (
        <span className="dp-src-count">
          {formatCount(source.review_count)}
        </span>
      ) : null}
    </div>
  )
}
