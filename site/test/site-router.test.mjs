// The site's CloudFront Function (infra/modules/site/functions/site-router.js).
//
// It is plain JavaScript for the cloudfront-js-2.0 runtime with no module
// syntax, so it is loaded from the Terraform module and run here exactly as
// written -- the same approach as web/src/deploy/cloudfront-functions.test.ts
// for the web client's functions.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'

const FILE = join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  '..',
  'infra',
  'modules',
  'site',
  'functions',
  'site-router.js',
)
const source = readFileSync(FILE, 'utf8')
const handler = new Function(`${source}\nreturn handler`)()

const req = (uri, host = 'shikkhokplus.example.com', querystring = {}) => ({
  request: { uri, querystring, headers: { host: { value: host } } },
})
const moved = (location) => ({
  statusCode: 301,
  statusDescription: 'Moved Permanently',
  headers: { location: { value: location } },
})

describe('site-router', () => {
  it('uses nothing the cloudfront-js-2.0 runtime lacks', () => {
    // No module syntax, no timers, no network: the runtime has none of them.
    for (const banned of ['import ', 'export ', 'require(', 'setTimeout', 'fetch(', 'console.']) {
      assert.ok(!source.includes(banned), `site-router.js uses ${banned}`)
    }
  })

  describe('www', () => {
    it('redirects www to the bare host, keeping the path', () => {
      assert.deepEqual(handler(req('/faq/', 'www.shikkhokplus.example.com')), moved('https://shikkhokplus.example.com/faq/'))
    })

    it('redirects the www root', () => {
      assert.deepEqual(handler(req('/', 'www.shikkhokplus.example.com')), moved('https://shikkhokplus.example.com/'))
    })

    it('keeps the query string, including repeated keys and bare flags', () => {
      const qs = {
        utm_source: { value: 'sms' },
        tag: { value: 'a', multiValue: [{ value: 'a' }, { value: 'b' }] },
        flag: { value: '' },
      }
      assert.deepEqual(
        handler(req('/bn/', 'www.shikkhokplus.example.com', qs)),
        moved('https://shikkhokplus.example.com/bn/?utm_source=sms&tag=a&tag=b&flag'),
      )
    })

    it('treats the Host header case-insensitively', () => {
      assert.deepEqual(handler(req('/', 'WWW.Shikkhokplus.Example.com')), moved('https://shikkhokplus.example.com/'))
    })

    it('redirects www before mapping indexes, so it is one hop', () => {
      assert.deepEqual(handler(req('/faq', 'www.shikkhokplus.example.com')), moved('https://shikkhokplus.example.com/faq'))
    })
  })

  describe('directory indexes', () => {
    for (const [uri, object] of [
      ['/', '/index.html'],
      ['/faq/', '/faq/index.html'],
      ['/bn/', '/bn/index.html'],
      ['/bn/faq/', '/bn/faq/index.html'],
    ]) {
      it(`serves ${uri} from ${object}`, () => {
        assert.equal(handler(req(uri)).uri, object)
      })
    }

    for (const [uri, location] of [
      ['/faq', '/faq/'],
      ['/bn', '/bn/'],
      ['/bn/faq', '/bn/faq/'],
    ]) {
      it(`redirects ${uri} to ${location}`, () => {
        assert.deepEqual(handler(req(uri)), moved(location))
      })
    }

    it('keeps the query string on the slash redirect', () => {
      assert.deepEqual(handler(req('/faq', undefined, { q: { value: '1' } })), moved('/faq/?q=1'))
    })

    for (const uri of [
      '/assets/site.3f2a1c9b.css',
      '/assets/noto_regular.0a1b2c3d.ttf',
      '/robots.txt',
      '/sitemap.xml',
      '/favicon.ico',
      '/404.html',
      '/assets/missing.css',
    ]) {
      it(`passes the file ${uri} to S3 unchanged`, () => {
        const result = handler(req(uri))
        assert.equal(result.uri, uri)
        assert.equal(result.statusCode, undefined)
      })
    }
  })

  it('copes with a request that has no Host header', () => {
    const result = handler({ request: { uri: '/faq/', querystring: {}, headers: {} } })
    assert.equal(result.uri, '/faq/index.html')
  })
})
