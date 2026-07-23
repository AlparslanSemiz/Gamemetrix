import { Info } from 'lucide-react'
import type { CSSProperties } from 'react'
import { ScoreRing } from '../../components/ScoreRing'
import type { Game, SourceScore } from '../../types/game'
import {
  DETAIL_PRIMARY_SOURCE_ORDER,
  REVIEW_VOLUME_SOURCES,
} from '../../utils/ratingSources'
import { formatCompactCount, formatCount } from './format'

const DEFAULT_APPLICABLE_SOURCE_COUNT = 4

const POPULARITY_TIERS = [
  { label: 'Phenomenon', threshold: '500K+ reviews', color: '#f472b6' },
  { label: 'Very High', threshold: '100K+ reviews', color: '#c084fc' },
  { label: 'High', threshold: '25K+ reviews', color: '#60a5fa' },
  { label: 'Medium', threshold: '5K+ reviews', color: '#4ade80' },
  { label: 'Niche', threshold: '500+ reviews', color: '#e0b341' },
]

export function GameScoreSummary({ game }: { game: Game }) {
  const livePrimaryScores = primaryLiveScores(game)
  const livePrimaryCount = (
    game.live_primary_source_count ?? livePrimaryScores.length
  )
  const applicableCount = (
    game.applicable_source_count ?? DEFAULT_APPLICABLE_SOURCE_COUNT
  )
  const sourceAverage = livePrimaryScores.length > 0
    ? Math.round(
        livePrimaryScores.reduce((sum, source) => sum + source.score, 0)
        / livePrimaryScores.length,
      )
    : Math.round(game.metrix_score)
  const totalReviews = livePrimaryScores.reduce(
    (total, source) => total + (source.review_count ?? 0),
    0,
  )
  const popularity = popularitySummary(game)
  const rankStatus = game.is_rankable ? 'Ranked' : 'Unranked'
  const rankDetail = game.is_rankable
    ? 'Eligible for leaderboard ranking.'
    : game.rank_exclusion_reason === 'catalog_only'
      ? 'Waiting for live rating data.'
      : 'Needs more reliable source coverage.'

  return (
    <div className="dp-score-block">
      <div className="dp-score-main">
        <div className="dp-score-ring-wrap">
          <ScoreRing score={Math.round(game.metrix_score)} size="lg" />
        </div>
        <div className="dp-score-meta">
          <span
            className={
              `dp-confidence dp-confidence-${
                (game.confidence_level ?? 'limited').toLowerCase()
              }`
            }
            title={reliabilityCopy(game, livePrimaryCount)}
          >
            {game.confidence_level}
          </span>
          <span className="dp-score-label">GameMetrix Score</span>
          {totalReviews > 0 ? (
            <span className="dp-total-reviews">
              {formatCount(totalReviews)} total reviews
            </span>
          ) : null}
        </div>
      </div>

      <div className="dp-score-stats">
        <div title="Plain average of the live primary source scores.">
          <span>Source avg</span>
          <strong>{sourceAverage}</strong>
        </div>
        <div title={reliabilityCopy(game, livePrimaryCount)}>
          <span>Coverage</span>
          <strong>{livePrimaryCount}/{applicableCount}</strong>
        </div>
        <div title="Score used for leaderboard ordering.">
          <span>Rank score</span>
          <strong>{Math.round(game.rank_score)}</strong>
        </div>
        <div title={popularity.detail}>
          <span>Popularity</span>
          <strong
            style={{
              '--pop-color': popularityColor(popularity.label),
            } as CSSProperties}
            className="dp-stat-pop"
          >
            {popularity.label}
            <PopularityInfo />
          </strong>
        </div>
        <div
          className={game.is_rankable ? '' : 'dp-stat-muted'}
          title={rankDetail}
        >
          <span>Ranking</span>
          <strong>{rankStatus}</strong>
        </div>
      </div>
    </div>
  )
}

function primaryLiveScores(game: Game): SourceScore[] {
  const scoreBySource = new Map(
    game.source_scores.map((source) => [source.source, source]),
  )
  return DETAIL_PRIMARY_SOURCE_ORDER
    .map((source) => scoreBySource.get(source))
    .filter((source): source is SourceScore => (
      source !== undefined
      && source.status === 'live'
      && source.score > 0
    ))
}

function reliabilityCopy(game: Game, livePrimaryCount: number): string {
  const applicableCount = (
    game.applicable_source_count ?? DEFAULT_APPLICABLE_SOURCE_COUNT
  )
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
    .filter((source) => (
      source.status === 'live'
      && REVIEW_VOLUME_SOURCES.has(source.source)
    ))
    .reduce((total, source) => total + (source.review_count ?? 0), 0)
  return {
    label: game.popularity_label ?? 'Untracked',
    detail: reviewCount > 0
      ? `${formatCompactCount(reviewCount)} tracked reviews`
      : 'No reliable volume signal yet',
  }
}

function popularityColor(label: string): string {
  return POPULARITY_TIERS.find((tier) => tier.label === label)?.color
    ?? '#9ca3af'
}

function PopularityInfo() {
  return (
    <button
      type="button"
      className="dp-hltb-info"
      aria-label="Popularity tiers"
      aria-describedby="game-popularity-tooltip"
    >
      <Info size={12} aria-hidden="true" />
      <span
        id="game-popularity-tooltip"
        className="dp-hltb-tip"
        role="tooltip"
      >
        {POPULARITY_TIERS.map((tier) => (
          <span className="dp-hltb-tip-row" key={tier.label}>
            <span style={{ color: tier.color }}>{tier.label}</span>
            <span>{tier.threshold}</span>
          </span>
        ))}
      </span>
    </button>
  )
}
