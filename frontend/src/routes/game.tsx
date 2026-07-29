import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { GameStructuredData } from '../components/GameStructuredData'
import { GameDetailPage } from '../pages/GameDetailPage'
import { BackendResponseError, fetchBackend } from '../server-api.server'
import type { Game } from '../types/game'

export async function loader({ params, request }: LoaderFunctionArgs): Promise<Game> {
  const slug = params.slug ?? ''
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Response('Not Found', { status: 404 })
  try {
    return await fetchBackend<Game>(
      `/api/games/${encodeURIComponent(slug)}?refresh=false`,
      { signal: request.signal },
    )
  } catch (error) {
    if (error instanceof BackendResponseError && error.status === 404) {
      throw new Response('Not Found', { status: 404 })
    }
    throw error
  }
}

function summary(value: string): string {
  const clean = value.replace(/\s+/g, ' ').trim()
  return clean.length > 158 ? `${clean.slice(0, 155).trimEnd()}...` : clean
}

export const meta: MetaFunction<typeof loader> = ({ loaderData, location }) => {
  if (!loaderData) return [{ title: 'Game Not Found | GameMetrix' }, { name: 'robots', content: 'noindex,follow' }]
  const canonical = `https://gamemetrix.me/game/${encodeURIComponent(loaderData.slug)}`
  const description = summary(loaderData.summary)
  const image = loaderData.cover_url || loaderData.image_url || undefined
  return [
    { title: `${loaderData.title} Scores, Linux Compatibility and Playtime | GameMetrix` },
    { name: 'description', content: description },
    { name: 'robots', content: loaderData.seo_indexable && !location.search ? 'index,follow,max-image-preview:large' : 'noindex,follow' },
    { tagName: 'link', rel: 'canonical', href: canonical },
    { property: 'og:title', content: `${loaderData.title} | GameMetrix` },
    { property: 'og:description', content: description },
    { property: 'og:type', content: 'website' },
    { property: 'og:url', content: canonical },
    ...(image ? [{ property: 'og:image', content: image }] : []),
    { name: 'twitter:card', content: image ? 'summary_large_image' : 'summary' },
    { name: 'twitter:title', content: `${loaderData.title} | GameMetrix` },
    { name: 'twitter:description', content: description },
    ...(image ? [{ name: 'twitter:image', content: image }] : []),
  ]
}

export function headers() {
  return { 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' }
}

export default function GameRoute({ loaderData }: { loaderData: Game }) {
  return <><GameStructuredData game={loaderData} /><GameDetailPage initialGame={loaderData} /></>
}
