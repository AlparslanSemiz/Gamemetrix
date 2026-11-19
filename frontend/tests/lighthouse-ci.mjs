import http from 'node:http'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { chromium } from '@playwright/test'
import { launch } from 'chrome-launcher'
import lighthouse from 'lighthouse'
import { startMockApi } from './mock-api.mjs'

const HOST = '127.0.0.1'
const PUBLIC_PORT = 4173
const FRONTEND_PORT = 4174
const API_PORT = 8001
const REPORT_DIRECTORY = 'test-results/lighthouse'
const LIGHTHOUSE_RUNS = 3
// Applied ("devtools") throttling instead of Lighthouse's default Lantern simulation.
// Lantern re-plays the observed trace on a model and charged the home page for the whole
// ~22-chunk module graph that finished before first paint, although the cover image (the
// LCP element) paints with the first frame even with JavaScript disabled. That gave home
// LCP 1.8-2.6 s on CI with up to 600 ms between runs of one job. With applied throttling
// Chrome really runs on Lighthouse's mobile slow-4G profile (562.5 ms request latency,
// 1.4 Mbps down, 4x CPU slowdown) and LCP is the paint the trace observed: the HTML ->
// render-blocking CSS -> first-frame path.
const THROTTLING_METHOD = 'devtools'
// Budgets on the median of LIGHTHOUSE_RUNS, set from observed applied-throttling values:
//   baseline (home / game median LCP): local 1834-1910 / 1926-2032 ms, CI see below.
//   a render-blocking stylesheet held 1 s by the server: local home 2331-2337, game 2422-2442 ms.
//   the home cover made lazy and its preload dropped: LCP 1993 ms but LCP - FCP 442-519 ms.
// LCP_BUDGET_MS catches a slower critical path; LCP_AFTER_FCP_BUDGET_MS catches the LCP
// element no longer painting with the first frame (it does today: LCP == FCP on both pages).
const LCP_BUDGET_MS = 2200
const LCP_AFTER_FCP_BUDGET_MS = 250
const PAGES = [
  { label: 'home', path: '/' },
  { label: 'game', path: '/game/complete-test-game' },
]
const CHROME_PROFILE = `${REPORT_DIRECTORY}/chrome-profile`

function closeServer(server) {
  return new Promise((resolveClose) => server.close(resolveClose))
}

function proxyServer() {
  return http.createServer((request, response) => {
    const path = request.url ?? '/'
    const apiRequest = path.startsWith('/api/') || path === '/robots.txt' || path === '/sitemap.xml' || path.startsWith('/admin/')
    const port = apiRequest ? API_PORT : FRONTEND_PORT
    const upstream = http.request({
      hostname: HOST,
      port,
      path,
      method: request.method,
      headers: { ...request.headers, host: `${HOST}:${port}` },
    }, (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers)
      upstreamResponse.pipe(response)
    })
    upstream.on('error', (error) => {
      response.writeHead(502, { 'Content-Type': 'text/plain' })
      response.end(`Proxy error: ${error.message}`)
    })
    request.pipe(upstream)
  })
}

async function waitForReady(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // Server is still starting.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250))
  }
  throw new Error(`Timed out waiting for ${url}`)
}

function metric(lhr, id) {
  const value = lhr.audits[id]?.numericValue
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor(sorted.length / 2)]
}

function lcpAfterFcp(lhr) {
  const lcp = metric(lhr, 'largest-contentful-paint')
  const fcp = metric(lhr, 'first-contentful-paint')
  return lcp === null || fcp === null ? null : lcp - fcp
}

function validate(lhr, label, lcpGapMs) {
  const thresholds = {
    performance: 0.90,
    accessibility: 0.90,
    'best-practices': 0.90,
    seo: 0.90,
  }
  const failures = []
  for (const [category, minimum] of Object.entries(thresholds)) {
    const score = lhr.categories[category]?.score ?? 0
    if (score < minimum) failures.push(`${category} ${(score * 100).toFixed(0)} < ${minimum * 100}`)
  }
  const lcp = metric(lhr, 'largest-contentful-paint')
  const fcp = metric(lhr, 'first-contentful-paint')
  const cls = metric(lhr, 'cumulative-layout-shift')
  const inp = metric(lhr, 'interaction-to-next-paint')
  if (lcp !== null && lcp > LCP_BUDGET_MS) failures.push(`LCP ${Math.round(lcp)}ms > ${LCP_BUDGET_MS}ms`)
  if (lcpGapMs !== null && lcpGapMs > LCP_AFTER_FCP_BUDGET_MS) {
    failures.push(`LCP - FCP ${Math.round(lcpGapMs)}ms > ${LCP_AFTER_FCP_BUDGET_MS}ms`)
  }
  if (cls !== null && cls > 0.1) failures.push(`CLS ${cls.toFixed(3)} > 0.1`)
  if (inp !== null && inp > 200) failures.push(`INP ${Math.round(inp)}ms > 200ms`)

  const summary = Object.fromEntries(
    Object.keys(thresholds).map((category) => [category, Math.round((lhr.categories[category]?.score ?? 0) * 100)]),
  )
  process.stdout.write(`${label}: ${JSON.stringify({
    ...summary,
    lcp_ms: lcp && Math.round(lcp),
    fcp_ms: fcp && Math.round(fcp),
    lcp_after_fcp_ms: lcpGapMs === null ? null : Math.round(lcpGapMs),
    cls,
    inp_ms: inp && Math.round(inp),
  })}\n`)
  return failures.length ? `${label} Lighthouse thresholds failed: ${failures.join(', ')}` : null
}

let frontendProcess
let proxy
let mock
let chrome

try {
  mock = await startMockApi(API_PORT)
  frontendProcess = spawn(
    process.execPath,
    ['node_modules/@react-router/serve/bin.cjs', 'build/server/index.js'],
    {
      env: {
        ...process.env,
        HOST,
        PORT: String(FRONTEND_PORT),
        INTERNAL_API_BASE_URL: `http://${HOST}:${API_PORT}`,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  frontendProcess.stderr.on('data', (chunk) => process.stderr.write(chunk))
  proxy = proxyServer()
  await new Promise((resolveListen, reject) => {
    proxy.once('error', reject)
    proxy.listen(PUBLIC_PORT, HOST, resolveListen)
  })
  await waitForReady(`http://${HOST}:${PUBLIC_PORT}/`)

  await mkdir(REPORT_DIRECTORY, { recursive: true })
  await rm(CHROME_PROFILE, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 })
  await mkdir(CHROME_PROFILE, { recursive: true })
  chrome = await launch({
    chromePath: chromium.executablePath(),
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-gpu'],
    userDataDir: CHROME_PROFILE,
  })

  const pageFailures = []
  for (const { label, path } of PAGES) {
    // Shared CI runners still vary from run to run; Lighthouse's own guidance is to judge
    // the median of several runs.
    const runs = []
    for (let attempt = 0; attempt < LIGHTHOUSE_RUNS; attempt += 1) {
      const result = await lighthouse(`http://${HOST}:${PUBLIC_PORT}${path}`, {
        port: chrome.port,
        logLevel: 'error',
        output: 'json',
        onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
        throttlingMethod: THROTTLING_METHOD,
      })
      if (!result) throw new Error(`Lighthouse returned no result for ${label}`)
      runs.push(result.lhr)
    }
    runs.sort((a, b) => (metric(a, 'largest-contentful-paint') ?? 0) - (metric(b, 'largest-contentful-paint') ?? 0))
    const medianRun = runs[Math.floor(runs.length / 2)]
    const gaps = runs.map(lcpAfterFcp).filter((value) => value !== null)
    const runMs = (id) => runs.map((lhr) => Math.round(metric(lhr, id) ?? 0)).join(', ')
    process.stdout.write(`${label} LCP runs: ${runMs('largest-contentful-paint')} ms; FCP: ${runMs('first-contentful-paint')} ms\n`)
    await writeFile(`${REPORT_DIRECTORY}/${label}.json`, JSON.stringify(medianRun, null, 2))
    // Report both pages before failing, so one CI log shows every number.
    const failure = validate(medianRun, label, gaps.length ? median(gaps) : null)
    if (failure) pageFailures.push(failure)
  }
  if (pageFailures.length) throw new Error(pageFailures.join('; '))
} finally {
  if (chrome) {
    const closed = new Promise((resolveClose) => chrome.process.once('close', resolveClose))
    chrome.kill()
    await Promise.race([closed, new Promise((resolveWait) => setTimeout(resolveWait, 3000))])
    await rm(CHROME_PROFILE, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 })
  }
  if (proxy?.listening) await closeServer(proxy)
  if (mock?.listening) await closeServer(mock)
  if (frontendProcess && !frontendProcess.killed) frontendProcess.kill()
}
