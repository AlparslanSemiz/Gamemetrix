import type { CSSProperties } from 'react'
import type { Game } from '../../types/game'
import { scoreColor, scoreColorRgb } from '../../utils/scoreColors'

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function displayDlcTitle(gameTitle: string, dlcTitle: string) {
  const cleaned = dlcTitle
    .replace(new RegExp(`^${escapeRegExp(gameTitle)}\\s*[-:–—]\\s*`, 'i'), '')
    .trim()
  return cleaned || dlcTitle
}

export function DlcSection({ game }: { game: Game }) {
  if (game.dlcs.length === 0) return null
  return (
    <section className="dp-dlc-section" aria-labelledby="dlc-title">
      <div className="dp-similar-heading">
        <h2 id="dlc-title">DLCs & expansions</h2>
        <small>{game.dlcs.length} add-ons</small>
      </div>
      <div className="dp-dlc-grid">
        {game.dlcs.slice(0, 12).map((item) => {
          const score = item.metacritic_score ?? (item.rating ? Math.round(item.rating * 20) : null)
          const title = displayDlcTitle(game.title, item.title)
          const accentScore = Math.round(score ?? game.rank_score)
          const cardStyle = {
            '--score-color': scoreColor(accentScore),
            '--score-rgb': scoreColorRgb(accentScore),
          } as CSSProperties
          const body = (
            <>
              <div className="dp-dlc-cover">
                {item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : null}
                {score ? (
                  <span
                    className="dp-similar-score"
                    style={{ '--score-color': scoreColor(Math.round(score)) } as CSSProperties}
                  >
                    {Math.round(score)}
                  </span>
                ) : null}
              </div>
              <div className="dp-dlc-body">
                <span>{item.type ? item.type.toUpperCase() : 'DLC'}</span>
                <strong title={item.title}>{title}</strong>
                <small>{item.release_year && item.release_year > 1970 ? item.release_year : 'Release date not tracked'}</small>
              </div>
            </>
          )
          return item.url ? (
            <a
              key={`${item.title}-${item.id ?? item.slug ?? ''}`}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="dp-dlc-card"
              style={cardStyle}
            >
              {body}
            </a>
          ) : (
            <div key={`${item.title}-${item.id ?? item.slug ?? ''}`} className="dp-dlc-card" style={cardStyle}>
              {body}
            </div>
          )
        })}
      </div>
    </section>
  )
}
