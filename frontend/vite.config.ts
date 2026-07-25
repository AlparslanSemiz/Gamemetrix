import { defineConfig } from 'vite'
import { reactRouter } from '@react-router/dev/vite'

const devApiTarget = process.env.DEV_API_BASE_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  envDir: false,
  plugins: [reactRouter()],
  server: {
    proxy: {
      '/api': devApiTarget,
      '/admin/': devApiTarget,
      // robots.txt is served statically from public/ (as it is in production);
      // the whole sitemap family — index, static and game chunks — is the backend's.
      '^/sitemap[\\w-]*\\.xml$': devApiTarget,
    },
  },
})
