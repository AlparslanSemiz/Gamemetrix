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
            // Small app modules used by more than one route (services, state, utils, hooks, the
            // catalog query helpers). Split one chunk per module they made the home page import
            // 19 chunks in a four-level chain (route -> App -> format/useCollectionActions ->
            // useAccount), each level fetched only after the previous one parsed; Lighthouse
            // charged the whole chain to LCP. Grouped: 7 chunks, three levels. JS only:
            // CSS-importing components stay out so no route gains a stylesheet
            // (tests/e2e/home-lcp.spec.ts pins the home script count).
            {
              name: 'shared',
              minShareCount: 2,
              test: /[\\/]src[\\/]((services|state|utils|hooks)[\\/][^\\/]+\.tsx?|catalog[\\/](queryParams|config|snapshot)\.ts|components[\\/](RouteErrorPage|ScoreRing|platforms)\.tsx?)$/,
            },
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
