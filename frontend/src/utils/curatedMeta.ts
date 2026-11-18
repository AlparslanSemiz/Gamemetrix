import type { CatalogGame } from '../types/game'
import { thumbnailUrl } from './coverImage'

export const DEFAULT_SOCIAL_IMAGE = 'https://gamemetrix.me/og/home.png'

function trimDescription(value: string, max = 155): string {
  const clean = value.replace(/\s+/g, ' ').trim()
  if (clean.length <= max) return clean
  const cut = clean.slice(0, max - 1)
  return `${cut.slice(0, cut.lastIndexOf(' ')).replace(/[,;:.\s]+$/, '')}…`
}

// First game's thumbnail when it is an absolute https URL, else the brand image.
function curatedSocialImage(games: CatalogGame[]): string {
  const url = games[0]?.cover_url || games[0]?.image_url || ''
  return /^https:\/\//.test(url) ? thumbnailUrl(url) : DEFAULT_SOCIAL_IMAGE
}

export function curatedMetaTags(
  data: { title: string; description: string; canonical: string; games: CatalogGame[] },
  search: string,
  pageTitle: string,
) {
  const description = trimDescription(data.description)
  const image = curatedSocialImage(data.games)
  return [
    { title: pageTitle },
    { name: 'description', content: description },
    { name: 'robots', content: data.games.length >= 5 && !search ? 'index,follow,max-image-preview:large' : 'noindex,follow' },
    { tagName: 'link', rel: 'canonical', href: data.canonical },
    { property: 'og:title', content: data.title },
    { property: 'og:description', content: description },
    { property: 'og:type', content: 'website' },
    { property: 'og:url', content: data.canonical },
    { property: 'og:image', content: image },
    { name: 'twitter:card', content: 'summary_large_image' },
    { name: 'twitter:title', content: data.title },
    { name: 'twitter:description', content: description },
    { name: 'twitter:image', content: image },
  ]
}
