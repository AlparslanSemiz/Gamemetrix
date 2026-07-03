export function RatingExplainer() {
  return (
    <div className="about-rating">
      <p className="about-lead">
        GameMetrix pulls scores from multiple independent sources and combines them into one transparent signal.
        Here's exactly how it works.
      </p>

      {/* Sources */}
      <div className="about-block">
        <h3>Rating sources</h3>
        <div className="about-source-list">
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-primary">Metacritic</span>
              <span className="about-badge badge-primary">OpenCritic</span>
            </div>
            <span className="about-source-desc">Professional critic reviews — highest signal quality</span>
          </div>
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-primary">Steam</span>
              <span className="about-badge badge-primary">IGDB</span>
            </div>
            <span className="about-source-desc">Player scores — Steam applies to PC games only</span>
          </div>
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-secondary">RAWG</span>
            </div>
            <span className="about-source-desc">Backup only — fills a missing primary slot at 70% weight</span>
          </div>
          <div className="about-source-row">
            <div className="about-badges">
              <span className="about-badge badge-support">SteamSpy</span>
              <span className="about-badge badge-support">CheapShark</span>
              <span className="about-badge badge-support">FreeToGame</span>
            </div>
            <span className="about-source-desc">Support data only — popularity, pricing, availability. Never affect the score.</span>
          </div>
        </div>
      </div>

      {/* Score */}
      <div className="about-block">
        <h3>GameMetrix Score</h3>
        <p>
          Up to 4 sources averaged with equal weight (25% each). If a primary source
          is unavailable for a game, RAWG can fill the gap at reduced weight.
        </p>
        <div className="about-score-demo">
          {[['Metacritic', 96], ['OpenCritic', 94], ['Steam', 92], ['IGDB', 90]].map(([src, val]) => (
            <div key={src as string} className="about-score-row">
              <span className="about-score-src">{src}</span>
              <div className="about-score-track">
                <div className="about-score-fill" style={{ width: `${val}%` }} />
              </div>
              <strong>{val}</strong>
            </div>
          ))}
          <div className="about-score-result">
            <span>GameMetrix Score</span>
            <span className="about-score-eq">= (96 + 94 + 92 + 90) ÷ 4</span>
            <strong className="about-score-final">93</strong>
          </div>
        </div>
      </div>

      {/* Rank */}
      <div className="about-block">
        <h3>
          GameMetrix Rank
          <span className="about-tag">Default sort</span>
        </h3>
        <p>
          A game showing 96 from one source shouldn't outrank Elden Ring with four.
          Rank shrinks the score toward a neutral baseline (70) based on how much
          reliable data exists. The card score never changes — only the ordering.
        </p>
        <div className="about-strength-table">
          <div className="about-strength-row">
            <span className="about-str-badge str-strong">Strong</span>
            <span className="about-str-desc">3–4 sources, critic + player mix</span>
            <span className="about-str-example">96 → <strong>96.0</strong></span>
          </div>
          <div className="about-strength-row">
            <span className="about-str-badge str-solid">Solid</span>
            <span className="about-str-desc">2+ sources or strong single coverage</span>
            <span className="about-str-example">96 → <strong>93.4</strong></span>
          </div>
          <div className="about-strength-row">
            <span className="about-str-badge str-limited">Limited</span>
            <span className="about-str-desc">1 source or backup-only data</span>
            <span className="about-str-example">96 → <strong>86.9</strong></span>
          </div>
          <div className="about-strength-row">
            <span className="about-str-badge str-catalog">Catalog</span>
            <span className="about-str-desc">No live rating data yet</span>
            <span className="about-str-example">Excluded from top lists</span>
          </div>
        </div>
      </div>

      {/* Platform fairness */}
      <div className="about-block">
        <h3>Platform fairness</h3>
        <p>
          Steam is only counted for PC games. A Nintendo exclusive missing Steam is not penalized —
          its applicable sources are Metacritic, OpenCritic, and IGDB, and full coverage across
          those three still qualifies as <strong>Data Strong</strong>.
        </p>
      </div>
    </div>
  )
}
