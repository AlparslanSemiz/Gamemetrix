import type {
  ClientLoaderFunctionArgs,
  LoaderFunctionArgs,
  MetaFunction,
  ShouldRevalidateFunctionArgs,
} from 'react-router'
import { AppContent } from '../App'
import { readCatalogSnapshot, type CatalogSnapshot } from '../catalog/snapshot'
import {
  clientForwardHeaders,
  fetchBackend,
  loadTopGenres,
  temporaryFailureResponse,
  type RankingGenre,
} from '../server-api.server'
import {
  buildCatalogParams,
  DEFAULT_FILTERS,
  mergeFiltersIntoSearch,
  readUrlFilters,
  sameFilterSearch,
} from '../catalog/queryParams'
import { RouteErrorPage } from '../components/RouteErrorPage'
import { sharedCacheHeaders } from '../utils/cacheHeaders'
import type { CatalogGameListResponse } from '../types/game'

const SOCIAL_IMAGE = 'https://gamemetrix.me/og/home.png'
const LOGO_IMAGE = 'https://gamemetrix.me/logo-512.png'

interface HomeLoaderData extends CatalogGameListResponse {
  snapshot: CatalogSnapshot | null
  genres: RankingGenre[]
}

function catalogRequestPath(request: Request): string {
  const url = new URL(request.url)
  // The same URL -> filters -> query code the browser uses, so a shared link
  // renders exactly the list the sharer saw. The default sort is rank_score desc.
  const filters = { ...DEFAULT_FILTERS, ...readUrlFilters(url.search) }
  return `/api/catalog/games?${buildCatalogParams(filters, 24, 0).toString()}`
}

async function loadHomeCatalog(path: string, init: RequestInit): Promise<CatalogGameListResponse> {
  try {
    return await fetchBackend<CatalogGameListResponse>(path, init)
  } catch (catalogError) {
    // A rate-limited backend answers the same way on the legacy route; surface it
    // (429 + Retry-After, never cached) instead of rendering an empty catalog.
    if (init.signal?.aborted || (catalogError instanceof Response && catalogError.status === 429)) {
      throw catalogError
    }
    // During a rolling deploy the frontend can briefly reach a backend instance
    // that does not have the lightweight route yet. The legacy endpoint reads
    // the same database and keeps the catalog available until instances converge.
    const legacyPath = path.replace('/api/catalog/games', '/api/games')
    try {
      return await fetchBackend<CatalogGameListResponse>(legacyPath, init)
    } catch (legacyError) {
      console.error('Catalog database endpoints are unavailable.', {
        catalogError,
        legacyError,
      })
      if (legacyError instanceof Response) throw legacyError
      throw temporaryFailureResponse(503)
    }
  }
}

export async function loader({ request }: LoaderFunctionArgs): Promise<HomeLoaderData> {
  // The hydrated catalog continues with /api/catalog/games, so SSR must use the same
  // query and total. Mixing the 400-row SEO-curated pool with the full catalog
  // made the badge jump from "24 / 400" to "48 / 10,929" after hydration.
  const init = { signal: request.signal, headers: clientForwardHeaders(request) }
  const [result, genres] = await Promise.all([
    loadHomeCatalog(catalogRequestPath(request), init),
    loadTopGenres(init),
  ])
  return { ...result, snapshot: null, genres }
}

export async function clientLoader({
  request,
  serverLoader,
}: ClientLoaderFunctionArgs): Promise<HomeLoaderData> {
  const url = new URL(request.url)
  const hasCatalogFilters = [...url.searchParams.keys()].some((key) => key !== 'view')
  const snapshot = readCatalogSnapshot()
  // The address bar mirrors the filters, so a snapshot also matches `/?q=…` when
  // those are the filters it was saved with.
  const matchesUrl = !hasCatalogFilters
    || (snapshot !== null && sameFilterSearch(url.search, mergeFiltersIntoSearch('', snapshot.filters)))
  if (matchesUrl && snapshot?.games.length) {
    return {
      games: snapshot.games,
      total: snapshot.catalogTotal,
      snapshot,
      genres: [],
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
  // Filters, search and view changes on the catalog page are fetched by the page
  // itself (debounced, cancellable) and mirrored into the URL with replace; the
  // loader only needs to run for a fresh visit or a deep link.
  return false
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

export const headers = sharedCacheHeaders

export function ErrorBoundary() {
  return <RouteErrorPage />
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
        logo: LOGO_IMAGE,
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
        footerGenres={loaderData.genres}
      />
    </>
  )
}
