import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { clientForwardHeaders, fetchBackend, loadTopGenres, type RankingGenre } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'
import { sharedCacheHeaders } from '../utils/cacheHeaders'
import { curatedMetaTags } from '../utils/curatedMeta'
import { curatedListPayload } from '../utils/curatedCards'

const PAGES = {
  'linux-games': {
    api: 'linux',
    label: 'Linux gaming',
    title: 'Best Linux Games',
    description: 'Top PC games with native Linux support or tracked Proton compatibility, ranked with source coverage and data reliability in view.',
  },
  'steam-deck-games': {
    api: 'steam-deck',
    label: 'Runs well on Linux / Steam Deck',
    title: 'Runs Well on Linux & Steam Deck (ProtonDB)',
    description: 'Top-ranked games that ProtonDB players report as running well on Linux (native, Platinum, Gold or Silver). This is community ProtonDB data, not Valve\'s Deck Verified status, which GameMetrix does not track. Check the Steam page before you buy.',
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
async function loadGenrePage(collection: string, init: RequestInit, related: RankingGenre[]): Promise<CuratedPageData | null> {
  if (!collection.endsWith(GENRE_SUFFIX)) return null
  const slug = collection.slice(0, -GENRE_SUFFIX.length)
  if (!slug) return null

  const { genres } = await fetchBackend<{ genres: SeoGenre[] }>('/api/seo/genres', init)
  const genre = genres.find((entry) => entry.slug === slug)
  if (!genre) return null

  const result = await fetchBackend<CatalogGameListResponse>(
    `/api/seo/curated/genre?genre=${encodeURIComponent(slug)}&limit=100`,
    init,
  )
  return {
    ...curatedListPayload(result, Date.now()),
    label: genre.name,
    title: `Best ${genre.name} Games`,
    description: `The highest-rated ${genre.name} games, ranked by a reliability-weighted score across Metacritic, OpenCritic, IGDB and Steam — with Linux compatibility and playtime alongside.`,
    canonical: `https://gamemetrix.me/best/${collection}`,
    genres: related,
  }
}

export async function loader({ params, request }: LoaderFunctionArgs): Promise<CuratedPageData> {
  const init: RequestInit = { signal: request.signal, headers: clientForwardHeaders(request) }
  const key = params.collection as keyof typeof PAGES
  const page = PAGES[key]
  const genres = await loadTopGenres(init)
  if (page) {
    const result = await fetchBackend<CatalogGameListResponse>(`/api/seo/curated/${page.api}?limit=100`, init)
    return { ...curatedListPayload(result, Date.now()), ...page, canonical: `https://gamemetrix.me/best/${key}`, genres }
  }

  const genrePage = await loadGenrePage(String(params.collection ?? ''), init, genres)
  if (!genrePage) throw new Response('Not Found', { status: 404 })
  return genrePage
}

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => loaderData
  ? curatedMetaTags(loaderData, location.search, `${loaderData.title} | GameMetrix`)
  : []

export const headers = sharedCacheHeaders
export default function CuratedRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
