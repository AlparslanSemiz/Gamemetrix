import type { Game } from '../types/game'
import { ACTIONABLE_PRICE_MAX_AGE_MS, currentPriceSnapshots } from '../utils/prices'
import { safeExternalUrl } from '../utils/url'

function validHttpUrl(value: string | null | undefined): string | undefined {
  return safeExternalUrl(value) ?? undefined
}

function jsonForScript(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c')
}

export function GameStructuredData({ game }: { game: Game }) {
  const canonical = `https://gamemetrix.me/game/${encodeURIComponent(game.slug)}`
  const structuredRating = ['Steam', 'IGDB']
    .map((source) => game.source_scores.find((score) => score.source === source))
    .find((score) => (
      score?.status === 'live'
      && Number.isFinite(score.score)
      && score.score > 0
      && score.score <= 100
      && Number.isInteger(score.review_count ?? 0)
      && (score.review_count ?? 0) > 0
    ))
  const price = currentPriceSnapshots(game.price_snapshots ?? [], ACTIONABLE_PRICE_MAX_AGE_MS)
    .filter((entry) => entry.is_free || entry.sale_price != null || entry.list_price != null)
    .sort((left, right) => Number(left.sale_price ?? left.list_price ?? Infinity) - Number(right.sale_price ?? right.list_price ?? Infinity))[0]
  const offerPrice = price?.is_free ? 0 : price?.sale_price ?? price?.list_price
  const image = validHttpUrl(game.cover_url) ?? validHttpUrl(game.image_url)
  const website = validHttpUrl(game.website_url)

  const entity: Record<string, unknown> = {
    '@type': ['VideoGame', 'SoftwareApplication'],
    '@id': `${canonical}#game`,
    name: game.title,
    url: canonical,
    description: game.summary,
    applicationCategory: 'GameApplication',
    datePublished: game.release_year > 1970 ? game.release_date : undefined,
    image,
    genre: game.genres.length ? game.genres : undefined,
    operatingSystem: game.platforms.length ? game.platforms : undefined,
    author: game.developer ? { '@type': 'Organization', name: game.developer } : undefined,
    publisher: game.publisher ? { '@type': 'Organization', name: game.publisher } : undefined,
    sameAs: website ? [website] : undefined,
  }
  if (structuredRating) {
    entity.aggregateRating = {
      '@type': 'AggregateRating',
      ratingValue: Math.round(structuredRating.score * 10) / 10,
      bestRating: 100,
      worstRating: 0,
      ratingCount: structuredRating.review_count,
    }
  }
  if (offerPrice != null && price?.currency) {
    entity.offers = {
      '@type': 'Offer',
      price: offerPrice,
      priceCurrency: price.currency,
      availability: 'https://schema.org/InStock',
      url: validHttpUrl(price.url) ?? canonical,
    }
  }

  type Crumb = { '@type': 'ListItem'; position: number; name: string; item: string }
  const crumbs: Crumb[] = [
    { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://gamemetrix.me/' },
  ]
  if (game.seo_genre) {
    crumbs.push({
      '@type': 'ListItem',
      position: crumbs.length + 1,
      name: game.seo_genre.name,
      item: `https://gamemetrix.me/best/${game.seo_genre.slug}-games`,
    })
  }
  crumbs.push({ '@type': 'ListItem', position: crumbs.length + 1, name: game.title, item: canonical })

  const graph = {
    '@context': 'https://schema.org',
    '@graph': [
      entity,
      {
        '@type': 'BreadcrumbList',
        '@id': `${canonical}#breadcrumb`,
        itemListElement: crumbs,
      },
    ],
  }
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonForScript(graph) }} />
}
