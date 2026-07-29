import type {
  ClientLoaderFunctionArgs,
  LoaderFunctionArgs,
  MetaFunction,
  ShouldRevalidateFunctionArgs,
} from 'react-router'
import { AppContent } from '../App'
import { readCatalogSnapshot, type CatalogSnapshot } from '../catalog/snapshot'
import { fetchBackend } from '../server-api.server'
import type { CatalogGameListResponse } from '../types/game'

const SOCIAL_IMAGE = 'https://gamemetrix.me/icons.svg'

interface HomeLoaderData extends CatalogGameListResponse {
  snapshot: CatalogSnapshot | null
}

function catalogRequestPath(request: Request): string {
  const url = new URL(request.url)
  const params = new URLSearchParams({
    sort: 'rank_score',
    direction: 'desc',
    limit: '24',
    offset: '0',
  })
  for (const key of ['genre', 'developer', 'publisher']) {
    const value = url.searchParams.get(key)?.trim()
    if (value) params.set(key, value)
  }
  const year = Number(url.searchParams.get('year'))
  if (Number.isInteger(year) && year > 1970) {
    params.set('year_min', String(year))
    params.set('year_max', String(year))
  }
  return `/api/catalog/games?${params.toString()}`
}

async function loadHomeCatalog(path: string): Promise<CatalogGameListResponse> {
  try {
    return await fetchBackend<CatalogGameListResponse>(path)
  } catch (catalogError) {
    // During a rolling deploy the frontend can briefly reach a backend instance
    // that does not have the lightweight route yet. The legacy endpoint reads
    // the same database and keeps the catalog available until instances converge.
    const legacyPath = path.replace('/api/catalog/games', '/api/games')
    try {
      return await fetchBackend<CatalogGameListResponse>(legacyPath)
    } catch (legacyError) {
      // Keep the application shell usable during a full backend interruption.
      // The client catalog effect retries the lightweight endpoint after hydration.
      console.error('Catalog database endpoints are unavailable.', {
        catalogError,
        legacyError,
      })
      return { games: [], total: 0 }
    }
  }
}

export async function loader({ request }: LoaderFunctionArgs): Promise<HomeLoaderData> {
  // The hydrated catalog continues with /api/catalog/games, so SSR must use the same
  // query and total. Mixing the 400-row SEO-curated pool with the full catalog
  // made the badge jump from "24 / 400" to "48 / 10,929" after hydration.
  const result = await loadHomeCatalog(catalogRequestPath(request))
  return { ...result, snapshot: null }
}

export async function clientLoader({
  request,
  serverLoader,
}: ClientLoaderFunctionArgs): Promise<HomeLoaderData> {
  const url = new URL(request.url)
  const hasCatalogFilters = [...url.searchParams.keys()].some((key) => key !== 'view')
  if (!hasCatalogFilters) {
    const snapshot = readCatalogSnapshot()
    if (snapshot?.games.length) {
      return {
        games: snapshot.games,
        total: snapshot.catalogTotal,
        snapshot,
      }
    }
  }
  return serverLoader<HomeLoaderData>()
}

export function shouldRevalidate({
  currentUrl,
  defaultShouldRevalidate,
  nextUrl,
}: ShouldRevalidateFunctionArgs): boolean {
  if (currentUrl.pathname !== '/' || nextUrl.pathname !== '/') {
    return defaultShouldRevalidate
  }
  const withoutView = (url: URL) => {
    const params = new URLSearchParams(url.search)
    params.delete('view')
    params.sort()
    return params.toString()
  }
  if (withoutView(currentUrl) === withoutView(nextUrl)) return false
  return defaultShouldRevalidate
}

export const meta: MetaFunction = ({ location }) => [
  { title: 'GameMetrix – Game Scores, Linux Compatibility & Playtime' },
  { name: 'description', content: 'Compare Metacritic, OpenCritic, Steam and IGDB scores with Proton compatibility, playtime and current PC game prices.' },
  { name: 'robots', content: location.search ? 'noindex,follow' : 'index,follow,max-image-preview:large' },
  { tagName: 'link', rel: 'canonical', href: 'https://gamemetrix.me/' },
  { property: 'og:title', content: 'GameMetrix – Game Scores, Compatibility & Playtime' },
  { property: 'og:description', content: 'Independent game rankings with four named score sources, Linux compatibility, playtime and prices.' },
  { property: 'og:type', content: 'website' },
  { property: 'og:url', content: 'https://gamemetrix.me/' },
  { property: 'og:image', content: SOCIAL_IMAGE },
  { name: 'twitter:card', content: 'summary_large_image' },
  { name: 'twitter:title', content: 'GameMetrix – Game Scores, Compatibility & Playtime' },
  { name: 'twitter:description', content: 'Independent game rankings with four named score sources, Linux compatibility, playtime and prices.' },
  { name: 'twitter:image', content: SOCIAL_IMAGE },
]

export function headers() {
  return { 'Cache-Control': 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600' }
}

function homeStructuredData(data: CatalogGameListResponse): string {
  return JSON.stringify({
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': 'https://gamemetrix.me/#organization',
        name: 'GameMetrix',
        alternateName: ['Game Metrix', 'gamemetrix.me'],
        url: 'https://gamemetrix.me/',
        logo: SOCIAL_IMAGE,
      },
      {
        '@type': 'WebSite',
        '@id': 'https://gamemetrix.me/#website',
        url: 'https://gamemetrix.me/',
        name: 'GameMetrix',
        alternateName: ['Game Metrix', 'gamemetrix.me'],
        description: 'PC game ratings, Linux compatibility, playtime and current deals.',
        publisher: { '@id': 'https://gamemetrix.me/#organization' },
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

export default function Home({ loaderData }: { loaderData: HomeLoaderData }) {
  const firstCover = loaderData.games[0]?.cover_url || loaderData.games[0]?.image_url
  return (
    <>
      {firstCover ? (
        <link rel="preload" as="image" href={firstCover} fetchPriority="high" />
      ) : null}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeStructuredData(loaderData) }} />
      <AppContent
        initialGames={loaderData.games}
        initialTotal={loaderData.total}
        initialSnapshot={loaderData.snapshot}
      />
    </>
  )
}
