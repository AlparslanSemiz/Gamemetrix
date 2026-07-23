export type CatalogFilter = 'developer' | 'publisher' | 'genre' | 'year'

export function catalogFilterHref(
  filter: CatalogFilter,
  value: string | number,
): string {
  return `/?${filter}=${encodeURIComponent(String(value))}`
}

export function websiteLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'Official site'
  }
}
