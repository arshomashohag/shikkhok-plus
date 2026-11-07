// Builds the public site (site/src) into site/dist.
//
// Zero dependencies, on purpose: the site is five pages of HTML and one
// stylesheet, and a static-site generator would be the largest thing in
// it. Everything a generator would have bought is here in a page of code:
//
//   * **Content-hashed assets.** Every file under src/assets is emitted as
//     assets/<name>.<hash>.<ext>, and every reference to it -- in the pages
//     and inside the stylesheet -- is rewritten. That is what lets the
//     deploy mark assets `immutable` for a year: a changed file is a new
//     URL, so no cache anywhere can serve a stale one.
//   * **One layout, two languages.** Pages are plain HTML fragments with a
//     small JSON front matter; the layout, header and footer are partials.
//     English lives at /, Bangla at /bn/, and a page without its
//     counterpart fails the build rather than shipping a broken language
//     switch.
//   * **Environment URLs at build time.** SITE_URL (canonical and hreflang
//     links, the sitemap), WEB_APP_URL and API_URL differ per environment,
//     so they are substituted here rather than hard-coded.
//
// An unknown {{variable}} or a reference to an asset that does not exist is
// a build error, never a silently broken page.

import { createHash } from 'node:crypto'
import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, extname, join, relative, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
export const SRC = join(HERE, 'src')
export const DIST = join(HERE, 'dist')

export const PLAY_URL = 'https://play.google.com/store/apps/details?id=com.shikkhokplus.app'
// The one public contact address, already published in docs/legal/PRIVACY.md.
export const CONTACT_EMAIL = 'shohagsiraj.ru@gmail.com'

// Eight hex characters of SHA-256: a name, not a security property.
export const HASH_LENGTH = 8

// Every extension the build may emit under assets/. The deploy workflow
// sets each one's Content-Type explicitly and refuses a file it has no
// type for, so adding one here means adding it there too.
export const ASSET_EXTENSIONS = ['.css', '.svg', '.png', '.webp', '.ttf']

// Local-preview defaults: `make up` serves the API on :8000 and
// `make web-dev` the web app on :5173. The deploy always sets all three.
export const DEFAULTS = {
  SITE_URL: 'http://localhost:8080',
  WEB_APP_URL: 'http://localhost:5173/',
  API_URL: 'http://localhost:8000',
}

const LANGS = {
  en: {
    site_name: 'ShikkhokPlus',
    og_locale: 'en_US',
    skip_label: 'Skip to content',
    og_image_alt: 'ShikkhokPlus: attendance, marks and fees for tutors and coaching centres.',
  },
  bn: {
    site_name: 'শিক্ষকপ্লাস',
    og_locale: 'bn_BD',
    skip_label: 'মূল লেখায় যান',
    og_image_alt: 'শিক্ষকপ্লাস: শিক্ষক ও কোচিং সেন্টারের জন্য হাজিরা, নম্বর ও ফি।',
  },
}

/**
 * Reads and validates the three environment URLs.
 *
 * SITE_URL must be an origin (the site is served at the root of its
 * host), and loses any trailing slash so `${SITE_URL}/faq/` is exact.
 */
export function resolveConfig(env = process.env) {
  const pick = (name) => (env[name] && env[name].trim()) || DEFAULTS[name]
  const url = (name) => {
    const value = pick(name)
    let parsed
    try {
      parsed = new URL(value)
    } catch {
      throw new Error(`${name} is not a URL: ${JSON.stringify(value)}`)
    }
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      throw new Error(`${name} must be http(s): ${value}`)
    }
    return { value, parsed }
  }

  const site = url('SITE_URL')
  if (site.parsed.pathname !== '/' || site.parsed.search || site.parsed.hash) {
    throw new Error(`SITE_URL must be an origin with no path: ${site.value}`)
  }
  const api = url('API_URL')
  return {
    siteUrl: site.parsed.origin,
    webAppUrl: url('WEB_APP_URL').value,
    apiUrl: api.value.replace(/\/+$/, ''),
  }
}

const escapeHtml = (s) =>
  s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')

/**
 * `{{name}}` is HTML-escaped, `{{{name}}}` is inserted as is. One pass, so
 * inserted text is never itself scanned for placeholders.
 */
export function render(template, vars, where) {
  return template.replace(/\{\{\{\s*([\w]+)\s*\}\}\}|\{\{\s*([\w]+)\s*\}\}/g, (_, raw, esc) => {
    const key = raw ?? esc
    if (!(key in vars)) throw new Error(`${where}: unknown variable {{${key}}}`)
    return raw ? String(vars[key]) : escapeHtml(String(vars[key]))
  })
}

async function walk(dir) {
  const out = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...(await walk(full)))
    else out.push(full)
  }
  return out.sort()
}

const toPosix = (p) => p.split(sep).join('/')
const hashOf = (buf) => createHash('sha256').update(buf).digest('hex').slice(0, HASH_LENGTH)

// A reference to a source asset, wherever it appears: an attribute, a
// CSS url(), or the tail of an absolute og:image URL.
const ASSET_REF = /\/assets\/[A-Za-z0-9_\-./]+/g

function rewriteAssets(text, assetMap, where) {
  return text.replace(ASSET_REF, (ref) => {
    const out = assetMap.get(ref)
    if (!out) throw new Error(`${where}: ${ref} is not a file under src/assets`)
    return out
  })
}

/** `<!--meta {json} -->` at the top of a page, then the body. */
function parsePage(source, where) {
  const match = source.match(/^<!--meta\s*([\s\S]*?)-->\s*/)
  if (!match) throw new Error(`${where}: missing <!--meta {...} --> front matter`)
  let meta
  try {
    meta = JSON.parse(match[1])
  } catch (e) {
    throw new Error(`${where}: front matter is not JSON (${e.message})`)
  }
  for (const key of ['title', 'description']) {
    if (typeof meta[key] !== 'string' || !meta[key].trim()) {
      throw new Error(`${where}: front matter needs a non-empty "${key}"`)
    }
  }
  return { meta, body: source.slice(match[0].length) }
}

/** pages/faq/index.html -> /faq/, pages/404.html -> /404.html */
function urlPathOf(rel) {
  const p = '/' + rel
  return p.endsWith('/index.html') ? p.slice(0, -'index.html'.length) : p
}

const langOf = (path) => (path === '/bn/' || path.startsWith('/bn/') ? 'bn' : 'en')
const alternateOf = (path) => (langOf(path) === 'bn' ? path.slice(3) : '/bn' + path)

/**
 * Builds the site. Returns what it wrote, for the tests and the log.
 */
export async function build({ outDir = DIST, env = process.env } = {}) {
  const config = resolveConfig(env)
  await rm(outDir, { recursive: true, force: true })
  await mkdir(join(outDir, 'assets'), { recursive: true })

  // 1. Assets. Everything but CSS first, so the stylesheet can be
  //    rewritten to the hashed names before it is hashed itself.
  const assetMap = new Map()
  const emitted = new Set()
  const assetFiles = await walk(join(SRC, 'assets'))
  const emit = async (file, content) => {
    const ext = extname(file)
    if (!ASSET_EXTENSIONS.includes(ext)) {
      throw new Error(`${file}: ${ext} is not in ASSET_EXTENSIONS (and the deploy has no Content-Type for it)`)
    }
    const stem = file.split(sep).pop().slice(0, -ext.length)
    const name = `${stem}.${hashOf(content)}${ext}`
    if (emitted.has(name)) throw new Error(`two assets would both be emitted as ${name}`)
    emitted.add(name)
    await writeFile(join(outDir, 'assets', name), content)
    assetMap.set('/assets/' + toPosix(relative(join(SRC, 'assets'), file)), `/assets/${name}`)
  }
  for (const file of assetFiles.filter((f) => extname(f) !== '.css')) {
    await emit(file, await readFile(file))
  }
  for (const file of assetFiles.filter((f) => extname(f) === '.css')) {
    const css = rewriteAssets(await readFile(file, 'utf8'), assetMap, file)
    await emit(file, Buffer.from(css))
  }

  // 2. Pages.
  const partial = (name) => readFile(join(SRC, 'partials', `${name}.html`), 'utf8')
  const layout = await partial('layout')
  const pageFiles = (await walk(join(SRC, 'pages'))).filter((f) => f.endsWith('.html'))
  const pages = []
  for (const file of pageFiles) {
    const rel = toPosix(relative(join(SRC, 'pages'), file))
    const { meta, body } = parsePage(await readFile(file, 'utf8'), rel)
    const path = urlPathOf(rel)
    const standalone = meta.standalone === true
    pages.push({ file, rel, path, meta, body, standalone, lang: standalone ? 'en' : langOf(path) })
  }
  const paths = new Set(pages.map((p) => p.path))
  for (const page of pages) {
    if (!page.standalone && !paths.has(alternateOf(page.path))) {
      throw new Error(`${page.rel}: no ${langOf(alternateOf(page.path))} counterpart at ${alternateOf(page.path)}`)
    }
  }

  for (const page of pages) {
    const { path, lang, standalone, meta } = page
    const canonical = config.siteUrl + path
    let headLinks
    if (standalone) {
      headLinks = '<meta name="robots" content="noindex">'
    } else {
      const en = config.siteUrl + (lang === 'en' ? path : alternateOf(path))
      const bn = config.siteUrl + (lang === 'bn' ? path : alternateOf(path))
      headLinks = [
        `<link rel="canonical" href="${escapeHtml(canonical)}">`,
        `<link rel="alternate" hreflang="en" href="${escapeHtml(en)}">`,
        `<link rel="alternate" hreflang="bn" href="${escapeHtml(bn)}">`,
        `<link rel="alternate" hreflang="x-default" href="${escapeHtml(en)}">`,
        `<meta property="og:locale:alternate" content="${LANGS[lang === 'en' ? 'bn' : 'en'].og_locale}">`,
      ].join('\n')
    }
    const vars = {
      ...LANGS[lang],
      lang,
      title: meta.title,
      description: meta.description,
      url: canonical,
      alternate_path: standalone ? '/' : alternateOf(path),
      faq_current: path.endsWith('/faq/') ? ' aria-current="page"' : '',
      head_links: headLinks,
      SITE_URL: config.siteUrl,
      WEB_APP_URL: config.webAppUrl,
      API_URL: config.apiUrl,
      ACCOUNT_DELETION_URL: `${config.apiUrl}/account-deletion`,
      PLAY_URL,
      CONTACT_EMAIL,
    }
    const chrome = standalone ? '404' : lang
    vars.header = render(await partial(`header.${chrome}`), vars, `header.${chrome}`)
    vars.footer = render(await partial(`footer.${chrome}`), vars, `footer.${chrome}`)
    vars.content = render(page.body, vars, page.rel)
    const html = rewriteAssets(render(layout, vars, 'layout'), assetMap, page.rel)

    const out = join(outDir, ...page.rel.split('/'))
    await mkdir(dirname(out), { recursive: true })
    await writeFile(out, html)
  }

  // 3. Unhashed files at fixed URLs (favicon.ico, the font licence).
  for (const file of await walk(join(SRC, 'static'))) {
    const rel = relative(join(SRC, 'static'), file)
    await mkdir(dirname(join(outDir, rel)), { recursive: true })
    await copyFile(file, join(outDir, rel))
  }

  // 4. robots.txt and the sitemap, which need SITE_URL.
  const indexable = pages.filter((p) => !p.standalone)
  await writeFile(
    join(outDir, 'robots.txt'),
    `User-agent: *\nAllow: /\n\nSitemap: ${config.siteUrl}/sitemap.xml\n`,
  )
  const urls = indexable
    .map((p) => {
      const en = config.siteUrl + (p.lang === 'en' ? p.path : alternateOf(p.path))
      const bn = config.siteUrl + (p.lang === 'bn' ? p.path : alternateOf(p.path))
      return [
        '  <url>',
        `    <loc>${escapeHtml(config.siteUrl + p.path)}</loc>`,
        `    <xhtml:link rel="alternate" hreflang="en" href="${escapeHtml(en)}"/>`,
        `    <xhtml:link rel="alternate" hreflang="bn" href="${escapeHtml(bn)}"/>`,
        `    <xhtml:link rel="alternate" hreflang="x-default" href="${escapeHtml(en)}"/>`,
        '  </url>',
      ].join('\n')
    })
    .join('\n')
  await writeFile(
    join(outDir, 'sitemap.xml'),
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' +
      urls +
      '\n</urlset>\n',
  )

  return {
    outDir,
    config,
    assets: assetMap,
    pages: pages.map(({ rel, path, lang, standalone }) => ({ rel, path, lang, standalone })),
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = await build()
  const { siteUrl, webAppUrl, apiUrl } = result.config
  console.log(`Built ${result.pages.length} pages and ${result.assets.size} assets into ${result.outDir}`)
  console.log(`  SITE_URL    ${siteUrl}`)
  console.log(`  WEB_APP_URL ${webAppUrl}`)
  console.log(`  API_URL     ${apiUrl}`)
}
