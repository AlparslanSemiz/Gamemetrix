import { expect, test } from '@playwright/test'
import { buildGameCardModel } from '../../src/components/game-card/model'
import {
  loadedImageLooksLikePlaceholder,
  responsiveImage,
  smallCoverUrl,
  thumbnailUrl,
} from '../../src/utils/coverImage'
import { toCuratedCard } from '../../src/utils/curatedCards'
import { sourceScoreUrl } from '../../src/utils/sourceLinks'
import type { CatalogGame } from '../../src/types/game'
import { activeFilterChips } from '../../src/catalog/filterChips'
import {
  DEFAULT_FILTERS,
  buildCatalogParams,
  mergeFiltersIntoSearch,
  readUrlFilters,
  sameFilterSearch,
} from '../../src/catalog/queryParams'
import { enqueueSync } from '../../src/state/syncQueue'
import { formatIsoDate } from '../../src/utils/format'

test.describe('sized image variants', () => {
  const RAWG = 'https://media.rawg.io/media/games/c16/c160077f8977cb22f14e56408c1560ef.jpg'

  test('small cover boxes get the 420px RAWG variant', () => {
    expect(smallCoverUrl(RAWG))
      .toBe('https://media.rawg.io/media/resize/420/-/games/c16/c160077f8977cb22f14e56408c1560ef.jpg')
  })

  test('small cover boxes swap the Steam library hero for the header capsule', () => {
    expect(smallCoverUrl('https://cdn.akamai.steamstatic.com/steam/apps/254700/library_hero.jpg'))
      .toBe('https://cdn.akamai.steamstatic.com/steam/apps/254700/header.jpg')
    expect(smallCoverUrl('https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/220/library_hero.jpg?t=1745368545'))
      .toBe('https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/220/header.jpg?t=1745368545')
    // Other Steam art and unknown hosts are left as they are.
    for (const url of [
      'https://cdn.akamai.steamstatic.com/steam/apps/620/capsule_616x353.jpg',
      'https://images.example/library_hero.jpg.png',
      'data:image/svg+xml;base64,AAAA',
    ]) expect(smallCoverUrl(url)).toBe(url)
  })

  test('placeholder size check only judges original-size files', () => {
    // A near-square RAWG cover fetched as the 420w srcset candidate is real art.
    expect(loadedImageLooksLikePlaceholder(
      'https://media.rawg.io/media/resize/420/-/games/c16/c160077f8977cb22f14e56408c1560ef.jpg', 420, 500,
    )).toBe(false)
    expect(loadedImageLooksLikePlaceholder('https://media.rawg.io/media/crop/600/400/games/a.jpg', 420, 420)).toBe(false)
    expect(loadedImageLooksLikePlaceholder(
      'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1/ss_a.600x338.jpg', 460, 460,
    )).toBe(false)
    // Original-size small near-square images are still treated as logo placeholders.
    expect(loadedImageLooksLikePlaceholder(RAWG, 420, 500)).toBe(true)
    expect(loadedImageLooksLikePlaceholder('https://cdn.akamai.steamstatic.com/steam/apps/1/capsule.jpg', 184, 184)).toBe(true)
    expect(loadedImageLooksLikePlaceholder(RAWG, 1200, 1400)).toBe(false)
    expect(loadedImageLooksLikePlaceholder(RAWG, 420, 236)).toBe(false)
  })

  test('the detail hero gets a RAWG srcset up to 1280px, never the original', () => {
    const hero = responsiveImage(RAWG, 1280)
    expect(hero.src).toBe('https://media.rawg.io/media/resize/1280/-/games/c16/c160077f8977cb22f14e56408c1560ef.jpg')
    expect(hero.srcSet).toBe([420, 640, 1280]
      .map((width) => `https://media.rawg.io/media/resize/${width}/-/games/c16/c160077f8977cb22f14e56408c1560ef.jpg ${width}w`)
      .join(', '))
    expect(responsiveImage(RAWG, 420).src)
      .toBe('https://media.rawg.io/media/resize/420/-/games/c16/c160077f8977cb22f14e56408c1560ef.jpg')
  })

  test('Steam screenshots offer the 600px frame; other URLs pass through', () => {
    const shot = 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1/ss_a.1920x1080.jpg?t=1'
    expect(responsiveImage(shot, 1280)).toEqual({
      src: shot,
      srcSet: 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1/ss_a.600x338.jpg?t=1 600w, '
        + `${shot} 1920w`,
    })
    expect(responsiveImage(shot, 420)).toEqual({ src: shot.replace('.1920x1080.', '.600x338.') })
    const capsule = 'https://cdn.akamai.steamstatic.com/steam/apps/1086940/capsule_616x353.jpg'
    expect(responsiveImage(capsule, 1280)).toEqual({ src: capsule })
    expect(responsiveImage('https://media.rawg.io/media/resize/640/-/games/a.jpg', 1280))
      .toEqual({ src: 'https://media.rawg.io/media/resize/640/-/games/a.jpg' })
  })
})

test('ranking rows keep only what they render', () => {
  const now = Date.parse('2026-11-19T12:00:00Z')
  const card = toCuratedCard({
    id: 1, title: 'Row', slug: 'row', cover_url: '', image_url: 'https://media.rawg.io/media/games/a/b.jpg',
    release_date: '2024-01-01', release_year: 2024, metrix_score: 87.6, genres: [], platforms: [],
    developer: 'Dev', playtime_minutes: 0, hltb_main_story_minutes: 0, hltb_all_styles_minutes: 95,
    proton_tier: 'platinum',
    source_scores: [
      { source: 'Metacritic', score: 91.4, scale: 100, status: 'live', detail: 'long text' },
      { source: 'Steam', score: 0, scale: 100, status: 'live' },
      { source: 'IGDB', score: 80, scale: 100, status: 'mock' },
    ],
    price_snapshots: [
      { source: 'CheapShark', store: 'GOG', currency: 'USD', list_price: 20, sale_price: 10, discount_percent: 50, is_free: false, url: 'https://gog.example/deal', fetched_at: '2026-11-19T00:00:00Z' },
      { source: 'Steam', store: 'Steam', currency: 'USD', list_price: 5, sale_price: 5, discount_percent: 0, is_free: false, url: 'https://steam.example', fetched_at: '2026-11-01T00:00:00Z' },
    ],
  } as unknown as CatalogGame, now)
  expect(card).toEqual({
    slug: 'row',
    title: 'Row',
    cover: 'https://media.rawg.io/media/games/a/b.jpg',
    release_year: 2024,
    developer: 'Dev',
    score: 88,
    sourceScores: [91, null, null, null],
    proton_tier: 'platinum',
    playtimeHours: 2,
    // The cheaper Steam snapshot is 18 days old, past the actionable window.
    price: { label: '$10.00', discountPercent: 50, url: 'https://gog.example/deal', store: 'GOG' },
  })
})

test.describe('thumbnailUrl', () => {
  test('uses the 640px RAWG variant', () => {
    expect(thumbnailUrl('https://media.rawg.io/media/games/abc/def.jpg'))
      .toBe('https://media.rawg.io/media/resize/640/-/games/abc/def.jpg')
  })

  test('leaves already transformed RAWG, other hosts and data URLs alone', () => {
    for (const url of [
      'https://media.rawg.io/media/resize/420/-/games/abc.jpg',
      'https://media.rawg.io/media/crop/600/400/games/abc.jpg',
      'https://images.example/cover.jpg',
      'data:image/svg+xml;base64,AAAA',
      '',
    ]) {
      expect(thumbnailUrl(url)).toBe(url)
    }
  })

  test('uses the smaller Steam variant', () => {
    expect(thumbnailUrl('https://cdn.akamai.steamstatic.com/a/ss_1.1920x1080.jpg'))
      .toBe('https://cdn.akamai.steamstatic.com/a/ss_1.600x338.jpg')
  })
})

test('game cards use the thumbnail for both the image and the CSS cover', () => {
  const game = {
    title: 'Thumb Test',
    slug: 'thumb-test',
    cover_url: 'https://media.rawg.io/media/games/abc/def.jpg',
    screenshots: [],
    source_scores: [],
    metrix_score: 80,
    content_type: 'game',
  } as unknown as CatalogGame
  const model = buildGameCardModel(game)
  expect(model.coverSrc).toBe('https://media.rawg.io/media/resize/640/-/games/abc/def.jpg')
  expect(String(model.cardStyle['--cover-image' as keyof typeof model.cardStyle]))
    .toContain('/media/resize/640/-/')
})

test('OpenCritic links use the working search URL in every context', () => {
  const game = { title: 'Hades II', slug: 'hades-ii' } as unknown as CatalogGame
  for (const context of ['catalog-card', 'game-detail'] as const) {
    expect(sourceScoreUrl('OpenCritic', game, context))
      .toBe('https://opencritic.com/search?q=Hades%20II')
  }
})

test('legal pages are noindex and every page links to them', async ({ page }) => {
  for (const path of ['/impressum', '/privacy', '/datenschutz']) {
    await page.goto(path)
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  }
  await page.goto('/impressum')
  await expect(page.locator('a[href="https://alparslansemiz.com/de/impressum/"]')).toBeVisible()
  await page.goto('/')
  await expect(page.locator('footer a[href="/impressum"]').first()).toBeVisible()
  await expect(page.locator('footer a[href="/privacy"]').first()).toBeVisible()
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute('content', /og\/home\.png$/)
})

test.describe('formatIsoDate', () => {
  test('formats the calendar day in UTC whatever the process time zone is', () => {
    expect(formatIsoDate('2024-04-12')).toBe('Apr 12, 2024')
    expect(formatIsoDate('2024-04-12T00:00:00Z', 'long')).toBe('April 12, 2024')
    expect(formatIsoDate('2024-01-01T00:30:00+00:00')).toBe('Jan 1, 2024')
  })

  test('rejects missing, invalid and epoch placeholder dates', () => {
    expect(formatIsoDate(null)).toBeNull()
    expect(formatIsoDate('')).toBeNull()
    expect(formatIsoDate('not a date')).toBeNull()
    expect(formatIsoDate('1970-01-01')).toBeNull()
  })
})

test.describe('catalog URL filters', () => {
  test('round-trip every filter field through the query string', () => {
    const filters = {
      ...DEFAULT_FILTERS,
      q: 'elden ring',
      genre: 'RPG',
      platform: 'Linux',
      yearMin: 2020,
      yearMax: 2023,
      minScore: 80,
      maxScore: 95,
      minRatings: 500,
      minLiveSources: 2,
      requireCritic: true,
      hasAward: true,
      playerMode: 'coop' as const,
      playtimeMaxHours: 20,
      sort: 'metrix_score' as const,
      direction: 'asc' as const,
    }
    const search = mergeFiltersIntoSearch('?view=catalog', filters)
    expect(search).toContain('view=catalog')
    expect({ ...DEFAULT_FILTERS, ...readUrlFilters(search) }).toEqual(filters)
  })

  test('defaults write nothing and bad values are ignored', () => {
    expect(mergeFiltersIntoSearch('', DEFAULT_FILTERS)).toBe('')
    expect(readUrlFilters('?min_score=abc&year_min=-5&sort=drop_table&mode=x&dir=up')).toEqual({})
  })

  test('the legacy single year link still means that year only', () => {
    expect(readUrlFilters('?year=2020')).toMatchObject({ yearMin: 2020, yearMax: 2020 })
  })

  test('filter comparison ignores order and non-filter params', () => {
    expect(sameFilterSearch('?view=x&genre=RPG&q=a', '?q=a&genre=RPG')).toBe(true)
    expect(sameFilterSearch('?genre=RPG', '?genre=Action')).toBe(false)
  })

  test('the API query is built from the same state', () => {
    const params = buildCatalogParams({ ...DEFAULT_FILTERS, q: ' hades ', playtimeMaxHours: 20 }, 24, 0)
    expect(params.get('q')).toBe('hades')
    expect(params.get('playtime_max_hours')).toBe('20')
    expect(params.get('year_min')).toBeNull()
  })
})

test.describe('active filter chips', () => {
  test('there is one chip for every active filter field and none by default', () => {
    expect(activeFilterChips(DEFAULT_FILTERS)).toEqual([])
    const ids = activeFilterChips({
      ...DEFAULT_FILTERS,
      q: 'a',
      genre: 'RPG',
      platform: 'Linux',
      developer: 'D',
      publisher: 'P',
      yearMin: 2020,
      minScore: 70,
      minRatings: 1000,
      minLiveSources: 2,
      playtimeMaxHours: 10,
      playerMode: 'coop',
      hasAward: true,
    }).map((chip) => chip.id)
    expect(ids).toEqual(['q', 'developer', 'publisher', 'genre', 'platform', 'year', 'score', 'ratings', 'sources', 'playtime', 'mode', 'award'])
  })

  test('clearing a chip returns exactly its fields to their defaults', () => {
    const chip = activeFilterChips({ ...DEFAULT_FILTERS, yearMin: 2020, yearMax: 2022 })[0]
    expect({ ...DEFAULT_FILTERS, yearMin: 2020, yearMax: 2022, ...chip.reset }).toEqual(DEFAULT_FILTERS)
  })
})

test('collection syncs for one game and list run in order, different keys in parallel', async () => {
  const log: string[] = []
  const slow = (name: string, ms: number) => async () => {
    log.push(`start ${name}`)
    await new Promise((resolve) => setTimeout(resolve, ms))
    log.push(`end ${name}`)
  }
  await Promise.all([
    enqueueSync('game:wishlist', slow('add', 60)),
    enqueueSync('game:wishlist', slow('remove', 5)),
    enqueueSync('other:wishlist', slow('other', 20)),
  ])
  // The remove starts only after the add finished, even though it is faster...
  expect(log.indexOf('end add')).toBeLessThan(log.indexOf('start remove'))
  // ...while an unrelated key is not held up behind them.
  expect(log.indexOf('start other')).toBeLessThan(log.indexOf('end add'))
})

test('a failed sync does not block the next one for the same key', async () => {
  await expect(enqueueSync('k', async () => { throw new Error('offline') })).rejects.toThrow('offline')
  await expect(enqueueSync('k', async () => 'ok')).resolves.toBe('ok')
})
