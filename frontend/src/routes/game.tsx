import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { GameStructuredData } from '../components/GameStructuredData'
import { GameDetailPage } from '../pages/GameDetailPage'
import { BackendResponseError, clientForwardHeaders, fetchBackend } from '../server-api.server'
import type { Game } from '../types/game'

export async function loader({ params, request }: LoaderFunctionArgs): Promise<Game> {
  const slug = params.slug ?? ''
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Response('Not Found', { status: 404 })
  try {
    return await fetchBackend<Game>(
      `/api/games/${encodeURIComponent(slug)}?refresh=false`,
      { signal: request.signal, headers: clientForwardHeaders(request) },
    )
  } catch (error) {
    if (error instanceof BackendResponseError && error.status === 404) {
      throw new Response('Not Found', { status: 404 })
    }
    throw error
  }
}

// Titles longer than ~60 characters get cut in search results.
function gameTitle(title: string): string {
  const full = `${title}: Scores, Linux & Playtime | GameMetrix`
  if (full.length <= 60) return full
  const short = `${title} Scores | GameMetrix`
  return short.length <= 60 ? short : `${title} | GameMetrix`
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
    { title: gameTitle(loaderData.title) },
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

export function headers({ errorHeaders }: { errorHeaders?: Headers }) {
  // A thrown 429/503 must keep its Retry-After and must never be cached.
  if (errorHeaders && errorHeaders.has('Retry-After')) {
    return {
      'Cache-Control': 'no-store',
      'Retry-After': errorHeaders.get('Retry-After') ?? '30',
    }
  }
  return { 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' }
}

export default function GameRoute({ loaderData }: { loaderData: Game }) {
  return <><GameStructuredData game={loaderData} /><GameDetailPage initialGame={loaderData} /></>
}
