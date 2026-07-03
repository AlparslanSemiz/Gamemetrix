import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { PlatformIcons } from '../../components/PlatformIcons'
import type { Game } from '../../types/game'
import { scoreColor } from '../../utils/scoreColors'
import { normalizeSignal } from './format'

export const SIMILAR_DISPLAY_LIMIT = 10

export function SimilarGamesSection({
  game,
  catalogGames,
  loading = false,
}: {
  game: Game
  catalogGames: Game[]
  loading?: boolean
}) {
  const rawgItems = game.similar_games.filter((item) => item.title !== game.title)
  const catalogItems = catalogGames.filter((item) => item.slug !== game.slug)
  const catalogDisplayItems = catalogItems.slice(0, SIMILAR_DISPLAY_LIMIT)
  const displayedTitles = new Set(catalogDisplayItems.map((item) => normalizeSignal(item.title)))
  const rawgDisplayItems = rawgItems
    .filter((item) => !displayedTitles.has(normalizeSignal(item.title)))
    .slice(0, Math.max(SIMILAR_DISPLAY_LIMIT - catalogDisplayItems.length, 0))
  const hasItems = rawgItems.length > 0 || catalogItems.length > 0

  if (!hasItems && loading) {
    return (
      <section className="dp-similar-section" aria-labelledby="similar-games-title">
        <div className="dp-similar-heading">
          <h2 id="similar-games-title">Games like {game.title}</h2>
        </div>
        <p className="dp-no-scores">Finding similar games…</p>
      </section>
    )
  }

  if (!hasItems) return null

  return (
    <section className="dp-similar-section" aria-labelledby="similar-games-title">
      <div className="dp-similar-heading">
        <h2 id="similar-games-title">Games like {game.title}</h2>
      </div>
      <div className="dp-similar-grid">
        {catalogDisplayItems.map((item) => (
          <Link
            key={item.slug}
            to={`/game/${item.slug}`}
            className="dp-similar-card"
          >
            <div className="dp-similar-cover">
              {item.cover_url || item.image_url ? (
                <img src={item.cover_url || item.image_url || ''} alt="" loading="lazy" />
              ) : null}
              <span
                className="dp-similar-score"
                style={{ '--score-color': scoreColor(Math.round(item.metrix_score)) } as CSSProperties}
              >
                {Math.round(item.metrix_score)}
              </span>
            </div>
            <div className="dp-similar-body">
              <PlatformIcons platforms={item.platforms} mode="compact" maxVisible={5} />
              <strong>{item.title}</strong>
              <span>{item.release_year > 1970 ? item.release_year : 'TBA'}</span>
            </div>
          </Link>
        ))}
        {rawgDisplayItems.map((item) => (
          <a
            key={`${item.title}-${item.id ?? item.slug ?? ''}`}
            href={item.url ?? '#'}
            target={item.url ? '_blank' : undefined}
            rel={item.url ? 'noreferrer' : undefined}
            className="dp-similar-card"
          >
            <div className="dp-similar-cover">
              {item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : null}
              {item.metacritic_score ? (
                <span
                  className="dp-similar-score"
                  style={{ '--score-color': scoreColor(Math.round(item.metacritic_score)) } as CSSProperties}
                >
                  {Math.round(item.metacritic_score)}
                </span>
              ) : null}
            </div>
            <div className="dp-similar-body">
              <strong>{item.title}</strong>
              <span>{item.release_year && item.release_year > 1970 ? item.release_year : 'TBA'}</span>
            </div>
          </a>
        ))}
      </div>
    </section>
  )
}
