import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { clientForwardHeaders, fetchBackend, loadTopGenres } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'
import { sharedCacheHeaders } from '../utils/cacheHeaders'
import { curatedMetaTags } from '../utils/curatedMeta'
import { latestContentUpdate } from '../utils/seo'

export async function loader({ request }: LoaderFunctionArgs): Promise<CuratedPageData> {
  const init = { signal: request.signal, headers: clientForwardHeaders(request) }
  const [result, genres] = await Promise.all([
    fetchBackend<CatalogGameListResponse>('/api/seo/curated/deals?limit=100', init),
    loadTopGenres(init),
  ])
  return {
    ...result,
    label: 'PC game deals',
    title: 'Best PC Game Deals',
    description: 'High-signal PC games with a tracked discount or free offer, ranked by quality and source reliability rather than discount alone.',
    canonical: 'https://gamemetrix.me/deals',
    updatedAt: latestContentUpdate(result.games),
    renderedAt: Date.now(),
    genres,
  }
}

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => loaderData
  ? curatedMetaTags(loaderData, location.search, 'Best PC Game Deals | GameMetrix')
  : []
export const headers = sharedCacheHeaders
export default function DealsRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
