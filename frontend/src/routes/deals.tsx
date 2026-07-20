import type { MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'
import { latestContentUpdate } from '../utils/seo'

export async function loader(): Promise<CuratedPageData> {
  const result = await fetchBackend<GameListResponse>('/api/seo/curated/deals?limit=100')
  return {
    ...result,
    label: 'PC game deals',
    title: 'Best PC Game Deals',
    description: 'High-signal PC games with a tracked discount or free offer, ranked by quality and source reliability rather than discount alone.',
    canonical: 'https://gamemetrix.me/deals',
    updatedAt: latestContentUpdate(result.games),
  }
}

export const meta: MetaFunction<typeof loader> = ({ data, location }) => data ? [
  { title: 'Best PC Game Deals | GameMetrix' },
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
export default function DealsRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
