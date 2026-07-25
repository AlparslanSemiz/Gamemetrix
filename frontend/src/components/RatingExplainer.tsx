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
      <h3>Rating sources</h3>
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

function ScoreExplanation() {
  return (
    <div className="about-block">
      <h3>GameMetrix Score</h3>
      <p>
        Up to four named primary sources are combined. Missing primary scores remain visibly missing;
        RAWG and support providers never substitute for them.
      </p>
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
          <span>GameMetrix Score</span>
          <span className="about-score-eq">= (96 + 94 + 92 + 90) ÷ 4</span>
          <strong className="about-score-final">93</strong>
        </div>
      </div>
    </div>
  )
}

function RankExplanation() {
  return (
    <div className="about-block">
      <h3>GameMetrix Rank <span className="about-tag">Default sort</span></h3>
      <p>
        A game showing 96 from one source shouldn't outrank Elden Ring with four.
        Rank shrinks the score toward a neutral baseline (70) based on how much
        reliable data exists. The card score never changes — only the ordering.
      </p>
      <div className="about-strength-table">
        <RankRow badge="Strong" className="str-strong" description="3–4 sources, critic + player mix">
          96 → <strong>96.0</strong>
        </RankRow>
        <RankRow badge="Solid" className="str-solid" description="2+ sources or strong single coverage">
          96 → <strong>93.4</strong>
        </RankRow>
        <RankRow badge="Limited" className="str-limited" description="1 source or backup-only data">
          96 → <strong>86.9</strong>
        </RankRow>
        <RankRow badge="Catalog" className="str-catalog" description="No live rating data yet">
          Excluded from top lists
        </RankRow>
      </div>
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
        <h3>What GameMetrix is</h3>
        <p>
          The catalog is designed to help people compare a game&apos;s critical reception,
          player reception, Linux and Steam Deck compatibility, estimated playtime and
          current price context in one place. It is a comparison tool, not a review
          publisher, store or substitute for the linked source pages.
        </p>
      </div>
      <RatingSources />
      <ScoreExplanation />
      <RankExplanation />
      <div className="about-block">
        <h3>Platform fairness</h3>
        <p>
          Steam is only counted for PC games. A Nintendo exclusive missing Steam is not penalized —
          its applicable sources are Metacritic, OpenCritic, and IGDB, and full coverage across
          those three still qualifies as <strong>Data Strong</strong>.
        </p>
      </div>
      <div className="about-block">
        <h3>How data is processed</h3>
        <p>
          Automated imports normalize provider identifiers, score scales and catalog
          metadata. Every primary score stays attached to its named source; a missing
          score remains missing instead of being estimated. Games must pass the published
          quality checks before they enter search-facing rankings.
        </p>
      </div>
      <div className="about-block">
        <h3>Limitations and updates</h3>
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
import type { ReactNode } from 'react'
