# GameMetrix Application Security Review

**Review date:** 2026-07-27

**Baseline commit:** `bac97b87502c1b3ab5a228951cb65447a3694ef2`

**Status:** Repository remediation complete; coordinated production TLS/firewall rollout pending Origin CA material.
**Frameworks:** OWASP ASVS 5.0, OWASP Top 10:2025, OWASP API Security Top 10

## Executive assessment

GameMetrix has strong application-level foundations: server-side authorization, strict
Pydantic payloads, parameterised SQLAlchemy queries, Argon2 password hashing, hashed
session tokens, CSRF validation, bounded public query parameters, provider timeouts,
and secret-safe AI error logging.

The deployment does not currently activate several of those controls. The production
backend resolves `ENV` to `development`, the Cloudflare-to-origin hop is plaintext,
and the origin is directly reachable over IPv6. Account routes are enabled while
email bodies and reset tokens are configured for development logging. The backend
also connects to PostgreSQL using a cluster superuser.

The AI fallback implementation adds a separate resource risk: only Groq has a
persistent request/token budget, so fallback providers can be consumed without the
same cost ceiling.

**Pre-remediation verdict: `SECURITY CHANGES REQUIRED`**

## Remediation result

The repository findings were remediated on 2026-07-27:

- Compose now requires explicit environment and separate application database
  credentials. Production validation is exercised in CI.
- An idempotent non-superuser database-role migration is provided; backend
  containers receive only the application role.
- Password hashing and verification run off the event loop with at most two
  concurrent Argon2 jobs and a retryable saturation response.
- Unsubscribe is a user-confirmed JSON-body POST reached through a fragment URL;
  nginx access logs omit query strings and admin audit queries redact secrets.
- Every AI provider attempt has a persistent request/token budget. Ambiguous
  outcomes retain reservations; concurrency, prompt and output are bounded.
- Similarity AI remains disabled by default and has a separate daily gate,
  minimum interval and bounded six-hour cache if enabled.
- Generated summaries pass deterministic issue and grounding validation. Catalog
  verdicts are advisory; approval, quarantine and deletion require an authenticated
  audited admin decision.
- HLTB follow-up URLs are restricted to the expected HTTPS origin and response
  and redirect sizes are bounded.
- React Router is on 8.3.0 with no production audit findings.
- Backend, frontend and nginx run non-root with read-only filesystems,
  `no-new-privileges`, dropped capabilities and bounded temporary filesystems.
- Base images and GitHub Actions use immutable digests/SHAs. CI includes Python
  and Node audits, Bandit, secret scanning, production-config validation and
  deployment-security regression tests.
- A tested Origin CA nginx overlay, Cloudflare-only UFW script and ordered
  rollback-aware runbook are included.

Repository validation after remediation:

- `python -m pytest -q` — 170 passed, 6 PostgreSQL integration tests skipped
  locally because the dedicated test database was not running.
- `python -m compileall -q app alembic`, `python -m pip check` — passed.
- `pip-audit` for runtime and development requirements — no known vulnerabilities.
- `bandit -q -r app -ll` — passed with no medium/high findings.
- `npm run lint`, `npm run typecheck`, `npm run build` — passed.
- Playwright — 17 passed.
- Lighthouse — home performance 95/accessibility 96/best-practices 100/SEO 100;
  game performance 96/accessibility 95/best-practices 100/SEO 100.
- `npm audit --omit=dev --audit-level=high` — zero vulnerabilities.
- Secret hook, base and production-overlay Compose validation, `git diff --check`,
  and non-root/read-only nginx `-t` — passed.

**Repository verdict: `PASS WITH PRODUCTION DEPENDENCY`**

GM-SEC-002 cannot be closed on the live origin until the user-supplied Cloudflare
Origin CA certificate/private key is installed and Cloudflare is switched to Full
(strict) before the Cloudflare-only firewall is enabled. GM-SEC-001 and
GM-SEC-003 also require the prepared production environment/role migration to be
deployed. Until that coordinated rollout completes, the live-system verdict
remains `SECURITY CHANGES REQUIRED`.

## Architecture and trust boundaries

1. Browsers connect to Cloudflare for `gamemetrix.me` and `api.gamemetrix.me`.
2. Cloudflare currently connects to the public nginx origin over port 80.
3. Nginx routes `/api/*` and `/admin/*` to FastAPI and other traffic to the
   React Router SSR service.
4. FastAPI validates public, account-cookie, and admin-bearer trust boundaries.
5. FastAPI connects to PostgreSQL and to third-party catalog, pricing, OAuth,
   email, and AI providers.
6. Game/catalog metadata from third parties is untrusted content even when the
   destination provider is trusted.
7. Secrets are supplied through Compose environment files and are not intended
   to cross into frontend bundles or API responses.

## Finding summary

| ID | Severity | Category | File/Location | Finding | Exploitability | Impact | Recommended fix | Confidence |
|---|---|---|---|---|---|---|---|---|
| GM-SEC-001 | High | Deployment / Authentication | `backend/app/config.py`, production runtime | Production runs as `development` | Directly verified | Insecure cookie flags, origin checks weakened, account tokens logged, docs exposed | Require explicit production mode and satisfy production validation | Confirmed |
| GM-SEC-002 | High | Transport / Cloud perimeter | `nginx.conf`, Compose, live origin | Cloudflare-origin hop is plaintext and origin is directly reachable | Remote network access with known host header | Cloudflare/WAF bypass and plaintext origin traffic | Origin TLS Full Strict plus Cloudflare-only firewall | Confirmed |
| GM-SEC-003 | Medium | Database / Secrets | `docker-compose.yml`, production role and `.env` | Backend uses PostgreSQL superuser; root `.env` is mode 664 | Requires app compromise or local read access | Database-cluster takeover and credential disclosure | Separate non-superuser app role, rotate secret, chmod 600 | Confirmed |
| GM-SEC-004 | Medium | Resource exhaustion | `backend/app/account_security.py`, account routes | Concurrent Argon2 verification can exceed 400 MB cgroup | Distributed unauthenticated login traffic | Backend OOM or prolonged auth/HTTP outage | Bounded async password worker pool | Confirmed |
| GM-SEC-005 | Medium | API cost / Availability | AI adapters and provider budgets | Gemini, Cloudflare and OpenRouter lack persistent budgets | Background fallback; public abuse if similarity AI enabled | Quota/cost exhaustion and provider outage | Per-provider persistent request/token budgets | Confirmed |
| GM-SEC-006 | Low | Quota accounting | `backend/app/integrations/groq.py` | Ambiguous Groq failures refund the full token reservation | Provider processes request but response is lost | Local ceiling undercounts real usage | Retain reservation unless valid usage is returned | Confirmed |
| GM-SEC-007 | Low | HTTP semantics / Capability URL | account unsubscribe route | State-changing GET carries token in query string | Link scanners, logs, or leaked URLs | Unintended preference change and token disclosure to logs | Fragment-based UI and JSON-body POST | Confirmed |
| GM-SEC-008 | Low | AI integrity / Prompt injection | summarizer and catalog-quality jobs | AI text/verdict can persist or quarantine without adequate deterministic gate | Compromised or adversarial third-party catalog content | Public content corruption or catalog hiding | Validate rewrites and require admin decision for destructive verdicts | Confirmed |

## Detailed findings

### GM-SEC-001 — Production security mode is not active

- **Severity:** High
- **Affected component:** Runtime configuration, account authentication, CSRF,
  cookies, OpenAPI exposure, account email delivery
- **Evidence:** Runtime inspection returned `ENV=development`,
  `ACCOUNT_AUTH_ENABLED=True`, `ACCOUNT_EMAIL_DELIVERY=log`, and
  `COOKIE_SECURE=False`. Running the production validator against the live settings
  failed issuer/audience, account URL, SMTP, and HTTPS CORS requirements.
- **Attack path:** A future verification or reset request writes the full account
  email body and capability token to backend logs. Session cookies are issued
  without `Secure`; origin-less state-changing requests receive development
  behaviour. The API documentation is public at the API hostname.
- **Impact:** Account-token disclosure to log readers, weaker cookie transport
  guarantees, and skipped production fail-closed checks.
- **Breaking change:** Production will refuse to start with incomplete settings.
  Account endpoints will be disabled until SMTP is configured.
- **Fix:** Require `ENV` explicitly in Compose, configure production origins and
  JWT scope, disable accounts while SMTP is absent, and verify secure cookies/docs.
- **Verification:** Production validation passes; docs return 404; account routes
  return 503 while disabled; cookies carry `Secure` when accounts are enabled.

### GM-SEC-002 — Origin is public and plaintext

- **Severity:** High
- **Affected component:** Cloudflare, nginx, host firewall
- **Evidence:** nginx publishes port 80 on IPv4 and IPv6; UFW is inactive; no
  listener exists on 443. A direct request to the origin IPv6 address with the API
  host header returned HTTP 200 without traversing Cloudflare.
- **Attack path:** An attacker sends traffic directly to the origin with a valid
  Host header, bypassing Cloudflare controls. Cloudflare itself must use plaintext
  HTTP to reach an origin with no TLS listener.
- **Impact:** Loss of edge protection and confidentiality/integrity on the
  Cloudflare-origin hop.
- **Breaking change:** Coordinated certificate, nginx, Cloudflare mode, and firewall
  rollout is required to avoid an outage.
- **Fix:** Install an Origin CA certificate, enable 443, select Full (strict), and
  allow web ports only from current Cloudflare source ranges.
- **Verification:** Cloudflare health is green over HTTPS; origin certificate and
  hostname validate; direct origin IPv4/IPv6 requests time out or are rejected.

### GM-SEC-003 — Excessive database privilege and readable secret file

- **Severity:** Medium
- **Affected component:** PostgreSQL and Compose secrets
- **Evidence:** The live backend database role reports `superuser=True`,
  `createrole=True`, `createdb=True`, `replication=True`, and `bypassrls=True`.
  The root `.env`, which contains `POSTGRES_PASSWORD`, is mode 664.
- **Attack path:** Application compromise inherits cluster-superuser rights. Any
  local account able to read the project directory can read the database password.
- **Impact:** Full database-cluster control and credential disclosure.
- **Breaking change:** A one-time role/ownership migration and password rotation.
- **Fix:** Create a database-owner application role without cluster capabilities,
  move object ownership, use a separate app password, and chmod secret files 600.
- **Verification:** The backend reports all elevated role flags false; Alembic and
  the complete PostgreSQL test suite still pass.

### GM-SEC-004 — Password hashing can exhaust container memory

- **Severity:** Medium
- **Affected component:** Login, registration, verification, reset and deletion
- **Evidence:** Argon2 uses 65,536 KiB per operation. Public login is a synchronous
  FastAPI handler and can execute concurrently in the thread pool, while the
  backend cgroup is limited to 400 MB.
- **Attack path:** Requests from multiple source addresses bypass the per-IP
  aggregation and cause several memory-hard verifications concurrently.
- **Impact:** OOM kill and loss of the full backend, not only authentication.
- **Breaking change:** Saturated authentication requests may receive a controlled
  503/429 rather than queue indefinitely.
- **Fix:** Offload hashes to an async bounded worker pool with two concurrent jobs
  and a short acquisition timeout.
- **Verification:** A concurrency regression test proves no more than two Argon2
  operations overlap and public health requests remain responsive.

### GM-SEC-005 — AI fallback providers have no persistent budgets

- **Severity:** Medium
- **Affected component:** AI orchestrator and Gemini/Cloudflare/OpenRouter adapters
- **Evidence:** Production has all four providers configured. The persistent budget
  status contains Groq but not the other three providers.
- **Attack path:** Scheduled jobs exhaust/fail Groq and continue through fallback
  providers. If public similarity AI is enabled, varied public requests amplify
  the same path.
- **Impact:** Provider quota/cost exhaustion and loss of AI-backed jobs.
- **Breaking change:** Calls stop when a provider's explicit budget is exhausted.
- **Fix:** Reserve and settle per-provider request/token budgets centrally; cap
  concurrency and request size; cache and separately throttle interactive AI.
- **Verification:** Fallback tests prove every attempt consumes the correct bucket,
  and exhausted/unconfigured budgets fail closed.

### GM-SEC-006 — Ambiguous failures undercount Groq tokens

- **Severity:** Low
- **Affected component:** Groq budget settlement
- **Evidence:** The adapter initialises response data to `None` and always settles
  in `finally`; a timeout after upstream acceptance is therefore settled as zero.
- **Attack path:** The provider processes a request but the response is lost;
  retries occur after the full reservation is refunded.
- **Impact:** Actual provider usage can exceed the intended token ceiling.
- **Breaking change:** Ambiguous failures retain reserved capacity.
- **Fix:** Only reconcile downward after a successful response with valid usage.
- **Verification:** Timeout and malformed-response tests retain the reservation.

### GM-SEC-007 — Unsubscribe capability is a state-changing query-string GET

- **Severity:** Low
- **Affected component:** Email digest unsubscribe
- **Evidence:** `GET /api/account/email/unsubscribe?token=...` mutates preferences;
  nginx logs the full request target.
- **Attack path:** Email scanners prefetch the link, or an access-log reader reuses
  the signed token.
- **Impact:** Unintended unsubscribe and capability-token exposure.
- **Breaking change:** Existing links change, but production currently has zero
  users and no delivered account emails.
- **Fix:** Put the token in a URL fragment, show a confirmation page, and submit it
  in a bounded POST body.
- **Verification:** GET cannot mutate; server/access logs never receive the token;
  POST changes only the token subject's preference.

### GM-SEC-008 — AI output has excessive integrity authority

- **Severity:** Low
- **Affected component:** Summary shortening and catalog-quality review
- **Evidence:** Shortened text is stored without the rewrite acceptance checks used
  by other paths. A valid AI `NOT_GAME` verdict can quarantine a row, and under an
  opt-in flag can delete rows with a deterministic marker.
- **Attack path:** Adversarial third-party metadata instructs the model to emit a
  syntactically valid but false output.
- **Impact:** Public content corruption, catalog hiding, or conditional deletion.
- **Breaking change:** Automated destructive actions become manual admin decisions.
- **Fix:** Apply deterministic rewrite validation; make AI verdicts advisory and
  require authenticated audited approval for quarantine/deletion.
- **Verification:** Prompt-injection fixtures cannot persist invalid text or mutate
  catalog visibility without an admin action.

## Endpoint authorization matrix

| Route group | Authentication | Authorization / ownership | CSRF / rate limit |
|---|---|---|---|
| `/health`, catalog, SEO, facets, detail, series | Public | Read-only bounded catalog data | Public per-IP limits where expensive |
| `/api/games/{slug}/trailer` | Public | Read-only fixed-provider lookup | 20/minute and bounded cache/concurrency |
| `/api/games/{slug}/similar` | Public | Read-only; optional AI rerank | Public limit; separate AI budget required |
| `/api/search` | Admin bearer | Admin role | Public limiter plus provider budget |
| `/api/import/*`, maintenance, score writes | Admin bearer | Admin role / heavy-job lock | Provider and job limits |
| `/admin/*` | Admin bearer | Parent-router admin dependency | Audit log and no-store |
| `/api/auth/token` | Public credential exchange | Admin username/password | Auth per-IP limit |
| Account register/login/reset/verify/OAuth | Public while accounts enabled | Token/mailbox/state checks | Origin validation and auth limits |
| Account session/state/export | Account cookie | Principal's own user ID only | Read-only |
| Account collections/preferences/alerts/delete | Account cookie | Principal's own user ID only | Same-origin plus CSRF |
| Account unsubscribe | Signed capability | Token subject only | Must be POST and separately limited |
| Analytics | Public or optional account | Server assigns account ID | Same-origin, strict schema, 120/minute |

## Hardening opportunities

- Run application containers as non-root with read-only filesystems and dropped
  capabilities.
- Pin CI actions and container images to immutable revisions.
- Add dependency, SAST and secret scans to CI.
- Restrict external HTML follow-up URLs to expected origins and bound response size.
- Remove stale provider-limit documentation.
- Reduce CSP reliance on `unsafe-inline` in a later nonce-capable frontend-server
  change; no exploitable XSS sink was confirmed in the reviewed code.

## Positive controls verified

- ORM query construction is parameterised; no attacker-controlled shell execution,
  unsafe deserialisation, or file upload surface was found.
- Admin and account authorization is enforced by FastAPI dependencies, not UI state.
- Account object queries derive user IDs from the authenticated principal.
- Request models generally forbid unknown fields and bound strings, arrays and
  numeric ranges.
- Passwords use Argon2; admin passwords use bcrypt; reset tokens are random,
  single-use and short-lived.
- Session and CSRF values are random and stored hashed.
- OAuth uses signed state, PKCE and a bounded relative return path.
- React rendering uses framework escaping; JSON-LD serializers escape `<`; external
  links are protocol-validated before rendering.
- AI provider secrets use headers; raw provider errors/prompts are not logged or
  returned.
- `.env` files are excluded from Git and Docker build contexts; tracked-secret and
  retained backend-log scans found no provider-key values.
- Nginx emits CSP, HSTS, clickjacking, MIME-sniffing, referrer and permissions
  headers.

## Review commands and validation

Executed before remediation:

- `python -m pytest -q` — 157 passed, 6 skipped
- Targeted AI/config/account tests — 35 passed
- `python -m pip check` — passed
- `python -m pip_audit -r requirements.txt` — no known vulnerabilities
- `python -m pip_audit -r requirements-dev.txt` — no known vulnerabilities
- `python -m bandit -r app -x tests -f json` — three low false positives
- `npm run lint` — passed
- `npm run typecheck` — passed
- `npm audit --omit=dev --json` — one React Router RSC advisory expanded to five
  dependency nodes; current application does not use unstable RSC APIs
- Secret signature and live log checks — no tracked/provider-secret match
- Live production config, role, file-mode, port, firewall, TLS and direct-origin
  checks — findings recorded above

## False positives and manual verification

- Bandit's `random.uniform` report concerns retry jitter, not a security token.
- Bandit classified fixed Google/Twitch token endpoint URLs as hard-coded passwords.
- The React Router advisory states that only unstable RSC APIs are affected; the
  repository does not use them. Upgrade is still planned to remove the vulnerable
  range and keep audit gates clean.
- Provider-side API-token scopes, billing caps, Cloudflare dashboard TLS mode,
  disk encryption, cloud firewall rules and backup encryption require provider or
  host-console verification.

## Scope limitations

This was a source/configuration review plus authorised non-destructive production
inspection. It was not a complete penetration test. No destructive production
payloads, credential attacks, provider-cost smoke calls, or external-user data
mutations were performed.

The verdict applies only to the reviewed repository, current deployment and observed
configuration; it is not a certification.
