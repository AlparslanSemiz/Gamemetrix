const SHARED_CACHE_CONTROL = 'public, max-age=60, s-maxage=900, stale-while-revalidate=3600'

// Rendered pages are cached at the edge, but a thrown 429/503 must keep its
// Retry-After and must never be cached, or one backend hiccup is served to
// everyone for 15 minutes.
export function sharedCacheHeaders({ errorHeaders }: { errorHeaders?: Headers } = {}): Record<string, string> {
  if (errorHeaders?.has('Retry-After')) {
    return {
      'Cache-Control': 'no-store',
      'Retry-After': errorHeaders.get('Retry-After') ?? '30',
    }
  }
  return { 'Cache-Control': SHARED_CACHE_CONTROL }
}
