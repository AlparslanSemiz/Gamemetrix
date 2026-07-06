import { type CSSProperties, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { SeriesGameItem } from '../types/game'
import { getSeriesGames } from '../services/games'
import { scoreColor } from '../utils/scoreColors'

// Self-fetching "More from this series" strip. Renders nothing while loading
// or when the game has no franchise siblings, so it can be dropped into any
// layout without the parent tracking its state.
export function SeriesRow({ slug }: { slug: string }) {
  const [games, setGames] = useState<SeriesGameItem[]>([])

  useEffect(() => {
    let active = true
    setGames([])
    getSeriesGames(slug)
      .then((response) => {
        if (active) setGames(response.games)
      })
      .catch(() => {
        if (active) setGames([])
      })
    return () => {
      active = false
    }
  }, [slug])

  if (games.length === 0) return null

  return (
    <section className="series-row" aria-label="More from this series">
      <h2 className="series-row-title">More from this series</h2>
      <div className="series-row-scroller">
        {games.map((item) => (
          <Link key={item.slug} to={`/game/${item.slug}`} className="series-tile" title={item.title}>
            <div className="series-tile-cover">
              {item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : null}
              {item.metrix_score > 0 ? (
                <span
                  className="series-tile-score"
                  style={{ '--score-color': scoreColor(Math.round(item.metrix_score)) } as CSSProperties}
                >
                  {Math.round(item.metrix_score)}
                </span>
              ) : null}
            </div>
            <strong className="series-tile-name">{item.title}</strong>
            <span className="series-tile-year">{item.release_year > 1970 ? item.release_year : 'TBA'}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}
