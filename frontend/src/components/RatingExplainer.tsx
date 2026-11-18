import type { ReactNode } from 'react'
import './RatingExplainer.css'

const SOURCE_GROUPS = [
  {
    badgeClass: 'badge-primary',
    description: 'Professional critic reviews — highest signal quality',
    sources: ['Metacritic', 'OpenCritic'],
  },
  {
    badgeClass: 'badge-primary',
    description: 'Player scores — Steam applies to PC games only',
    sources: ['Steam', 'IGDB'],
  },
  {
    badgeClass: 'badge-secondary',
    description: 'Supplementary context and metadata — never fills a primary score slot',
    sources: ['RAWG'],
  },
  {
    badgeClass: 'badge-support',
    description: 'Support data only — popularity, pricing, availability. Never affect the score.',
    sources: ['SteamSpy', 'CheapShark', 'FreeToGame'],
  },
]

function RatingSources() {
  return (
    <div className="about-block">
      <h2>Rating sources</h2>
      <div className="about-source-list">
        {SOURCE_GROUPS.map((group) => (
          <div className="about-source-row" key={group.sources.join('-')}>
            <div className="about-badges">
              {group.sources.map((source) => (
                <span className={`about-badge ${group.badgeClass}`} key={source}>
                  {source}
                </span>
              ))}
            </div>
            <span className="about-source-desc">{group.description}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const SOURCE_WEIGHT_ROWS: Array<[string, string]> = [
  ['Metacritic', '32%'],
  ['OpenCritic', '28%'],
  ['Steam', '25%'],
  ['IGDB', '15%'],
]

function ScoreExplanation() {
  return (
    <div className="about-block">
      <h2>GameMetrix Score</h2>
      <p>
        The score is a <strong>weighted average</strong> of the live primary sources, pulled toward a
        neutral 70 when the evidence is thin. Missing primary scores stay visibly missing; RAWG and
        support providers never substitute for them.
      </p>
      <ol className="about-steps">
        <li>
          <strong>Weighted average.</strong> Each live primary score is weighted:{' '}
          {SOURCE_WEIGHT_ROWS.map(([source, weight]) => `${source} ${weight}`).join(', ')}. Weights are
          renormalised over the sources a game actually has.
        </li>
        <li>
          <strong>Reliability, 0.46 to 1.00.</strong> Start from coverage (1 source 0.62, 2 sources 0.78,
          3 sources 0.90, 4 sources 1.00), add a critic-and-player balance adjustment (both +0.03, critic only
          −0.04, player only −0.06) and a review-volume adjustment (100,000+ reviews +0.04, 10,000+ +0.02,
          500+ +0.01, fewer −0.02, none −0.04). Each coverage level also has a ceiling (1 source 0.68,
          2 sources 0.84, 3 sources 0.94).
        </li>
        <li>
          <strong>Pull and penalty.</strong>{' '}
          <code>score = average × reliability + 70 × (1 − reliability) − 6 × (1 − reliability)</code>.
          Full reliability leaves the average untouched; every missing bit of evidence moves the score
          toward 70 and then takes a small uncertainty penalty.
        </li>
      </ol>
      <div className="about-score-demo">
        {[['Metacritic', 96], ['OpenCritic', 94], ['Steam', 92], ['IGDB', 90]].map(([source, value]) => (
          <div key={source as string} className="about-score-row">
            <span className="about-score-src">{source}</span>
            <div className="about-score-track">
              <div className="about-score-fill" style={{ width: `${value}%` }} />
            </div>
            <strong>{value}</strong>
          </div>
        ))}
        <div className="about-score-result">
          <span>Four sources</span>
          <span className="about-score-eq">
            average 93.54 (0.32×96 + 0.28×94 + 0.25×92 + 0.15×90), reliability 1.00
          </span>
          <strong className="about-score-final">93.5</strong>
        </div>
      </div>
    </div>
  )
}

function RankExplanation() {
  return (
    <div className="about-block">
      <h2>Why the same 96 can score differently <span className="about-tag">Default sort</span></h2>
      <p>
        A 96 from one source should not outrank a game with four agreeing sources. The default
        &ldquo;GameMetrix Rank&rdquo; order is this same score; there is no second adjustment. Examples
        with the same 96 from Metacritic:
      </p>
      <div className="about-strength-table">
        <RankRow badge="4 sources" className="str-strong" description="Metacritic 96, OpenCritic 94, Steam 92, IGDB 90; 150,000 reviews">
          reliability 1.00 → <strong>93.5</strong>
        </RankRow>
        <RankRow badge="2 sources" className="str-solid" description="Metacritic 96 + Steam 92; about 3,000 reviews">
          reliability 0.82 → <strong>88.8</strong>
        </RankRow>
        <RankRow badge="1 source" className="str-limited" description="Metacritic 96 only; 80 reviews">
          reliability 0.56 → <strong>81.9</strong>
        </RankRow>
        <RankRow badge="No score" className="str-catalog" description="No live primary rating yet">
          Excluded from top lists
        </RankRow>
      </div>
      <p>
        To appear in ranked lists a game needs two live primary sources, or one critic plus one player
        source, or one source backed by awards. The Strong / Solid / Limited / Catalog label on a game
        page describes how much data stands behind its score.
      </p>
    </div>
  )
}

function RankRow({
  badge,
  children,
  className,
  description,
}: {
  badge: string
  children: ReactNode
  className: string
  description: string
}) {
  return (
    <div className="about-strength-row">
      <span className={`about-str-badge ${className}`}>{badge}</span>
      <span className="about-str-desc">{description}</span>
      <span className="about-str-example">{children}</span>
    </div>
  )
}

export function RatingExplainer() {
  return (
    <div className="about-rating">
      <p className="about-lead">
        GameMetrix is an independent comparison catalog. It brings named third-party
        scores and practical PC decision signals together; no listed provider endorses
        GameMetrix. Here is exactly how the comparison works.
      </p>
      <div className="about-block">
        <h2>What GameMetrix is</h2>
        <p>
          The catalog is designed to help people compare a game&apos;s critical reception,
          player reception, Linux and Steam Deck compatibility, estimated playtime and
          current price context in one place. It is a comparison tool, not a review
          publisher, store or substitute for the linked source pages.
        </p>
      </div>
      <p className="about-byline">
        Built by <a href="https://alparslansemiz.com/" rel="noopener">Alparslan Semiz</a>.
      </p>
      <RatingSources />
      <ScoreExplanation />
      <RankExplanation />
      <div className="about-block">
        <h2>Platform fairness</h2>
        <p>
          Steam is only counted for PC games. A Nintendo exclusive missing Steam is not penalized —
          its applicable sources are Metacritic, OpenCritic, and IGDB, and full coverage across
          those three still qualifies as <strong>Data Strong</strong>.
        </p>
      </div>
      <div className="about-block">
        <h2>How data is processed</h2>
        <p>
          Automated imports normalize provider identifiers, score scales and catalog
          metadata. Every primary score stays attached to its named source; a missing
          score remains missing instead of being estimated. Games must pass the published
          quality checks before they enter search-facing rankings.
        </p>
      </div>
      <div className="about-block">
        <h2>Limitations and updates</h2>
        <p>
          Provider data can be delayed, incomplete or changed after an import. Compatibility,
          prices and playtime are snapshots rather than guarantees. Each game page names and
          links its sources so important decisions can be checked at the source; GameMetrix
          refreshes available data but does not claim real-time completeness.
        </p>
      </div>
    </div>
  )
}
