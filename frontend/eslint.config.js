import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'build', '.react-router']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    // Hydration safety: the server renders in the container's time zone and
    // locale, the browser in the visitor's. Anything that reads the local zone,
    // the locale or the clock during render makes the two disagree (React #418,
    // dates a day off). Format through utils/format.ts and take "now" from the
    // route loader (`renderedAt`); client-only code uses utils/clock.ts.
    files: ['src/**/*.{ts,tsx}'],
    ignores: [
      'src/utils/**',
      'src/services/**',
      'src/routes/**',
      'src/root.tsx',
      'src/**/*.server.ts',
      'src/pages/admin/**',
      'src/pages/AdminPage.tsx',
    ],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "CallExpression[callee.property.name=/^toLocale(Date|Time)?String$/]",
          message: 'Locale/zone-dependent formatting breaks hydration. Use utils/format.ts (formatIsoDate, formatNumber).',
        },
        {
          selector: "CallExpression[callee.object.name='Date'][callee.property.name='now']",
          message: 'Date.now() in a render path breaks hydration. Take renderedAt from the route loader, or use clientNow() in client-only code.',
        },
        {
          selector: "NewExpression[callee.name='Date'][arguments.length=0]",
          message: 'new Date() reads the clock; take renderedAt from the route loader, or use utils/clock.ts in client-only code.',
        },
        {
          selector: "CallExpression[callee.property.name=/^get(FullYear|Month|Date|Day|Hours)$/]",
          message: 'Local-zone date getters differ between server and browser. Use the getUTC* variants.',
        },
        {
          selector: "MemberExpression[object.name='Intl'][property.name='DateTimeFormat']",
          message: 'Intl.DateTimeFormat must pin timeZone and locale; build it in utils/format.ts.',
        },
      ],
    },
  },
  {
    files: ['src/routes/**/*.{ts,tsx}', 'src/root.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
