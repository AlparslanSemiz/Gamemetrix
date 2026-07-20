# Provider access and quota runbook

Last reviewed: 2026-07-20

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

## RAWG

The current [RAWG API page](https://rawg.io/apidocs) advertises 20,000 requests per month for Free, 50,000 for Business, and custom Enterprise access up to 1,000,000. Its current page also requires attribution and backlinks where RAWG data or images are used. The API page and [API terms](https://rawg.io/tos_api) contain wording that can differ by plan and project type, so commercial use must be confirmed in writing before launch.

Use the Business/Enterprise contact shown in the authenticated RAWG API portal. Keep `RAWG_MONTHLY_LIMIT=20000` until the portal or a written response grants more. A 401 normally means the key is rejected, not that the monthly allocation is exhausted.

**Subject:** GameMetrix RAWG API plan and licensing request

```text
Hello RAWG API team,

I am building GameMetrix (https://gamemetrix.me), a public game decision tool that compares named rating sources, Linux/Proton compatibility, playtime, and store prices.

Expected usage:
- launch catalog: approximately 10,000 games
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

## IsThereAnyDeal

The official [ITAD API documentation](https://docs.isthereanydeal.com/) lists `api@isthereanydeal.com` as the general API contact. It currently documents a default 1,000 requests per five-minute window for verified-email accounts, asks clients to cache, warns against constantly maxing the burst window, and says higher limits require a use-case review. The terms also restrict competitive uses and modification of supplied URLs/prices. GameMetrix must obtain written confirmation that its deal comparison and outbound links are acceptable.

Keep `ITAD_FIVE_MINUTE_LIMIT=1000` and the lower daily safety budget until the app setup page or written approval says otherwise. Preserve ITAD affiliate tags and price values exactly.

**To:** `api@isthereanydeal.com`  
**Subject:** GameMetrix API use approval and quota request

```text
Hello IsThereAnyDeal team,

I am building GameMetrix (https://gamemetrix.me), a public game decision tool. Price data supports a small part of each game page and links users to the original store; the product is not intended to reproduce the full ITAD experience.

Expected usage:
- launch catalog: approximately 10,000 games
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

**To:** `admin@opencritic.com`  
**Subject:** GameMetrix score read API and display license request

```text
Hello OpenCritic team,

I am building GameMetrix (https://gamemetrix.me), a public game decision tool that displays OpenCritic as one of four separately named score sources. Missing OpenCritic data remains missing and is never replaced by another provider.

Expected usage:
- approximately 10,000 games at launch
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
