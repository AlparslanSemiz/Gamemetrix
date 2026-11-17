import { expect, test } from '@playwright/test'
import { buildGameCardModel } from '../../src/components/game-card/model'
import { thumbnailUrl } from '../../src/utils/coverImage'
import { sourceScoreUrl } from '../../src/utils/sourceLinks'
import type { CatalogGame } from '../../src/types/game'

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
