/// <reference types="vitest/config" />
/**
 * Build configuration for the ShikkhokPlus web client.
 *
 * Three decisions live here rather than in code, and each is deliberate:
 *
 * 1. **The service worker caches the app shell and nothing else.** Every
 *    `/v1/` response carries a child's name, marks or fees. Persisting
 *    those in the browser's Cache Storage would put children's data at
 *    rest, unencrypted, on a machine that may be shared — which the
 *    Android client avoids by encrypting its offline copies. So API
 *    traffic is never cached, never pre-cached, and never answered from
 *    the navigation fallback. Offline, the shell opens and says so.
 * 2. **The API origin is fixed at build time** (`VITE_API_BASE_URL`), and
 *    the Content-Security-Policy's `connect-src` is generated from it, so
 *    the page cannot be talked into sending a token anywhere else.
 * 3. **Local development is same-origin** through Vite's proxy, so no
 *    CORS configuration is needed on a developer's machine.
 * 4. **The path it is served under is fixed at build time** (`WEB_BASE`,
 *    default `/`). The deploy builds with `/ui/`, the path CloudFront
 *    routes to the web bucket on the API's own distribution
 *    (infra/modules/cdn/web.tf). Assets, the manifest's scope and the
 *    service worker's scope all follow it, so the worker can never
 *    claim the API's paths.
 */
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { readFileSync } from 'node:fs'

const VERSION = (
  JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
    version: string
  }
).version

/** The path the app is served under: `/` locally, `/ui/` when deployed. */
const BASE = process.env.WEB_BASE ?? '/'
if (!/^\/([a-z0-9-]+\/)*$/.test(BASE)) {
  throw new Error(`WEB_BASE must start and end with '/', got '${BASE}'`)
}

/** Where `npm run dev` forwards API calls. */
const DEV_API_TARGET = process.env.SHIKKHOKPLUS_API ?? 'http://127.0.0.1:8000'

/**
 * Paths the backend owns. The service worker must never answer these
 * with the cached `index.html`, and the dev server forwards them.
 */
const BACKEND_PATHS = ['/v1', '/health', '/account-deletion', '/staging']

/**
 * Write the Content-Security-Policy into `index.html`.
 *
 * @param apiBase The API origin the build talks to; empty for same-origin
 * @param dev Whether this is the dev server, which needs its HMR socket
 */
function contentSecurityPolicy(apiBase: string, dev: boolean): Plugin {
  const connect = ["'self'"]
  if (apiBase) connect.push(new URL(apiBase).origin)
  if (dev) connect.push('ws:')
  const policy = [
    "default-src 'self'",
    `connect-src ${connect.join(' ')}`,
    // The React dev runtime injects an inline preamble; the production
    // build has no inline script at all.
    dev ? "script-src 'self' 'unsafe-inline'" : "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
  return {
    name: 'shikkhok-csp',
    transformIndexHtml(html) {
      return html.replace('__CSP__', policy)
    },
  }
}

export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiBase = env.VITE_API_BASE_URL ?? ''
  if (apiBase && command === 'build' && !apiBase.startsWith('https://')) {
    // The same rule ApiClient.kt enforces on Android: tokens travel over
    // TLS or not at all.
    throw new Error(`VITE_API_BASE_URL must be https, got '${apiBase}'`)
  }

  return {
    base: BASE,
    define: { __APP_VERSION__: JSON.stringify(VERSION) },
    plugins: [
      react(),
      contentSecurityPolicy(apiBase, command === 'serve'),
      VitePWA({
        registerType: 'prompt',
        injectRegister: false,
        includeAssets: ['fonts/*.ttf', 'icons/*.svg', 'icons/apple-touch-icon.png'],
        manifest: {
          id: BASE,
          name: 'ShikkhokPlus',
          short_name: 'ShikkhokPlus',
          description:
            'Classes, marks and fees for private tuition — for teachers, students and guardians.',
          lang: 'bn',
          dir: 'ltr',
          start_url: BASE,
          scope: BASE,
          display: 'standalone',
          display_override: ['window-controls-overlay', 'standalone'],
          orientation: 'any',
          theme_color: '#1D4F91',
          background_color: '#F4F6F9',
          categories: ['education', 'productivity'],
          icons: [
            { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
            { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
            {
              src: 'icons/icon-maskable-512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
          shortcuts: [
            { name: 'Today', short_name: 'Today', url: `${BASE}today` },
            { name: 'Dues', short_name: 'Dues', url: `${BASE}dues` },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,svg,png,ttf,woff2}'],
          navigateFallback: `${BASE}index.html`,
          navigateFallbackDenylist: BACKEND_PATHS.map((p) => new RegExp(`^${p}(/|$)`)),
          // No runtimeCaching entry: API responses are never stored. See
          // the module comment, point 1.
          runtimeCaching: [],
          cleanupOutdatedCaches: true,
          maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        },
        devOptions: { enabled: false },
      }),
    ],
    server: {
      port: 5173,
      proxy: Object.fromEntries(
        BACKEND_PATHS.map((p) => [p, { target: DEV_API_TARGET, changeOrigin: true }]),
      ),
    },
    build: {
      target: 'es2022',
      sourcemap: true,
      rollupOptions: {
        output: {
          // React and the router change far less often than the app, so
          // they get their own long-lived chunk: a deploy that changes a
          // screen leaves this one in every browser's cache.
          manualChunks(id) {
            if (/node_modules\/(react|react-dom|react-router|scheduler)\//.test(id)) return 'vendor'
            return undefined
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      restoreMocks: true,
    },
  }
})
