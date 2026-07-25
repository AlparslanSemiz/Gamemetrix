# SEO growth operating guide

Last reviewed: 2026-07-20

Google position is not guaranteed. GameMetrix measures progress through valid indexed pages, impressions, organic clicks, CTR, returning visitors, account conversion, and outbound store clicks.

## Canonical and index policy

The only canonical origin is `https://gamemetrix.me`.

| URL | Rendering | Index policy |
| --- | --- | --- |
| `/` | SSR catalog HTML | Index |
| `/about` | SSR methodology and limitations | Index |
| `/game/:slug` | SSR game HTML | Index only when the database quality gate passes and the page is in the initial publication set |
| `/best/linux-games` | SSR curation | Index with at least five qualifying games |
| `/best/steam-deck-games` | SSR curation | Index with at least five qualifying games |
| `/best/free-pc-games` | SSR curation | Index with at least five qualifying games |
| `/deals` | SSR curation | Index with at least five qualifying games |
| `/best/games/:year` | SSR curation | Index with at least five qualifying games |
| Search/filter query strings | Interactive | `noindex` and excluded from sitemap |
| `/login`, `/register`, password routes, `/account`, `/alerts`, `/settings`, `/admin` | Interactive/private | `noindex`, excluded from sitemap, no cache |

Cloudflare must redirect HTTP and `www` requests to the apex HTTPS URL with path and query intact. The origin Nginx also redirects `www`. Never expose the same document under multiple canonical hosts.

### Cloudflare rules

Create these rules in this order and test them with a path that includes a query string:

1. Redirect Rule: when `http.request.full_uri` uses HTTP, issue a static/dynamic 301 to `https://gamemetrix.me${uri.path}` while preserving the query string.
2. Redirect Rule: when `http.host eq "www.gamemetrix.me"`, issue a 301 to the same apex HTTPS path and query.
3. Cache Rule: bypass cache for `/api/*`, `/admin*`, `/account`, `/login`, `/register`, `/forgot-password`, `/reset-password`, and `/verify-email`.
4. Cache Rule: cache eligible `/game/*`, `/best/*`, and `/deals` HTML according to the origin `s-maxage=900` response.
5. Cache Rule: cache the `/sitemap*.xml` family (the index and its chunks) according to their one-hour origin response.

Use Full (strict) TLS, keep the origin inaccessible except through the trusted proxy/network where practical, and enable `ANALYTICS_TRUST_PROXY_HEADERS` only after that restriction is in place. Cloudflare configuration is an operator step; repository code cannot create the DNS property, TLS mode, or account rules by itself.

## Game quality gate

A game can be published only when all checks pass:

1. `content_type` is `game`.
2. Release year/date is known.
3. A valid HTTP(S) cover image exists.
4. The normalized summary has at least 160 meaningful characters and is not a placeholder.
5. At least two applicable primary sources are live: Metacritic, OpenCritic, Steam, and IGDB.
6. At least one decision signal exists: Proton/Linux, HLTB/playtime, price, or award context.
7. It ranks inside `SEO_INDEX_LIMIT`, initially 500.

RAWG never fills one of the four primary slots. It is displayed under supplementary sources. Failing pages remain functional but receive `noindex,follow`, stay out of the XML sitemap, and show their exclusion reason in admin.

## Metadata templates

- Game title: `[Game] Scores, Linux Compatibility and Playtime | GameMetrix`
- Year page: `Best Games of [Year] | GameMetrix`
- Linux page: `Best Linux Games | GameMetrix`
- Steam Deck page: `Best Steam Deck Games | GameMetrix`
- Free page: `Best Free PC Games | GameMetrix`
- Deals page: `Best PC Game Deals | GameMetrix`

Descriptions must state the page-specific decision value and stay factual. Each indexable page includes canonical, Open Graph, Twitter metadata, `BreadcrumbList`, and appropriate `VideoGame`/`SoftwareApplication` or `ItemList` JSON-LD. Missing price or rating values are omitted from structured data rather than invented.

## Search demand clusters

Build pages only where catalog evidence supports the intent:

- `[game] metacritic opencritic steam score`
- `[game] linux proton compatibility`
- `[game] steam deck compatibility`
- `[game] how long to beat`
- `[game] price / best deal`
- `best linux games`
- `best steam deck games`
- `best free pc games`
- `best games [year]`

Do not generate combinatorial genre/platform/year pages until each page has a distinct methodology, useful copy, enough qualifying games, and internal links.

## Internal linking and content

- Every curation links to its game pages and sibling curations with ordinary `<a href>` links.
- Every game page links its four named sources, official site when known, price destination, and relevant related games.
- Show source coverage, data update date, Proton tier colors, HLTB, and price context visibly.
- Add human review or original methodology notes to high-impression pages before expanding beyond the first 500 games.
- Preserve provider attribution and outbound URL requirements described in `docs/provider-access.md`.

Google's [JavaScript SEO guidance](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics) explains crawl, render, and index stages; SSR is used here so essential content is already present in the first response. Google's [helpful content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content) is the publication standard: pages must help people make a game decision, not exist merely to capture a query.

## Sitemap, robots, and crawler checks

- `/sitemap.xml` is a UTF-8 sitemap **index**. It references `/sitemap-static.xml` (landing, curation, genre and year pages) and one or more `/sitemap-games-N.xml` chunks of at most 10,000 game URLs each. All entries are absolute canonical URLs and the family is cached for one hour.
- `/robots.txt` is served as a static file by the frontend — the single source of truth. It links the sitemap index and blocks private route families.
- Missing slugs return HTTP 404.
- Game HTML is cached for 15 minutes at the edge; account, API, and admin responses are not cached.
- Chunking keeps every file well under Google's 50,000-URL / 50 MB per-file limits; the index grows a new chunk automatically as `SEO_INDEX_LIMIT` rises. See Google's [sitemap guide](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap).

Release smoke checks:

```bash
curl -sS https://gamemetrix.me/game/example-slug | grep -E '<h1|canonical|application/ld\+json|Metacritic|OpenCritic|Steam|IGDB'
curl -I https://gamemetrix.me/game/definitely-missing
curl -sS https://gamemetrix.me/sitemap.xml            # sitemap index
curl -sS https://gamemetrix.me/sitemap-static.xml     # landing + curation URLs
curl -sS https://gamemetrix.me/sitemap-games-1.xml    # first game chunk
curl -sS https://gamemetrix.me/robots.txt
```

## Search Console setup

1. Add the Domain property `gamemetrix.me` in Search Console. A Domain property covers protocols and subdomains and uses DNS verification, as documented in the official [Search Console property guide](https://support.google.com/webmasters/answer/34592).
2. Add the supplied TXT record in Cloudflare DNS and keep it permanently.
3. Submit `https://gamemetrix.me/sitemap.xml`.
4. Inspect `/`, all five curation types, and a representative indexable/non-indexable game.
5. Validate canonical selection, rendered HTML, structured data, mobile usability, and Core Web Vitals.
6. Do not request indexing for pages that fail the quality gate.

## GA4 setup

1. Create one GA4 property for GameMetrix and one Web data stream for
   `https://gamemetrix.me`.
2. Put the resulting `G-...` value in the deployment environment as
   `VITE_GA_MEASUREMENT_ID`, then rebuild the frontend image. Do not commit the
   measurement ID to source-controlled environment files.
3. Verify that no Google Analytics request is sent before the visitor selects
   **Allow analytics**, and that choosing **Decline** stops later events.
4. Mark administrator and test browsers as internal in Settings. Admin sign-in
   does this automatically for that browser.
5. Link the Search Console property from GA4 after both properties are verified.

GA4 browser/device counts, GameMetrix browser IDs, and hashed network IDs are
different approximations; none should be presented as an exact person count.

## Weekly CTR process

Every Monday compare the last 28 days with the previous 28 days:

1. Export Search Console page/query data: impressions, clicks, CTR, and average position.
2. Segment brand, individual games, Linux/Steam Deck, free/deal, and year intent.
3. Prioritize high-impression pages with below-cluster CTR, then check query-title alignment and snippet accuracy.
4. Check losing pages for stale source coverage, broken images, accidental `noindex`, canonical drift, 404s, or slower Core Web Vitals.
5. Make one attributable title/content/internal-link change per page cohort and annotate the date.
6. Compare organic landing sessions to `signup_completed`, `wishlist_add`, `alert_enabled`, `store_outbound`, and returning visitors in admin.
7. Expand the publication cap only when the current cohort is valid, useful, and receiving stable crawl/index coverage.

After changing `SEO_INDEX_LIMIT`, run one controlled catalog SEO-state refresh so
stored `seo_indexable` flags match the new cohort. Do not enable the full
maintenance pass on every application boot.

Performance targets are p75 LCP <= 2.5 s, INP <= 200 ms, and CLS <= 0.1.

## Prohibited growth tactics

- No bought links, private blog networks, automated forum spam, doorway pages, cloaking, or hidden keyword blocks.
- No mass publication of API summaries or near-duplicate filter pages.
- No copied reviews, scraped OpenCritic pages, invented ratings, or misleading structured data.
- No claims that a provider endorses GameMetrix without written permission.
- No title changes solely to inflate clicks when the page does not satisfy the promise.
