/**
 * Build configuration for the ShikkhokPlus **admin** app: a separate
 * build (`npm run build:admin` → `dist-admin/`) from `admin.html`,
 * served at the root of its own hostname (`https://admin.<zone>/`).
 *
 * How it differs from the main app's `vite.config.ts`, each on purpose:
 *
 * 1. **Same origin only.** Every admin call goes to the host the page was
 *    loaded from, so `connect-src` is `'self'` and nothing else; there is
 *    no `VITE_API_BASE_URL`. An admin token can only ever travel to the
 *    admin host.
 * 2. **No service worker, no manifest, no install.** Nothing of the admin
 *    app is cached for offline use and it is not installable.
 * 3. **Base `/`, always**, and the page is written as `index.html`.
 * 4. **Local development** (`npm run dev:admin`) proxies `/v1/admin` to
 *    the API on :8000 and adds the `X-Admin-Edge` header the admin
 *    CloudFront distribution adds in a deployment, taken from
 *    `SHIKKHOKPLUS_ADMIN_EDGE_SECRET` — the same variable the API reads.
 */
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'

const VERSION = (
  JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
    version: string
  }
).version

/** Where `npm run dev:admin` forwards admin API calls. */
const DEV_API_TARGET = process.env.SHIKKHOKPLUS_API ?? 'http://localhost:8000'

/** The header the admin edge adds; the API refuses admin routes without it. */
const EDGE_HEADER = 'X-Admin-Edge'

/**
 * The admin page's Content-Security-Policy: same-origin connections only.
 *
 * @param dev Whether this is the dev server, which needs its HMR socket
 *   and the React dev runtime's inline preamble
 */
function contentSecurityPolicy(dev: boolean): Plugin {
  const policy = [
    "default-src 'self'",
    dev ? "connect-src 'self' ws:" : "connect-src 'self'",
    dev ? "script-src 'self' 'unsafe-inline'" : "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self'",
    "font-src 'self'",
    "manifest-src 'none'",
    "worker-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
  return {
    name: 'shikkhok-admin-csp',
    transformIndexHtml(html) {
      return html.replace('__CSP__', policy)
    },
  }
}

/**
 * Serve and emit `admin.html` as the app's `index.html`: the dev server
 * answers every page address with it (a client-side route such as
 * `/help/tickets` included), and the build writes it as `index.html`.
 */
function adminIndex(): Plugin {
  return {
    name: 'shikkhok-admin-index',
    // After Vite's own HTML plugin, which emits the page in generateBundle.
    enforce: 'post',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? '/'
        const page =
          req.method === 'GET' &&
          (req.headers.accept ?? '').includes('text/html') &&
          !url.startsWith('/v1/') &&
          !url.startsWith('/@') &&
          !url.startsWith('/src/') &&
          !url.startsWith('/node_modules/')
        if (page) req.url = '/admin.html'
        next()
      })
    },
    generateBundle(_options, bundle) {
      const page = bundle['admin.html']
      if (page) page.fileName = 'index.html'
    },
  }
}

export default defineConfig(({ command }) => {
  const edgeSecret = process.env.SHIKKHOKPLUS_ADMIN_EDGE_SECRET ?? ''
  if (command === 'serve' && !edgeSecret) {
    console.warn(
      `[admin] SHIKKHOKPLUS_ADMIN_EDGE_SECRET is not set: the API will answer every ` +
        `admin call with 404. Set it to the same value the API runs with.`,
    )
  }

  return {
    base: '/',
    define: { __APP_VERSION__: JSON.stringify(VERSION) },
    plugins: [react(), contentSecurityPolicy(command === 'serve'), adminIndex()],
    server: {
      port: 5174,
      strictPort: true,
      proxy: {
        '/v1/admin': {
          target: DEV_API_TARGET,
          changeOrigin: true,
          headers: edgeSecret ? { [EDGE_HEADER]: edgeSecret } : {},
        },
      },
    },
    preview: { port: 4174 },
    build: {
      target: 'es2022',
      outDir: 'dist-admin',
      emptyOutDir: true,
      sourcemap: true,
      rollupOptions: {
        input: 'admin.html',
        output: {
          manualChunks(id) {
            if (/node_modules\/(react|react-dom|react-router|scheduler)\//.test(id)) return 'vendor'
            return undefined
          },
        },
      },
    },
  }
})
