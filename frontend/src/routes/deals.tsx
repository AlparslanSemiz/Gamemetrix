import type { MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { fetchBackend } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'
import { curatedMetaTags } from '../utils/curatedMeta'
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

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => loaderData
  ? curatedMetaTags(loaderData, location.search, 'Best PC Game Deals | GameMetrix')
  : []
export const headers = () => ({ 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' })
export default function DealsRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
