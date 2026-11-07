// The built site, checked as a visitor and a crawler would meet it.
//
// Every test reads a fresh build into a temporary directory, made with
// distinctive URLs so a value that leaked from the defaults, or a
// placeholder that was never substituted, shows up as a failure.

import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative, sep } from 'node:path'
import { after, before, describe, it } from 'node:test'

import { ASSET_EXTENSIONS, CONTACT_EMAIL, HASH_LENGTH, PLAY_URL, build, resolveConfig } from '../build.mjs'

const ENV = {
  SITE_URL: 'https://site.example.test/',
  WEB_APP_URL: 'https://app.example.test/ui/',
  API_URL: 'https://api.example.test/',
}
const SITE = 'https://site.example.test'

let out
let result
const files = []

const walk = (dir) =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)],
  )
const rel = (f) => relative(out, f).split(sep).join('/')
const read = (p) => readFileSync(join(out, ...p.split('/')), 'utf8')
const htmlFiles = () => files.filter((f) => f.endsWith('.html'))
const fileForPath = (path) => (path.endsWith('/') ? path + 'index.html' : path).replace(/^\//, '')

before(async () => {
  out = mkdtempSync(join(tmpdir(), 'site-build-'))
  result = await build({ outDir: out, env: ENV })
  files.push(...walk(out))
})

after(() => rmSync(out, { recursive: true, force: true }))

describe('build', () => {
  it('builds every page under src/pages', () => {
    const paths = result.pages.map((p) => p.path).sort()
    assert.deepEqual(paths, ['/', '/404.html', '/bn/', '/bn/faq/', '/faq/'])
    for (const page of result.pages) assert.ok(existsSync(join(out, page.rel)), `${page.rel} missing`)
  })

  it('substitutes every placeholder', () => {
    for (const f of files.filter((f) => /\.(html|css|xml|txt)$/.test(f))) {
      const text = readFileSync(f, 'utf8')
      assert.ok(!/\{\{/.test(text), `${rel(f)} still contains a {{placeholder}}`)
      assert.ok(!text.includes('localhost'), `${rel(f)} carries a local-preview default`)
    }
  })

  it('uses the environment URLs it was given', () => {
    for (const p of ['index.html', 'bn/index.html']) {
      const html = read(p)
      assert.ok(html.includes(`href="${ENV.WEB_APP_URL}"`), `${p}: web app link`)
      assert.ok(html.includes(`href="${PLAY_URL}"`), `${p}: Play Store link`)
      assert.ok(html.includes('href="https://api.example.test/account-deletion"'), `${p}: deletion page`)
      assert.ok(html.includes(`mailto:${CONTACT_EMAIL}`), `${p}: contact email`)
      assert.ok(html.includes('id="contact"'), `${p}: contact section`)
      assert.ok(html.includes('id="centres"') && html.includes('id="tutors"'), `${p}: centre and tutor sections`)
    }
  })
})

describe('links and assets', () => {
  it('resolves every internal link and asset reference', () => {
    const refs = []
    for (const f of htmlFiles()) {
      const html = readFileSync(f, 'utf8')
      for (const m of html.matchAll(/\s(?:href|src|content)="([^"]*)"/g)) refs.push([rel(f), m[1]])
    }
    for (const f of files.filter((f) => f.endsWith('.css'))) {
      for (const m of readFileSync(f, 'utf8').matchAll(/url\(\s*['"]?([^'")]+)['"]?\s*\)/g)) refs.push([rel(f), m[1]])
    }
    let checked = 0
    for (const [from, raw] of refs) {
      let ref = raw
      if (ref.startsWith(SITE + '/')) ref = ref.slice(SITE.length)
      if (!ref.startsWith('/') || ref.startsWith('//')) continue
      ref = ref.replace(/[#?].*$/, '')
      const target = fileForPath(ref)
      assert.ok(existsSync(join(out, ...target.split('/'))), `${from} -> ${raw} does not resolve (${target})`)
      checked++
    }
    assert.ok(checked > 40, `only ${checked} internal references checked`)
  })

  it('resolves every in-page fragment link', () => {
    for (const f of htmlFiles()) {
      const html = readFileSync(f, 'utf8')
      for (const m of html.matchAll(/href="([^"]*)#([\w-]+)"/g)) {
        const [, path, id] = m
        const target = path === '' ? rel(f) : fileForPath(path.replace(SITE, ''))
        if (path.startsWith('http') && !path.startsWith(SITE)) continue
        assert.ok(read(target).includes(`id="${id}"`), `${rel(f)}: #${id} not found in ${target}`)
      }
    }
  })

  it('names every asset by the hash of its content', () => {
    const assets = files.filter((f) => rel(f).startsWith('assets/'))
    assert.ok(assets.length >= 8)
    for (const f of assets) {
      const name = rel(f).slice('assets/'.length)
      const m = name.match(new RegExp(`^([\\w-]+)\\.([0-9a-f]{${HASH_LENGTH}})(\\.[a-z0-9]+)$`))
      assert.ok(m, `${name} is not <name>.<hash>.<ext>`)
      assert.ok(ASSET_EXTENSIONS.includes(m[3]), `${name}: ${m[3]} is not an allowed asset type`)
      const actual = createHash('sha256').update(readFileSync(f)).digest('hex').slice(0, HASH_LENGTH)
      assert.equal(m[2], actual, `${name} does not match its content`)
    }
  })

  it('emits only files the deploy knows how to serve', () => {
    for (const f of files) {
      const name = rel(f)
      if (name.startsWith('assets/')) continue
      assert.match(name, /(\.html|^robots\.txt|^sitemap\.xml|^favicon\.ico|^OFL\.txt)$/, `${name} is unexpected`)
    }
  })

  it('references every asset it ships, so nothing dead adds weight', () => {
    const text = files
      .filter((f) => /\.(html|css)$/.test(f))
      .map((f) => readFileSync(f, 'utf8'))
      .join('\n')
    for (const f of files.filter((f) => rel(f).startsWith('assets/'))) {
      assert.ok(text.includes('/' + rel(f)), `${rel(f)} is never referenced`)
    }
  })

  it('stays small', () => {
    let total = 0
    for (const f of files) {
      const size = statSync(f).size
      total += size
      if (/\.(webp|png)$/.test(f)) assert.ok(size < 150_000, `${rel(f)} is ${size} bytes`)
    }
    assert.ok(total < 900_000, `the whole site is ${total} bytes`)
  })
})

describe('no script, no inline style', () => {
  // The CSP is `default-src 'none'; style-src 'self'; ...` with no
  // script-src at all: an inline script, handler or style would be blocked
  // in the browser, so it is refused here first.
  for (const name of ['index.html', 'faq/index.html', 'bn/index.html', 'bn/faq/index.html', '404.html']) {
    it(name, () => {
      const html = read(name)
      assert.ok(!/<script\b/i.test(html), 'contains <script>')
      assert.ok(!/<style\b/i.test(html), 'contains <style>')
      assert.ok(!/\sstyle=/i.test(html), 'contains a style attribute')
      assert.ok(!/\son[a-z]+=/i.test(html), 'contains an inline event handler')
      assert.ok(!/javascript:/i.test(html), 'contains a javascript: URL')
      assert.ok(!/<iframe\b|<object\b|<embed\b/i.test(html), 'embeds third-party content')
    })
  }
})

describe('every page', () => {
  const head = (html, pattern) => (html.match(pattern) || [])[1]

  it('has a language, a title and a description', () => {
    for (const page of result.pages) {
      const html = read(page.rel)
      assert.equal(head(html, /<html lang="([^"]+)"/), page.lang, `${page.rel}: lang`)
      assert.ok(head(html, /<title>([^<]+)<\/title>/)?.trim(), `${page.rel}: title`)
      assert.ok(head(html, /<meta name="description" content="([^"]+)"/)?.trim(), `${page.rel}: description`)
      assert.ok(html.includes('<meta name="viewport"'), `${page.rel}: viewport`)
      assert.ok(html.includes('<main id="main">'), `${page.rel}: main landmark`)
    }
  })

  it('has a canonical URL and hreflang alternates for both languages', () => {
    for (const page of result.pages.filter((p) => !p.standalone)) {
      const html = read(page.rel)
      const enPath = page.lang === 'en' ? page.path : page.path.slice(3)
      const bnPath = page.lang === 'bn' ? page.path : '/bn' + page.path
      assert.ok(html.includes(`<link rel="canonical" href="${SITE}${page.path}">`), `${page.rel}: canonical`)
      assert.ok(html.includes(`hreflang="en" href="${SITE}${enPath}"`), `${page.rel}: hreflang en`)
      assert.ok(html.includes(`hreflang="bn" href="${SITE}${bnPath}"`), `${page.rel}: hreflang bn`)
      assert.ok(html.includes(`hreflang="x-default" href="${SITE}${enPath}"`), `${page.rel}: x-default`)
      assert.ok(html.includes(`property="og:url" content="${SITE}${page.path}"`), `${page.rel}: og:url`)
      const other = page.lang === 'en' ? bnPath : enPath
      assert.ok(html.includes(`class="lang-switch" href="${other}"`), `${page.rel}: language switch`)
    }
  })

  it('keeps the 404 page out of the index', () => {
    const html = read('404.html')
    assert.ok(html.includes('<meta name="robots" content="noindex">'))
    assert.ok(!html.includes('rel="canonical"'))
    assert.ok(html.includes('lang="bn"'), 'the 404 page also speaks Bangla')
  })
})

describe('the two languages mirror each other', () => {
  it('has a Bangla page for every English page and the reverse', () => {
    const indexable = result.pages.filter((p) => !p.standalone)
    const en = indexable.filter((p) => p.lang === 'en').map((p) => p.path).sort()
    const bn = indexable.filter((p) => p.lang === 'bn').map((p) => p.path.slice(3)).sort()
    assert.deepEqual(bn, en)
  })

  it('has the same sections on both home pages', () => {
    const ids = (p) => [...read(p).matchAll(/<section id="([\w-]+)"/g)].map((m) => m[1])
    assert.deepEqual(ids('bn/index.html'), ids('index.html'))
  })

  it('answers the same FAQ questions, in the same order, 12 to 16 of them', () => {
    const entries = (p) => [...read(p).matchAll(/<details id="([\w-]+)">\s*<summary>([^<]+)<\/summary>/g)]
    const en = entries('faq/index.html')
    const bn = entries('bn/faq/index.html')
    assert.ok(en.length >= 12 && en.length <= 16, `${en.length} English questions`)
    assert.equal(bn.length, en.length)
    assert.deepEqual(
      bn.map((m) => m[1]),
      en.map((m) => m[1]),
    )
    assert.equal((read('faq/index.html').match(/<details\b/g) || []).length, en.length)
    assert.equal((read('bn/faq/index.html').match(/<details\b/g) || []).length, bn.length)
  })

  it('writes the Bangla pages in Bangla', () => {
    for (const p of ['bn/index.html', 'bn/faq/index.html']) {
      const body = read(p).split('<main id="main">')[1]
      const bengali = (body.match(/[ঀ-৿]/g) || []).length
      const latin = (body.replace(/<[^>]+>/g, '').match(/[A-Za-z]/g) || []).length
      assert.ok(bengali > latin * 3, `${p}: ${bengali} Bengali letters against ${latin} Latin`)
    }
  })
})

describe('robots.txt and the sitemap', () => {
  it('points robots at the sitemap', () => {
    assert.equal(read('robots.txt'), `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`)
  })

  it('lists every indexable page, with alternates, and nothing else', () => {
    const xml = read('sitemap.xml')
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]).sort()
    const expected = result.pages
      .filter((p) => !p.standalone)
      .map((p) => SITE + p.path)
      .sort()
    assert.deepEqual(locs, expected)
    assert.equal((xml.match(/hreflang="bn"/g) || []).length, expected.length)
  })
})

describe('configuration', () => {
  it('falls back to local-preview defaults', () => {
    const c = resolveConfig({})
    assert.equal(c.siteUrl, 'http://localhost:8080')
    assert.equal(c.apiUrl, 'http://localhost:8000')
  })

  it('normalises trailing slashes on SITE_URL and API_URL only', () => {
    const c = resolveConfig(ENV)
    assert.equal(c.siteUrl, SITE)
    assert.equal(c.apiUrl, 'https://api.example.test')
    assert.equal(c.webAppUrl, ENV.WEB_APP_URL)
  })

  it('refuses a SITE_URL with a path, and anything that is not http(s)', () => {
    assert.throws(() => resolveConfig({ SITE_URL: 'https://x.test/site' }), /origin/)
    assert.throws(() => resolveConfig({ WEB_APP_URL: 'ftp://x.test/' }), /http/)
    assert.throws(() => resolveConfig({ API_URL: 'not a url' }), /not a URL/)
  })
})
