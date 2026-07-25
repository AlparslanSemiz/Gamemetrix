# Provider access and quota runbook

Last reviewed: 2026-07-25

GameMetrix never raises a local limit above a provider's published allowance or written approval. A larger value in `.env` does not grant a larger upstream quota.

## Health status interpretation

| Admin status | Meaning | Action |
| --- | --- | --- |
| `invalid_key` | HTTP 401/403: rejected, expired, wrong host, or endpoint not approved | Validate the credential and provider approval. Do not treat this as quota exhaustion. |
| `rate_limited` | HTTP 429 | Stop until the provider window resets and honor `Retry-After`. |
| `timeout` | No response before the configured timeout | Retry with backoff; inspect network and provider status. |
| `provider_error` | Provider HTTP 5xx | Retry with jitter; do not rotate credentials. |
| `failing` | Invalid response or another integration error | Inspect the admin message and source snapshot. |

Credentials stay in backend environment variables. They must never be added to frontend variables, JSON responses, analytics properties, screenshots, or logs.

## Periodic enrichment and budget order

All provider work is server-side and persisted in PostgreSQL. Page views never
trigger provider traffic. The normal schedule is:

| Job | Default cadence | Purpose |
| --- | --- | --- |
| Primary rating refresh | 6 hours | Missing/stale primary scores; RAWG is used only for missing Metacritic |
| Metadata backfill | 30 minutes | Highest-value missing cover, summary, company, platform, media, and external-ID fields |
| HLTB backfill | 60 minutes | Gentle playtime lookup |
| Full data fill | 24 hours | Resumable catalog cursors, quality review/repair, metadata, scores, playtime, summaries, prices, SEO |

Scarce providers are called last. IGDB, Steam, Wikidata, CheapShark, and local
snapshots are tried before RAWG or a paid/approval-gated source. A provider's
daily limit can stop one job while leaving the persisted cursor and freshness
timestamps ready for the next period.

`STARTUP_RATING_REFRESH_LIMIT=0` and
`STARTUP_METADATA_BACKFILL_LIMIT=0` are intentional. On boot, the ordered
data-fill job gets the first budget and seeds free CheapShark Metacritic values
before RAWG. Set a positive startup limit only for a controlled maintenance run;
rating refresh remains bounded and does not enable the zero-weight RAWG
fallback.

## Provider outreach status

| Provider | Access route | Draft status |
| --- | --- | --- |
| OpenCritic | `admin@opencritic.com` | Ready to send |
| RAWG | `api@rawg.io` / authenticated portal | Ready to send |
| IGDB | `partner@igdb.com` | Ready to send |
| IsThereAnyDeal | `api@isthereanydeal.com` | Ready to send after key/account check |
| GameBrain | API console contact route | Ready; storage remains disabled pending written permission |
| Metacritic | [official support request](https://metacritichelp.zendesk.com/hc/en-us/requests/new) | Ready; no public read API assumed |

Before sending, replace the bracketed commercial model, MAU/page-view, contact
name, and attribution fields. Save replies and their effective dates outside
the repository.

## IGDB

[IGDB's current getting-started documentation](https://api-docs.igdb.com/#getting-started)
requires a free Twitch developer application and identifies the API as free for
non-commercial use. Commercial projects must contact `partner@igdb.com`. The API
allows 4 requests/second and up to 8 concurrent requests; GameMetrix stays
sequential and uses a persistent daily budget.

Set `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET`. The full-catalog importer scans
main games by ascending ID, stores its cursor in PostgreSQL, and resumes after
quota exhaustion. It uses `game_type`, not IGDB's deprecated `category` field.

**To:** `partner@igdb.com` — **Subject:** GameMetrix commercial use, caching, and bulk catalog request

```text
Hello IGDB partnerships team,

I am building GameMetrix (https://gamemetrix.me), a game discovery and decision
tool that combines separately attributed ratings with game metadata.

We would like to use IGDB for a cached catalog and metadata backfills:
- target catalog: approximately 50,000 games initially
- traffic: scheduled server-side imports; no API request per page view
- stored fields: titles, IDs/slugs, dates, descriptions, covers, platforms,
  genres, companies, modes, and screenshots
- commercial model: [NON-COMMERCIAL / ADS / AFFILIATE / SUBSCRIPTION]
- attribution: [PROPOSED ATTRIBUTION]

Could you confirm whether this use is covered, permitted cache/retention and
image-display terms, required attribution, and whether Data Partner/bulk dump
access is available? We will keep the integration disabled for commercial use
until written approval if a commercial partnership is required.

Thank you,
[NAME]
GameMetrix
```

## Steam

The official
[IStoreService/GetAppList](https://partner.steamgames.com/doc/webapi/IStoreService)
catalog requires a Steam Web API key and can return game-only pages with a
`last_appid` cursor. Set `STEAM_WEB_API_KEY`; GameMetrix requests only games
(not DLC, software, videos, or hardware), then validates each candidate through
Steam app details before storing it. The cursor is persisted so runs resume.

Steam metadata and reviews have their own platform/API terms. Keep original
Steam links and do not treat the Web API key as permission to redistribute
assets outside those terms. Steam Store endpoints can return HTTP 429 before
the local daily ceiling is reached; GameMetrix treats that response as a
process-level circuit breaker and resumes the persisted catalog cursor in a
later run.

## Wikidata

[Wikidata data access](https://www.wikidata.org/wiki/Wikidata:Data_access)
requires no API key and structured Wikidata data is available under CC0.
GameMetrix performs small exact-identity SPARQL queries using a known Steam App
ID or IGDB slug; it does not do unreliable fuzzy title matching. The public
query service is shared infrastructure, so requests use an identifying
User-Agent and a conservative local budget (`WIKIDATA_DAILY_LIMIT=200`).

No registration or email is needed. For a future truly bulk Wikidata import,
use official dumps instead of sending a huge SPARQL query.

## GameBrain

The [GameBrain API console](https://gamebrain.co/api/console) currently lists a
free non-commercial plan with 50 tokens/day, one concurrent request, 60
requests/minute, and a required backlink. However, the
[API terms](https://gamebrain.co/api/terms) prohibit copying/storing API data by
default and permit at most a one-hour cache only with prior written permission.
That conflicts with GameMetrix's persistent PostgreSQL enrichment.

Therefore a key alone cannot enable GameBrain. All three values are required:

```text
GAMEBRAIN_API_KEY=...
GAMEBRAIN_NONCOMMERCIAL_ENABLED=true
GAMEBRAIN_CACHE_PERMISSION_GRANTED=true
```

Set the last flag only after GameBrain grants written permission covering the
actual cache/retention model. The local cap is 40 tokens/day, below the free
plan's 50, and GameBrain ratings are deliberately excluded from GameMetrix
scoring. A visible backlink is included in the site footer.

Use the contact path in the GameBrain API console; do not guess an email
address.

**Subject:** GameMetrix non-commercial API caching and display permission

```text
Hello GameBrain team,

I am building GameMetrix (https://gamemetrix.me), a [NON-COMMERCIAL DESCRIPTION]
game discovery and decision tool. We would like to use the free API only as a
supplementary metadata fallback.

Expected use:
- at most 40 API tokens/day
- server-side title lookup followed by game detail
- stored fields: GameBrain ID/link, title, date, description, cover,
  developer/publisher, genres, platforms, modes, screenshots, and Steam ID
- visible linked GameBrain attribution in the site footer
- no GameBrain ratings in our score and no raw-response redistribution

Your current terms prohibit storage by default and mention written permission
for limited caching. Could you grant written permission for persistent caching
of the listed fields, or specify an acceptable retention/refresh/deletion model?
Please also confirm that our project qualifies for the free non-commercial plan.
We will not enable the integration until we have your written approval.

Thank you,
[NAME]
GameMetrix
```

## RAWG

The current [RAWG API page](https://rawg.io/apidocs) advertises 20,000 requests per month for Free, 50,000 for Business, and custom Enterprise access up to 1,000,000. Its current page also requires attribution and backlinks where RAWG data or images are used. The API page and [API terms](https://rawg.io/tos_api) contain wording that can differ by plan and project type, so commercial use must be confirmed in writing before launch.

Use the Business/Enterprise contact shown in the authenticated RAWG API portal.
Keep `RAWG_MONTHLY_LIMIT=20000` until the portal or a written response grants
more. RAWG can return HTTP 401 both for rejected credentials and for an
exhausted monthly allocation; GameMetrix distinguishes the provider's explicit
quota message and stops further RAWG requests in that process.

The current GameMetrix key renews on day 25, so use:

```text
RAWG_DAILY_LIMIT=600
RAWG_MONTHLY_LIMIT=20000
RAWG_MONTHLY_RESET_DAY=25
```

The ordinary 15% reserve makes only 510 requests/day and 17,000 requests/cycle
usable. Even a 31-day cycle therefore schedules at most 15,810 calls, leaving
additional headroom below the monthly ceiling.

RAWG request priority is deliberately strict:

1. Fill a missing Metacritic primary-score slot.
2. Fill user-visible metadata gaps on a game with a known RAWG identity.
3. Search for a RAWG identity only when the same request can repair a meaningful
   metadata gap.
4. Use RAWG catalog paging only if IGDB, Steam, and free catalog sources cannot
   reach the configured catalog target.

Broad rating refreshes disable the zero-weight RAWG rating fallback and generic
RAWG metadata helpers. Scheduled metadata refreshes request `additions` only
for missing DLC data and `game-series` only for missing similar-game data. A
missing cover or description therefore costs detail/search calls only, not
three unrelated requests.

**Subject:** GameMetrix RAWG API plan and licensing request

```text
Hello RAWG API team,

I am building GameMetrix (https://gamemetrix.me), a public game decision tool that compares named rating sources, Linux/Proton compatibility, playtime, and store prices.

Expected usage:
- launch catalog: approximately 50,000 games
- estimated monthly API volume: [REQUESTS]
- estimated monthly active users/page views: [MAU] / [PAGE VIEWS]
- refresh model: cached PostgreSQL records, stale-field backfills, and no request per page view
- attribution: linked RAWG attribution on every page that displays RAWG-derived data or imagery
- commercial model: [NON-COMMERCIAL / ADS / AFFILIATE / SUBSCRIPTION]

Could you confirm the appropriate plan, monthly request allowance, caching/retention rights, image rights, and whether our use is covered by the requested plan? We would also appreciate written guidance on bulk/bootstrap access if available.

Thank you,
[NAME]
GameMetrix
```

## Metacritic

GameMetrix currently receives Metacritic values through RAWG and shares the
same 20,000-request monthly budget. Metacritic's official site explains the
Metascore but does not advertise a general public read API. Do not scrape the
website or interpret RAWG access as a direct Metacritic license.

Submit the request through the
[official Metacritic support form](https://metacritichelp.zendesk.com/hc/en-us/requests/new).

**Subject:** GameMetrix Metascore data API and display licensing request

```text
Hello Metacritic team,

I am building GameMetrix (https://gamemetrix.me), a public game discovery and
decision tool. We would like to display the Metascore as a separately named and
linked critic source; missing values remain missing and are never synthesized.

Expected use:
- approximately 50,000 games at launch
- scheduled server-side missing/stale refreshes, never a request per page view
- PostgreSQL caching with the retention period you approve
- displayed fields: game/platform identity, Metascore, critic-review count,
  source URL, and fetched/updated timestamp
- commercial model: [NON-COMMERCIAL / ADS / AFFILIATE / SUBSCRIPTION]
- estimated MAU/page views: [MAU] / [PAGE VIEWS]

Do you offer an official API, data feed, or display license for this use?
Please confirm permitted fields, platform-specific score handling,
cache/retention rules, attribution/link requirements, request limits, and
pricing. We will not scrape Metacritic or increase usage without written
approval.

Thank you,
[NAME]
GameMetrix
```

## IsThereAnyDeal

The official [ITAD API documentation](https://docs.isthereanydeal.com/) lists `api@isthereanydeal.com` as the general API contact. It currently documents a default 1,000 requests per five-minute window for verified-email accounts, asks clients to cache, warns against constantly maxing the burst window, and says higher limits require a use-case review. The terms also restrict competitive uses and modification of supplied URLs/prices. GameMetrix must obtain written confirmation that its deal comparison and outbound links are acceptable.

Keep `ITAD_FIVE_MINUTE_LIMIT=1000` and the lower daily safety budget until the app setup page or written approval says otherwise. Preserve ITAD affiliate tags and price values exactly.

**To:** `api@isthereanydeal.com` — **Subject:** GameMetrix API use approval and quota request

```text
Hello IsThereAnyDeal team,

I am building GameMetrix (https://gamemetrix.me), a public game decision tool. Price data supports a small part of each game page and links users to the original store; the product is not intended to reproduce the full ITAD experience.

Expected usage:
- launch catalog: approximately 50,000 games
- estimated requests: [DAILY] daily, [PEAK] per five minutes
- cache: PostgreSQL snapshots with [TTL], refreshed by stale/missing fields rather than page views
- attribution: visible IsThereAnyDeal/API attribution and original outbound URLs with affiliate tags intact
- commercial model: [MODEL]

Could you confirm that this use complies with your terms, which endpoints are approved, and whether a higher daily/window allowance is available? We will not raise our configured limits before written approval.

Thank you,
[NAME]
GameMetrix
```

## OpenCritic

The public OpenCritic portal documents API keys for publisher/review submission workflows, but it does not publish a general read API license for a score aggregation product. The portal directs API-key access questions to `admin@opencritic.com`. The current RapidAPI credential used by GameMetrix is not evidence of a direct OpenCritic read license.

Keep OpenCritic disabled or at the approved RapidAPI allowance until OpenCritic grants direct read/cache/display rights in writing. Do not scrape OpenCritic pages.

For approved direct access, set `OPENCRITIC_API_BASE` to the endpoint supplied by OpenCritic and put the direct credential in `OPENCRITIC_API_KEY`. Keep `RAPIDAPI_KEY` exclusively for the RapidAPI endpoint so the two credentials cannot be confused during rotation.

**To:** `admin@opencritic.com` — **Subject:** GameMetrix score read API and display license request

```text
Hello OpenCritic team,

I am building GameMetrix (https://gamemetrix.me), a public game decision tool that displays OpenCritic as one of four separately named score sources. Missing OpenCritic data remains missing and is never replaced by another provider.

Expected usage:
- approximately 50,000 games at launch
- [REQUESTS] read requests per month
- PostgreSQL caching with [TTL] and stale-only refreshes
- linked OpenCritic attribution beside every displayed score
- no redistribution of raw API responses
- commercial model: [MODEL]

Do you offer an official read API key and license for this use? Please confirm permitted fields, cache/retention duration, attribution requirements, request limits, and pricing. We will not increase traffic or use an unofficial scraping path without approval.

Thank you,
[NAME]
GameMetrix
```

## HowLongToBeat

GameMetrix does not assume a documented bulk API allowance for HowLongToBeat. HLTB enrichment is therefore a conservative, optional lookup job with a persistent local daily budget, a minimum delay between requests, long-lived no-match timestamps, and no request on page view. Keep `HLTB_DAILY_LIMIT=250` and `HLTB_REQUEST_DELAY_SECONDS=1.5` at or below the values approved for the deployed integration. Disable the job immediately if the service rejects automated traffic or its terms change.

HLTB playtime is displayed as attributed decision context and never as a GameMetrix rating source. A failed or unmatched lookup remains missing; it is not estimated from another field.

## Approval checklist

- Save the provider response and effective date outside the repository.
- Record approved daily, monthly, and rolling-window limits in deployment secrets.
- Record cache/retention, attribution, image, affiliate-link, and commercial-use conditions.
- Update this document and admin budget configuration in the same pull request.
- Run one low-volume health check before enabling a backfill.
- Never work around 401, 403, or 429 responses with credential rotation or parallel accounts.
