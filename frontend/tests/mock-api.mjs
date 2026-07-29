import http from 'node:http'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const now = new Date().toISOString()
const account = {
  id: '11111111-1111-4111-8111-111111111111',
  email: 'player@example.com',
  display_name: 'Test Player',
  email_verified: true,
  created_at: now,
}
const emptyCollections = {
  watchlist: [], playing: [], seen: [], completed: [], on_hold: [], dropped: [], liked: [], favorites: [],
}
let state = {
  account,
  collections: structuredClone(emptyCollections),
  preferences: {
    min_discount: 20,
    min_score: 80,
    upcoming_days: 45,
    email_digest_enabled: false,
    marketing_enabled: false,
    settings: {},
  },
  read_alerts: [],
  dismissed_alerts: [],
}
let lastMerge = null
let delayedCatalogPage = null

const game = {
  id: 1,
  title: 'Complete Test Game',
  slug: 'complete-test-game',
  summary: 'Complete Test Game is a carefully documented role-playing adventure with tactical combat, meaningful exploration, accessible difficulty options, and enough original context to help players compare its strengths before choosing where and how to play.',
  summary_short: 'A complete game fixture for crawler and interaction tests.',
  cover_url: 'http://127.0.0.1:4173/favicon.svg?cover=1',
  image_url: null,
  website_url: 'https://example.com/complete-test-game',
  release_date: '2024-04-12',
  release_year: 2024,
  early_access_date: null,
  official_release_date: '2024-04-12',
  metacritic_score: 88,
  ratings_refreshed_at: now,
  metadata_refreshed_at: now,
  prices_refreshed_at: now,
  content_type: 'game',
  live_primary_source_count: 4,
  applicable_source_count: 4,
  applicable_sources: ['Metacritic', 'OpenCritic', 'IGDB', 'Steam'],
  confidence_level: 'Strong',
  data_strength: 'DATA_STRONG',
  score_profile: 'critic + user',
  popularity_label: 'Popular',
  metrix_score: 88,
  rank_score: 88,
  is_rankable: true,
  rank_exclusion_reason: null,
  seo_indexable: true,
  seo_exclusion_reason: null,
  seo_updated_at: now,
  critic_score: 88.5,
  user_score: 87.5,
  genres: ['RPG'],
  platforms: ['PC', 'Linux'],
  source_scores: [
    { source: 'Metacritic', score: 88, scale: 100, status: 'live', review_count: 80, refreshed_at: now },
    { source: 'OpenCritic', score: 89, scale: 100, status: 'live', review_count: 72, refreshed_at: now },
    { source: 'Steam', score: 87, scale: 100, status: 'live', review_count: 25000, refreshed_at: now },
    { source: 'IGDB', score: 88, scale: 100, status: 'live', review_count: 1200, refreshed_at: now },
    { source: 'RAWG', score: 86, scale: 100, status: 'live', review_count: 500, refreshed_at: now },
  ],
  developer: 'Fixture Studio',
  publisher: 'Fixture Publishing',
  playtime_minutes: 1800,
  hltb_id: 100,
  hltb_url: 'https://howlongtobeat.com/game/100',
  hltb_main_story_minutes: 1800,
  hltb_main_extra_minutes: 2400,
  hltb_completionist_minutes: 3600,
  hltb_all_styles_minutes: 2100,
  hltb_refreshed_at: now,
  award_count: 1,
  award_nominations: 2,
  goty_year: null,
  awards: ['Fixture Award'],
  screenshots: Array.from(
    { length: 18 },
    (_, index) => `http://127.0.0.1:4173/favicon.svg?screenshot=${index + 1}`,
  ),
  system_requirements: [],
  dlcs: [{
    id: 101,
    title: 'Complete Test Game - Expansion',
    release_year: 2025,
    cover_url: 'http://127.0.0.1:4173/favicon.svg?dlc=1',
    metacritic_score: 84,
    url: 'https://example.com/complete-test-game-expansion',
    type: 'expansion',
  }],
  similar_games: [],
  proton_tier: 'gold',
  proton_score: 0.9,
  price_snapshots: [{
    source: 'Steam', store: 'Steam', platform: 'PC', region: 'US', currency: 'USD',
    list_price: 59.99, sale_price: 29.99, discount_percent: 50,
    historical_low: 24.99, historical_low_date: '2026-06-01', sale_end_date: null,
    is_free: false, is_subscription_included: false, subscription_service: null,
    url: 'https://store.steampowered.com/', fetched_at: now,
  }],
}

const catalogOmittedFields = new Set([
  'summary',
  'website_url',
  'early_access_date',
  'official_release_date',
  'metacritic_score',
  'critic_score',
  'user_score',
  'seo_indexable',
  'seo_exclusion_reason',
  'game_modes',
  'hltb_id',
  'hltb_refreshed_at',
  'screenshots',
  'system_requirements',
  'dlcs',
  'similar_games',
  'franchise',
])

function catalogProjection(value, includePrices = false) {
  return Object.fromEntries(
    Object.entries(value).filter(([field]) =>
      !catalogOmittedFields.has(field) && (includePrices || field !== 'price_snapshots'),
    ),
  )
}

const catalogGame = catalogProjection(game)

function json(response, status, payload, headers = {}) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', ...headers })
  response.end(JSON.stringify(payload))
}

function hasSession(request) {
  return /(?:^|;\s*)gm_session=test-session(?:;|$)/.test(request.headers.cookie ?? '')
}

async function body(request) {
  const chunks = []
  for await (const chunk of request) chunks.push(chunk)
  if (!chunks.length) return {}
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1:8001')
  if (url.pathname === '/__test/merge') return json(response, 200, lastMerge ?? {})
  if (url.pathname === '/__test/catalog-delay' && request.method === 'POST') {
    const payload = await body(request)
    delayedCatalogPage = {
      offset: Math.max(0, Number(payload.offset ?? 0)),
      delayMs: Math.max(0, Number(payload.delay_ms ?? 0)),
    }
    return json(response, 200, delayedCatalogPage)
  }
  if (url.pathname === '/robots.txt') {
    response.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' })
    return response.end('User-agent: *\nDisallow: /api/\nSitemap: https://gamemetrix.me/sitemap.xml\n')
  }
  if (url.pathname === '/sitemap.xml') {
    response.writeHead(200, { 'Content-Type': 'application/xml; charset=utf-8' })
    return response.end('<?xml version="1.0"?><urlset><url><loc>https://gamemetrix.me/game/complete-test-game</loc></url></urlset>')
  }
  if (url.pathname.startsWith('/api/analytics/')) {
    response.writeHead(204)
    return response.end()
  }
  if (url.pathname === '/api/account/login' && request.method === 'POST') {
    return json(response, 200, { account }, {
      'Set-Cookie': [
        'gm_session=test-session; Path=/; HttpOnly; SameSite=Lax',
        'gm_csrf=test-csrf; Path=/; SameSite=Lax',
      ],
    })
  }
  if (url.pathname === '/api/account/me') {
    return hasSession(request) ? json(response, 200, { account }) : json(response, 401, { detail: 'Not authenticated.' })
  }
  if (url.pathname === '/api/account/session') {
    return json(response, 200, { account: hasSession(request) ? account : null })
  }
  if (url.pathname === '/api/account/state') {
    return hasSession(request) ? json(response, 200, state) : json(response, 401, { detail: 'Not authenticated.' })
  }
  if (url.pathname === '/api/account/state/merge' && request.method === 'POST') {
    if (!hasSession(request)) return json(response, 401, { detail: 'Not authenticated.' })
    const payload = await body(request)
    lastMerge = payload
    for (const key of Object.keys(emptyCollections)) {
      state.collections[key] = [...new Set([...(state.collections[key] ?? []), ...(payload.collections?.[key] ?? [])])]
    }
    state = {
      ...state,
      preferences: { ...state.preferences, ...(payload.preferences ?? {}) },
      read_alerts: [...new Set([...(state.read_alerts ?? []), ...(payload.read_alerts ?? [])])],
      dismissed_alerts: [...new Set([...(state.dismissed_alerts ?? []), ...(payload.dismissed_alerts ?? [])])],
    }
    return json(response, 200, state)
  }
  if (url.pathname === '/api/account/preferences' && request.method === 'PATCH') {
    state.preferences = { ...state.preferences, ...(await body(request)) }
    return json(response, 200, state.preferences)
  }
  if (url.pathname === '/api/account/logout' && request.method === 'POST') {
    return json(response, 200, { message: 'Logged out.' }, {
      'Set-Cookie': ['gm_session=; Path=/; Max-Age=0', 'gm_csrf=; Path=/; Max-Age=0'],
    })
  }
  if (url.pathname === '/api/seo/curated/home' || url.pathname.startsWith('/api/seo/curated/')) {
    return json(response, 200, { games: [catalogProjection(game, true)], total: 400 })
  }
  if (
    url.pathname === '/api/catalog/games'
    && url.searchParams.get('developer') === '__catalog_unavailable__'
  ) {
    return json(response, 503, { detail: 'Catalog temporarily unavailable.' })
  }
  if (url.pathname === '/api/catalog/games' || url.pathname === '/api/games') {
    const offset = Math.max(0, Number(url.searchParams.get('offset') ?? 0))
    const limit = Math.max(1, Number(url.searchParams.get('limit') ?? 24))
    if (delayedCatalogPage?.offset === offset) {
      const { delayMs } = delayedCatalogPage
      delayedCatalogPage = null
      await new Promise((resolveDelay) => setTimeout(resolveDelay, delayMs))
    }
    const pageSize = Math.min(limit, 48 - offset)
    const games = Array.from({ length: Math.max(0, pageSize) }, (_, index) => {
      const id = offset + index + 1
      return id === 1
        ? catalogGame
        : { ...catalogGame, id, title: `Catalog Test Game ${id}`, slug: `catalog-test-game-${id}` }
    })
    return json(response, 200, { games, total: 48 })
  }
  if (
    (url.pathname === '/api/catalog/games/batch' || url.pathname === '/api/games/batch')
    && request.method === 'POST'
  ) {
    const payload = await body(request)
    const includePrices = url.searchParams.get('include_prices') === 'true'
    const games = (payload.slugs ?? []).map((slug) => {
      if (slug === game.slug) return catalogProjection(game, includePrices)
      const id = Number(slug.match(/(\d+)$/)?.[1] ?? 2)
      return {
        ...catalogProjection(game, includePrices),
        id,
        title: `Catalog Test Game ${id}`,
        slug,
      }
    })
    return json(response, 200, { games, total: games.length })
  }
  if (url.pathname === '/api/facets') return json(response, 200, { genres: ['RPG'], years: [2024], platforms: ['PC', 'Linux'] })
  if (url.pathname === '/api/integrations/status') return json(response, 200, [
    { source: 'Steam', status: 'ok', detail: 'Fixture provider' },
  ])
  if (url.pathname === '/api/games/complete-test-game/similar') return json(response, 200, { games: [], total: 0 })
  if (url.pathname === '/api/games/complete-test-game/series') return json(response, 200, { series_key: '', games: [], total: 0 })
  if (url.pathname === '/api/games/complete-test-game/trailer') return json(response, 200, { video_id: null, watch_url: null })
  if (url.pathname === '/api/games/complete-test-game') return json(response, 200, game)
  const catalogDetailMatch = url.pathname.match(/^\/api\/games\/(catalog-test-game-(\d+))(?:\/(similar|series|trailer))?$/)
  if (catalogDetailMatch) {
    const [, slug, id, related] = catalogDetailMatch
    if (related === 'similar') return json(response, 200, { games: [], total: 0 })
    if (related === 'series') return json(response, 200, { series_key: '', games: [], total: 0 })
    if (related === 'trailer') return json(response, 200, { video_id: null, watch_url: null })
    return json(response, 200, {
      ...game,
      id: Number(id),
      title: `Catalog Test Game ${id}`,
      slug,
    })
  }
  if (url.pathname.startsWith('/api/games/')) return json(response, 404, { detail: 'Game not found.' })
  return json(response, 404, { detail: 'Not found.' })
})

export function startMockApi(port = 8001) {
  if (server.listening) return Promise.resolve(server)
  return new Promise((resolveStart, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => {
      server.off('error', reject)
      resolveStart(server)
    })
  })
}

const isDirectRun = process.argv[1]
  && fileURLToPath(import.meta.url) === resolve(process.argv[1])

if (isDirectRun) {
  await startMockApi()
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => server.close(() => process.exit(0)))
  }
}
