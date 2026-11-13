// Serves the production build for the browser tests, the way nginx does in
// production: API, admin API and sitemap requests go to the mock API, every
// other path goes to react-router-serve. Running the tests against the Vite dev
// server made them slow and flaky (on-demand dependency optimisation reloads the
// first page, and unbundled modules miss the navigation time budgets).
import http from 'node:http'
import { spawn } from 'node:child_process'

const HOST = '127.0.0.1'
const PUBLIC_PORT = Number(process.env.E2E_PORT ?? 4173)
const FRONTEND_PORT = PUBLIC_PORT + 1
const API_PORT = Number(process.env.E2E_API_PORT ?? 8001)

const isApiPath = (path) =>
  path.startsWith('/api/') || path.startsWith('/admin/') || /^\/sitemap[\w-]*\.xml(\?|$)/.test(path)

const frontend = spawn(
  process.execPath,
  ['node_modules/@react-router/serve/bin.cjs', 'build/server/index.js'],
  {
    env: {
      ...process.env,
      HOST,
      PORT: String(FRONTEND_PORT),
      INTERNAL_API_BASE_URL: `http://${HOST}:${API_PORT}`,
    },
    stdio: ['ignore', 'inherit', 'inherit'],
  },
)
frontend.on('exit', (code) => process.exit(code ?? 1))

const proxy = http.createServer((request, response) => {
  const path = request.url ?? '/'
  const port = isApiPath(path) ? API_PORT : FRONTEND_PORT
  const upstream = http.request(
    { hostname: HOST, port, path, method: request.method, headers: { ...request.headers, host: `${HOST}:${port}` } },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers)
      upstreamResponse.pipe(response)
    },
  )
  upstream.on('error', (error) => {
    if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'text/plain' })
    response.end(`Proxy error: ${error.message}`)
  })
  request.pipe(upstream)
})
proxy.listen(PUBLIC_PORT, HOST)

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    frontend.kill(signal)
    proxy.close()
  })
}
