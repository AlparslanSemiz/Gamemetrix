import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { clientForwardHeaders, fetchBackend, loadTopGenres } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'
import { sharedCacheHeaders } from '../utils/cacheHeaders'
import { curatedMetaTags } from '../utils/curatedMeta'
import { curatedListPayload } from '../utils/curatedCards'

export async function loader({ params, request }: LoaderFunctionArgs): Promise<CuratedPageData> {
  const year = Number(params.year)
  const currentYear = new Date().getUTCFullYear()
  if (!Number.isInteger(year) || year < 1970 || year > currentYear) throw new Response('Not Found', { status: 404 })
  const init = { signal: request.signal, headers: clientForwardHeaders(request) }
  const [result, genres] = await Promise.all([
    fetchBackend<CatalogGameListResponse>(`/api/seo/curated/year?year=${year}&limit=100`, init),
    loadTopGenres(init),
  ])
  return {
    ...curatedListPayload(result, Date.now()),
    label: `Games of ${year}`,
    title: `Best Games of ${year}`,
    description: `The strongest ${year} game releases with enough primary score coverage and decision context to pass the GameMetrix publication threshold.`,
    canonical: `https://gamemetrix.me/best/games/${year}`,
    genres,
  }
}

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => loaderData
  ? curatedMetaTags(loaderData, location.search, `${loaderData.title} | GameMetrix`)
  : []
export const headers = sharedCacheHeaders
export default function YearRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
