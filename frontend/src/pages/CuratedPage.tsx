import { Clock3, ExternalLink, Gamepad2, LogIn, Search, Tag } from 'lucide-react'
import { Link } from 'react-router'
import type { RankingGenre } from '../server-api.server'
import { useAccount } from '../state/useAccount'
import { trackProductEvent } from '../services/analytics'
import { smallCoverUrl } from '../utils/coverImage'
import { CURATED_PRIMARY_SOURCES, type CuratedGameCard } from '../utils/curatedCards'
import { formatIsoDate } from '../utils/format'
import { PROTON_TIER_LABELS } from '../utils/proton'
import './CuratedPage.css'

export interface CuratedPageData {
  /** Row-sized projection (`toCuratedCard`), not the backend's full catalog payload. */
  games: CuratedGameCard[]
  total: number
  title: string
  description: string
  canonical: string
  label: string
  updatedAt: string
  /** Loader wall-clock (ms) so server and browser agree on price freshness. */
  renderedAt: number
  /** Genre landing pages to cross-link under Related rankings. */
  genres: RankingGenre[]
}

function itemListJson(data: CuratedPageData) {
  return JSON.stringify({
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'ItemList',
        name: data.title,
        numberOfItems: data.games.length,
        itemListElement: data.games.map((game, index) => ({
          '@type': 'ListItem',
          position: index + 1,
          url: `https://gamemetrix.me/game/${encodeURIComponent(game.slug)}`,
          name: game.title,
        })),
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://gamemetrix.me/' },
          { '@type': 'ListItem', position: 2, name: data.label, item: data.canonical },
        ],
      },
    ],
  }).replace(/</g, '\\u003c')
}

function recentYears(renderedAt: number): number[] {
  const current = new Date(renderedAt).getUTCFullYear()
  return [current, current - 1, current - 2]
}

export function CuratedPage({ data }: { data: CuratedPageData }) {
  const { account, accountsEnabled } = useAccount()
  return (
    <main id="main-content" className="curated-shell">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: itemListJson(data) }} />
      <header className="curated-topbar">
        <a href="/" className="curated-brand">Game<span>Metrix</span></a>
        {/* A plain GET form: works before hydration and lands on the catalog with the query in the URL. */}
        <form className="curated-search" action="/" method="get" role="search">
          <input type="search" name="q" maxLength={120} placeholder="Search games" aria-label="Search games by title" />
          <button type="submit" aria-label="Search"><Search size={15} aria-hidden="true" /></button>
        </form>
        {accountsEnabled || account ? (
          <nav aria-label="Account navigation">
            <Link to={account ? '/account' : '/login'}>{account ? <Gamepad2 size={16} /> : <LogIn size={16} />}{account ? 'Account' : 'Login'}</Link>
          </nav>
        ) : null}
      </header>

      <div className="curated-inner">
        <nav className="curated-breadcrumb" aria-label="Breadcrumb"><Link to="/">Home</Link><span>/</span><span>{data.label}</span></nav>
        <header className="curated-heading">
          <p>{data.label}</p>
          <h1>{data.title}</h1>
          <div>{data.description}</div>
          <small>Updated {formatIsoDate(data.updatedAt, 'long') ?? 'recently'}. Ranked from live source coverage and GameMetrix reliability weighting.</small>
        </header>

        <nav className="curated-links" aria-label="Related rankings">
          <Link to="/best/linux-games">Linux games</Link>
          <Link to="/best/steam-deck-games">Runs well on Linux / Deck</Link>
          <Link to="/best/free-pc-games">Free PC games</Link>
          <Link to="/deals">Best deals</Link>
          {recentYears(data.renderedAt).map((year) => (
            <Link key={year} to={`/best/games/${year}`}>Best of {year}</Link>
          ))}
          {data.genres.map((genre) => (
            <Link key={genre.slug} to={`/best/${genre.slug}-games`}>{genre.name}</Link>
          ))}
        </nav>

        {data.games.length ? (
          <ol className="curated-list">
            {data.games.map((game, index) => {
              const price = game.price
              const proton = game.proton_tier ? PROTON_TIER_LABELS[game.proton_tier] : null
              return (
                <li key={game.slug}>
                  <span className="curated-rank">{index + 1}</span>
                  <Link className="curated-cover" to={`/game/${game.slug}`} aria-label={`Open ${game.title}`}>
                    <img src={game.cover ? smallCoverUrl(game.cover) : '/favicon.svg'} alt="" loading={index < 4 ? 'eager' : 'lazy'} />
                  </Link>
                  <article>
                    <div className="curated-game-head">
                      <div>
                        <Link to={`/game/${game.slug}`}><h2>{game.title}</h2></Link>
                        <p>
                          {game.release_year > 1970 ? (
                            <Link to={`/best/games/${game.release_year}`}>
                              {game.release_year}
                            </Link>
                          ) : 'Release date pending'}
                          {game.developer ? ` · ${game.developer}` : ''}
                        </p>
                      </div>
                      <strong>{game.score}</strong>
                    </div>
                    <div className="curated-scores" aria-label={`${game.title} source scores`}>
                      {CURATED_PRIMARY_SOURCES.map((source, slot) => (
                        <span key={source}><small>{source}</small><b>{game.sourceScores[slot] ?? '—'}</b></span>
                      ))}
                    </div>
                    <div className="curated-context">
                      {proton ? <span className={`is-proton-${game.proton_tier}`}>Linux: {proton}</span> : null}
                      {game.playtimeHours > 0 ? <span><Clock3 size={13} />{game.playtimeHours}h HLTB</span> : null}
                      {price ? <span><Tag size={13} />{price.label}{price.discountPercent > 0 ? ` · ${price.discountPercent}% off` : ''}</span> : null}
                      {price?.url ? <a href={price.url} target="_blank" rel="noopener noreferrer" onClick={() => trackProductEvent('store_outbound', { game_slug: game.slug, store: price.store })}>Store <ExternalLink size={12} /></a> : null}
                    </div>
                  </article>
                </li>
              )
            })}
          </ol>
        ) : <p className="curated-empty">No games currently meet this page's publication threshold.</p>}

        <section className="curated-method">
          <h2>How this list is built</h2>
          <p>GameMetrix keeps Metacritic, OpenCritic, Steam and IGDB as distinct primary score slots. Missing scores remain missing, while <a href="https://rawg.io/" target="_blank" rel="noopener noreferrer">RAWG</a> and other providers appear as supplementary sources. Pages enter this list only after the catalog quality checks for release data, imagery, meaningful summaries, source coverage and decision context pass.</p>
        </section>
      </div>
    </main>
  )
}
