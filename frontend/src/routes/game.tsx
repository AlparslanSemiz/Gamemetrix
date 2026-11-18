import type { LoaderFunctionArgs, MetaFunction } from 'react-router'
import { GameStructuredData } from '../components/GameStructuredData'
import { RouteErrorPage } from '../components/RouteErrorPage'
import { sharedCacheHeaders } from '../utils/cacheHeaders'
import { GameDetailPage } from '../pages/GameDetailPage'
import { BackendResponseError, clientForwardHeaders, fetchBackend } from '../server-api.server'
import type { Game } from '../types/game'

export interface GameLoaderData {
  game: Game
  renderedAt: number
}

export async function loader({ params, request }: LoaderFunctionArgs): Promise<GameLoaderData> {
  const slug = params.slug ?? ''
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Response('Not Found', { status: 404 })
  try {
    const game = await fetchBackend<Game>(
      `/api/games/${encodeURIComponent(slug)}?refresh=false`,
      { signal: request.signal, headers: clientForwardHeaders(request) },
    )
    return { game, renderedAt: Date.now() }
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
  const game = loaderData.game
  const canonical = `https://gamemetrix.me/game/${encodeURIComponent(game.slug)}`
  const description = summary(game.summary)
  const image = game.cover_url || game.image_url || undefined
  return [
    { title: gameTitle(game.title) },
    { name: 'description', content: description },
    { name: 'robots', content: game.seo_indexable && !location.search ? 'index,follow,max-image-preview:large' : 'noindex,follow' },
    { tagName: 'link', rel: 'canonical', href: canonical },
    { property: 'og:title', content: `${game.title} | GameMetrix` },
    { property: 'og:description', content: description },
    { property: 'og:type', content: 'website' },
    { property: 'og:url', content: canonical },
    ...(image ? [{ property: 'og:image', content: image }] : []),
    { name: 'twitter:card', content: image ? 'summary_large_image' : 'summary' },
    { name: 'twitter:title', content: `${game.title} | GameMetrix` },
    { name: 'twitter:description', content: description },
    ...(image ? [{ name: 'twitter:image', content: image }] : []),
  ]
}

export const headers = sharedCacheHeaders

export function ErrorBoundary() {
  return <RouteErrorPage />
}

export default function GameRoute({ loaderData }: { loaderData: GameLoaderData }) {
  return (
    <>
      <GameStructuredData game={loaderData.game} now={loaderData.renderedAt} />
      <GameDetailPage initialGame={loaderData.game} renderedAt={loaderData.renderedAt} />
    </>
  )
}
