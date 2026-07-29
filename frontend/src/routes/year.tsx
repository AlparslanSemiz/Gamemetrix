import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { fetchBackend } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'
import { latestContentUpdate } from '../utils/seo'

export async function loader({ params }: LoaderFunctionArgs): Promise<CuratedPageData> {
  const year = Number(params.year)
  const currentYear = new Date().getUTCFullYear()
  if (!Number.isInteger(year) || year < 1970 || year > currentYear) throw new Response('Not Found', { status: 404 })
  const result = await fetchBackend<CatalogGameListResponse>(`/api/seo/curated/year?year=${year}&limit=100`)
  return {
    ...result,
    label: `Games of ${year}`,
    title: `Best Games of ${year}`,
    description: `The strongest ${year} game releases with enough primary score coverage and decision context to pass the GameMetrix publication threshold.`,
    canonical: `https://gamemetrix.me/best/games/${year}`,
    updatedAt: latestContentUpdate(result.games),
  }
}

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => loaderData ? [
  { title: `${loaderData.title} | GameMetrix` },
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
export default function YearRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
