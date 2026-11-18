import { expect, test } from '@playwright/test'

// src/entry.server.tsx removes non-essential modulepreload hints by chunk name. If a
// chunk is renamed the filter would silently strip every hint, so pin the essential ones.
test('SSR head keeps the entry, runtime and framework modulepreloads and trims the rest', async ({ request }) => {
  const html = await (await request.get('/')).text()
  const head = html.slice(0, html.indexOf('</head>'))
  const preloads = [...head.matchAll(/<link rel="modulepreload" href="\/assets\/([^"]+)"/g)].map((match) => match[1])
  for (const chunk of ['entry.client', 'rolldown-runtime', 'framework']) {
    expect(preloads.some((name) => name.startsWith(`${chunk}-`)), `${chunk} modulepreload`).toBe(true)
  }
  expect(preloads.length).toBeLessThanOrEqual(6)
})
