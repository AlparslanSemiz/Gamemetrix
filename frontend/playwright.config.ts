import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: 'node tests/mock-api.mjs',
      port: 8001,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      // Production build behind an nginx-like proxy (see tests/e2e-server.mjs).
      // The catalog timeout is a build-time value, so the tests build their own copy.
      command: 'npx react-router build && node tests/e2e-server.mjs',
      url: 'http://127.0.0.1:4173/',
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        VITE_CATALOG_REQUEST_TIMEOUT_MS: '500',
      },
    },
  ],
})
