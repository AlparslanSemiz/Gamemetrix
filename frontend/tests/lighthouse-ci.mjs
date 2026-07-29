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

function validate(lhr, label) {
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
  const cls = metric(lhr, 'cumulative-layout-shift')
  const inp = metric(lhr, 'interaction-to-next-paint')
  if (lcp !== null && lcp > 2500) failures.push(`LCP ${Math.round(lcp)}ms > 2500ms`)
  if (cls !== null && cls > 0.1) failures.push(`CLS ${cls.toFixed(3)} > 0.1`)
  if (inp !== null && inp > 200) failures.push(`INP ${Math.round(inp)}ms > 200ms`)

  const summary = Object.fromEntries(
    Object.keys(thresholds).map((category) => [category, Math.round((lhr.categories[category]?.score ?? 0) * 100)]),
  )
  process.stdout.write(`${label}: ${JSON.stringify({ ...summary, lcp_ms: lcp && Math.round(lcp), cls, inp_ms: inp && Math.round(inp) })}\n`)
  if (failures.length) throw new Error(`${label} Lighthouse thresholds failed: ${failures.join(', ')}`)
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

  for (const [label, path] of [['home', '/'], ['game', '/game/complete-test-game']]) {
    const result = await lighthouse(`http://${HOST}:${PUBLIC_PORT}${path}`, {
      port: chrome.port,
      logLevel: 'error',
      output: 'json',
      onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
    })
    if (!result) throw new Error(`Lighthouse returned no result for ${label}`)
    await writeFile(`${REPORT_DIRECTORY}/${label}.json`, JSON.stringify(result.lhr, null, 2))
    validate(result.lhr, label)
  }
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
