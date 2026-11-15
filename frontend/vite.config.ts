import { defineConfig } from 'vite'
import { reactRouter } from '@react-router/dev/vite'

const devApiTarget = process.env.DEV_API_BASE_URL ?? 'http://127.0.0.1:8000'

export default defineConfig(({ isSsrBuild }) => ({
  envDir: false,
  plugins: [reactRouter()],
  // Without groups the client build splits every lucide icon and each piece of the
  // React runtime into its own tiny chunk, so the first page load had ~27 module
  // preloads competing with the render-blocking CSS. Two stable chunks keep the
  // critical request chain short (and cache well across deploys).
  build: isSsrBuild ? undefined : {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'icons', test: /node_modules[\\/]lucide-react[\\/]/ },
            { name: 'framework', test: /node_modules[\\/](react|react-dom|react-router|scheduler|cookie|set-cookie-parser)[\\/]/ },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': devApiTarget,
      '/admin/': devApiTarget,
      // robots.txt is served statically from public/ (as it is in production);
      // the whole sitemap family — index, static and game chunks — is the backend's.
      '^/sitemap[\\w-]*\\.xml$': devApiTarget,
    },
  },
}))
