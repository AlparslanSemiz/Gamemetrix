import type { MetaFunction } from 'react-router'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'
import { UtilityRoute } from './utility'

export function headers() {
  return { 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' }
}
export async function loader(): Promise<GameListResponse> {
  return fetchBackend<GameListResponse>('/api/seo/curated/home?limit=24')
}
export const meta: MetaFunction = () => [
  { title: 'How GameMetrix Scores and Ranks Games | GameMetrix' },
  {
    name: 'description',
    content: 'Learn how GameMetrix combines named rating sources, handles missing data and ranks games with compatibility, playtime and price context.',
  },
  { name: 'robots', content: 'index,follow,max-image-preview:large' },
  { tagName: 'link', rel: 'canonical', href: 'https://gamemetrix.me/about' },
  { property: 'og:title', content: 'How GameMetrix Scores and Ranks Games' },
  {
    property: 'og:description',
    content: 'Our source coverage, scoring method, ranking rules, limitations and update policy.',
  },
  { property: 'og:type', content: 'website' },
  { property: 'og:url', content: 'https://gamemetrix.me/about' },
]

export default function AboutRoute({ loaderData }: { loaderData: GameListResponse }) {
  const structuredData = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'AboutPage',
    '@id': 'https://gamemetrix.me/about#page',
    url: 'https://gamemetrix.me/about',
    name: 'How GameMetrix Scores and Ranks Games',
    isPartOf: { '@id': 'https://gamemetrix.me/#website' },
    about: { '@id': 'https://gamemetrix.me/#organization' },
  }).replace(/</g, '\\u003c')
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: structuredData }} />
      <UtilityRoute loaderData={loaderData} page="about" />
    </>
  )
}
