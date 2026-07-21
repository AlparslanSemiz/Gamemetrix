import type { MetaFunction } from 'react-router'
import { AppContent } from '../App'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'

const SOCIAL_IMAGE = 'https://gamemetrix.me/icons.svg'

export async function loader(): Promise<GameListResponse> {
  return fetchBackend<GameListResponse>('/api/seo/curated/home?limit=24')
}

export const meta: MetaFunction = ({ location }) => [
  { title: 'GameMetrix' },
  { name: 'description', content: 'Compare Metacritic, OpenCritic, Steam and IGDB scores with Proton compatibility, playtime and current PC game prices.' },
  { name: 'robots', content: location.search ? 'noindex,follow' : 'index,follow,max-image-preview:large' },
  { tagName: 'link', rel: 'canonical', href: 'https://gamemetrix.me/' },
  { property: 'og:title', content: 'GameMetrix Game Rankings' },
  { property: 'og:description', content: 'Independent game rankings with four named score sources, Linux compatibility, playtime and prices.' },
  { property: 'og:type', content: 'website' },
  { property: 'og:url', content: 'https://gamemetrix.me/' },
  { property: 'og:image', content: SOCIAL_IMAGE },
  { name: 'twitter:card', content: 'summary_large_image' },
  { name: 'twitter:title', content: 'GameMetrix Game Rankings' },
  { name: 'twitter:description', content: 'Independent game rankings with four named score sources, Linux compatibility, playtime and prices.' },
  { name: 'twitter:image', content: SOCIAL_IMAGE },
]

export function headers() {
  return { 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' }
}

function homeStructuredData(data: GameListResponse): string {
  return JSON.stringify({
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': 'https://gamemetrix.me/#organization',
        name: 'GameMetrix',
        url: 'https://gamemetrix.me/',
        logo: SOCIAL_IMAGE,
      },
      {
        '@type': 'WebSite',
        '@id': 'https://gamemetrix.me/#website',
        url: 'https://gamemetrix.me/',
        name: 'GameMetrix',
        description: 'PC game ratings, Linux compatibility, playtime and current deals.',
        publisher: { '@id': 'https://gamemetrix.me/#organization' },
        // Enables the sitelinks search box in Google results.
        potentialAction: {
          '@type': 'SearchAction',
          target: {
            '@type': 'EntryPoint',
            urlTemplate: 'https://gamemetrix.me/?q={search_term_string}',
          },
          'query-input': 'required name=search_term_string',
        },
      },
      {
        '@type': 'ItemList',
        name: 'GameMetrix game rankings',
        numberOfItems: data.games.length,
        itemListElement: data.games.map((game, index) => ({
          '@type': 'ListItem',
          position: index + 1,
          name: game.title,
          url: `https://gamemetrix.me/game/${encodeURIComponent(game.slug)}`,
        })),
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://gamemetrix.me/' },
        ],
      },
    ],
  }).replace(/</g, '\\u003c')
}

export default function Home({ loaderData }: { loaderData: GameListResponse }) {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeStructuredData(loaderData) }} />
      <AppContent initialGames={loaderData.games} initialTotal={loaderData.total} />
    </>
  )
}
