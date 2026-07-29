import type { MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { fetchBackend } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'
import { latestContentUpdate } from '../utils/seo'

export async function loader(): Promise<CuratedPageData> {
  const result = await fetchBackend<CatalogGameListResponse>('/api/seo/curated/deals?limit=100')
  return {
    ...result,
    label: 'PC game deals',
    title: 'Best PC Game Deals',
    description: 'High-signal PC games with a tracked discount or free offer, ranked by quality and source reliability rather than discount alone.',
    canonical: 'https://gamemetrix.me/deals',
    updatedAt: latestContentUpdate(result.games),
  }
}

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => loaderData ? [
  { title: 'Best PC Game Deals | GameMetrix' },
  { name: 'description', content: loaderData.description },
  { name: 'robots', content: loaderData.games.length >= 5 && !location.search ? 'index,follow,max-image-preview:large' : 'noindex,follow' },
  { tagName: 'link', rel: 'canonical', href: loaderData.canonical },
  { property: 'og:title', content: loaderData.title },
  { property: 'og:description', content: loaderData.description },
  { property: 'og:type', content: 'website' },
  { property: 'og:url', content: loaderData.canonical },
  { name: 'twitter:card', content: 'summary' },
  { name: 'twitter:title', content: loaderData.title },
  { name: 'twitter:description', content: loaderData.description },
] : []
export const headers = () => ({ 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' })
export default function DealsRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
