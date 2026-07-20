import { Clock3, ExternalLink, Gamepad2, LogIn, Shield, Tag } from 'lucide-react'
import { Link } from 'react-router'
import { useAccount } from '../state/useAccount'
import { trackProductEvent } from '../services/analytics'
import type { Game, PriceSnapshot } from '../types/game'
import { currentPriceSnapshots } from '../utils/prices'
import { isProtonTier, PROTON_TIER_LABELS } from '../utils/proton'
import { safeExternalUrl } from '../utils/url'
import './CuratedPage.css'

export interface CuratedPageData {
  games: Game[]
  total: number
  title: string
  description: string
  canonical: string
  label: string
  updatedAt: string
}

const PRIMARY_SOURCES = ['Metacritic', 'OpenCritic', 'Steam', 'IGDB'] as const

function bestPrice(prices: PriceSnapshot[]): PriceSnapshot | undefined {
  return currentPriceSnapshots(prices)
    .filter((price) => price.is_free || price.sale_price != null || price.list_price != null)
    .sort((left, right) => Number(left.sale_price ?? left.list_price ?? Infinity) - Number(right.sale_price ?? right.list_price ?? Infinity))[0]
}

function priceText(price: PriceSnapshot | undefined): string | null {
  if (!price) return null
  if (price.is_free || price.sale_price === 0) return 'Free'
  const amount = price.sale_price ?? price.list_price
  if (amount == null) return null
  try { return new Intl.NumberFormat('en-US', { style: 'currency', currency: price.currency }).format(amount) }
  catch { return `${amount.toFixed(2)} ${price.currency}` }
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

export function CuratedPage({ data }: { data: CuratedPageData }) {
  const { account } = useAccount()
  return (
    <main className="curated-shell">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: itemListJson(data) }} />
      <header className="curated-topbar">
        <a href="/" className="curated-brand">Game<span>Metrix</span></a>
        <nav aria-label="Account navigation">
          <Link to={account ? '/account' : '/login'}>{account ? <Gamepad2 size={16} /> : <LogIn size={16} />}{account ? 'Account' : 'Login'}</Link>
          <Link to="/admin"><Shield size={16} />Admin</Link>
        </nav>
      </header>

      <div className="curated-inner">
        <nav className="curated-breadcrumb" aria-label="Breadcrumb"><Link to="/">Home</Link><span>/</span><span>{data.label}</span></nav>
        <header className="curated-heading">
          <p>{data.label}</p>
          <h1>{data.title}</h1>
          <div>{data.description}</div>
          <small>Updated {new Date(data.updatedAt).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}. Ranked from live source coverage and GameMetrix reliability weighting.</small>
        </header>

        <nav className="curated-links" aria-label="Related rankings">
          <Link to="/best/linux-games">Linux games</Link>
          <Link to="/best/steam-deck-games">Steam Deck</Link>
          <Link to="/best/free-pc-games">Free PC games</Link>
          <Link to="/deals">Best deals</Link>
        </nav>

        {data.games.length ? (
          <ol className="curated-list">
            {data.games.map((game, index) => {
              const scores = new Map(game.source_scores.map((score) => [score.source, score]))
              const price = bestPrice(game.price_snapshots ?? [])
              const priceLabel = priceText(price)
              const storeUrl = safeExternalUrl(price?.url)
              const proton = game.proton_tier && isProtonTier(game.proton_tier) ? PROTON_TIER_LABELS[game.proton_tier] : null
              const playtime = game.hltb_main_story_minutes || game.hltb_all_styles_minutes || game.playtime_minutes
              return (
                <li key={game.slug}>
                  <span className="curated-rank">{index + 1}</span>
                  <Link className="curated-cover" to={`/game/${game.slug}`} aria-label={`Open ${game.title}`}>
                    <img src={game.cover_url || game.image_url || '/favicon.svg'} alt="" loading={index < 4 ? 'eager' : 'lazy'} />
                  </Link>
                  <article>
                    <div className="curated-game-head">
                      <div><Link to={`/game/${game.slug}`}><h2>{game.title}</h2></Link><p>{game.release_year > 1970 ? game.release_year : 'Release date pending'}{game.developer ? ` · ${game.developer}` : ''}</p></div>
                      <strong>{Math.round(game.metrix_score)}</strong>
                    </div>
                    <div className="curated-scores" aria-label={`${game.title} source scores`}>
                      {PRIMARY_SOURCES.map((source) => {
                        const score = scores.get(source)
                        return <span key={source}><small>{source}</small><b>{score?.status === 'live' && score.score > 0 ? Math.round(score.score) : '—'}</b></span>
                      })}
                    </div>
                    <div className="curated-context">
                      {proton ? <span className={`is-proton-${game.proton_tier}`}>Linux: {proton}</span> : null}
                      {playtime > 0 ? <span><Clock3 size={13} />{Math.max(1, Math.round(playtime / 60))}h HLTB</span> : null}
                      {priceLabel ? <span><Tag size={13} />{priceLabel}{(price?.discount_percent ?? 0) > 0 ? ` · ${price?.discount_percent}% off` : ''}</span> : null}
                      {storeUrl && price ? <a href={storeUrl} target="_blank" rel="noopener noreferrer" onClick={() => trackProductEvent('store_outbound', { game_slug: game.slug, store: price.store })}>Store <ExternalLink size={12} /></a> : null}
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
