import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { CuratedPage, type CuratedPageData } from '../pages/CuratedPage'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'
import { latestContentUpdate } from '../utils/seo'

export async function loader({ params }: LoaderFunctionArgs): Promise<CuratedPageData> {
  const year = Number(params.year)
  const currentYear = new Date().getUTCFullYear()
  if (!Number.isInteger(year) || year < 1970 || year > currentYear) throw new Response('Not Found', { status: 404 })
  const result = await fetchBackend<GameListResponse>(`/api/seo/curated/year?year=${year}&limit=100`)
  return {
    ...result,
    label: `Games of ${year}`,
    title: `Best Games of ${year}`,
    description: `The strongest ${year} game releases with enough primary score coverage and decision context to pass the GameMetrix publication threshold.`,
    canonical: `https://gamemetrix.me/best/games/${year}`,
    updatedAt: latestContentUpdate(result.games),
  }
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
export default function YearRoute({ loaderData }: { loaderData: CuratedPageData }) { return <CuratedPage data={loaderData} /> }
