import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'
import { latestContentUpdate } from '../utils/seo'

const PAGES = {
  'linux-games': {
    api: 'linux',
    label: 'Linux gaming',
    title: 'Best Linux Games',
    description: 'Top PC games with native Linux support or tracked Proton compatibility, ranked with source coverage and data reliability in view.',
  },
  'steam-deck-games': {
    api: 'steam-deck',
    label: 'Steam Deck',
    title: 'Best Steam Deck Games',
    description: 'Strong games with a usable Proton compatibility signal for Steam Deck and Linux players.',
  },
  'free-pc-games': {
    api: 'free',
    label: 'Free PC games',
    title: 'Best Free PC Games',
    description: 'Quality-ranked PC games currently tracked as free, with their four primary score slots kept separate.',
  },
} as const

const GENRE_SUFFIX = '-games'

interface SeoGenre {
  slug: string
  name: string
  count: number
}

/** Genre landing pages are derived from live catalogue data, not a hand-written list. */
async function loadGenrePage(collection: string): Promise<CuratedPageData | null> {
  if (!collection.endsWith(GENRE_SUFFIX)) return null
  const slug = collection.slice(0, -GENRE_SUFFIX.length)
  if (!slug) return null

  const { genres } = await fetchBackend<{ genres: SeoGenre[] }>('/api/seo/genres')
  const genre = genres.find((entry) => entry.slug === slug)
  if (!genre) return null

  const result = await fetchBackend<GameListResponse>(
    `/api/seo/curated/genre?genre=${encodeURIComponent(slug)}&limit=100`,
  )
  return {
    ...result,
    label: genre.name,
    title: `Best ${genre.name} Games`,
    description: `The highest-rated ${genre.name} games, ranked by a reliability-weighted score across Metacritic, OpenCritic, IGDB and Steam — with Linux compatibility and playtime alongside.`,
    canonical: `https://gamemetrix.me/best/${collection}`,
    updatedAt: latestContentUpdate(result.games),
  }
}

export async function loader({ params }: LoaderFunctionArgs): Promise<CuratedPageData> {
  const key = params.collection as keyof typeof PAGES
  const page = PAGES[key]
  if (page) {
    const result = await fetchBackend<GameListResponse>(`/api/seo/curated/${page.api}?limit=100`)
    return { ...result, ...page, canonical: `https://gamemetrix.me/best/${key}`, updatedAt: latestContentUpdate(result.games) }
  }

  const genrePage = await loadGenrePage(String(params.collection ?? ''))
  if (!genrePage) throw new Response('Not Found', { status: 404 })
  return genrePage
}

export const meta: MetaFunction<typeof loader> = ({ data, location }) => data ? [
  { title: `${data.title} | GameMetrix` },
  { name: 'description', content: data.description },
  { name: 'robots', content: data.games.length >= 5 && !location.search ? 'index,follow,max-image-preview:large' : 'noindex,follow' },
  { tagName: 'link', rel: 'canonical', href: data.canonical },
  { property: 'og:title', content: data.title },
  { property: 'og:description', content: data.description },
  { property: 'og:type', content: 'website' },
  { property: 'og:url', content: data.canonical },
  { name: 'twitter:card', content: 'summary' },
  { name: 'twitter:title', content: data.title },
  { name: 'twitter:description', content: data.description },
] : []

export const headers = () => ({ 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' })
export default function CuratedRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
