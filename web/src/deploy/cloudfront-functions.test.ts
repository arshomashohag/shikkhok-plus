/**
 * The two CloudFront Functions in infra/modules/cdn/functions/. They are
 * plain JavaScript for the cloudfront-js-2.0 runtime, so they are loaded
 * from the Terraform module and run here exactly as written.
 *
 * The property that matters most: neither function can change what an
 * API request reaches.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

interface CfRequest {
  uri: string
  headers: Record<string, { value: string }>
}
type CfResult = CfRequest | { statusCode: number; headers: Record<string, { value: string }> }

const FUNCTIONS = resolve(process.cwd(), '..', 'infra', 'modules', 'cdn', 'functions')

function load(
  file: string,
  vars: Record<string, string> = {},
): (e: { request: CfRequest }) => CfResult {
  let src = readFileSync(resolve(FUNCTIONS, file), 'utf8')
  for (const [k, v] of Object.entries(vars)) src = src.replaceAll('${' + k + '}', v)
  return new Function(`${src}\nreturn handler`)() as (e: { request: CfRequest }) => CfResult
}

const req = (uri: string, host = 'api.shikkhokplus.example.com'): { request: CfRequest } => ({
  request: { uri, headers: { host: { value: host } } },
})

describe('ui-router (on /ui and /ui/*)', () => {
  const handler = load('ui-router.js')

  it('redirects the bare /ui to the service worker scope', () => {
    expect(handler(req('/ui'))).toEqual({
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: { location: { value: '/ui/' } },
    })
  })

  it.each(['/ui/', '/ui/dues', '/ui/batches/93eb0d57-6a0b-4f87-8067-86298f00ae45', '/ui/signin'])(
    'serves the app for the client route %s',
    (uri) => {
      expect(handler(req(uri))).toMatchObject({ uri: '/ui/index.html' })
    },
  )

  it.each([
    '/ui/index.html',
    '/ui/sw.js',
    '/ui/manifest.webmanifest',
    '/ui/assets/index-Iyq8Vukz.js',
    '/ui/fonts/noto_regular.ttf',
    '/ui/icons/icon-192.png',
    '/ui/assets/missing.js',
  ])('passes the real file %s to S3 unchanged', (uri) => {
    expect(handler(req(uri))).toMatchObject({ uri })
  })
})

describe('ui-host-root (on the default, API, behaviour)', () => {
  const ui = 'app.shikkhokplus.example.com'
  const handler = load('ui-host-root.js.tftpl', { ui_fqdn: ui })

  it('sends the UI hostname’s root to the app', () => {
    expect(handler(req('/', ui))).toMatchObject({
      statusCode: 302,
      headers: { location: { value: '/ui/' } },
    })
  })

  it.each([
    ['/', 'api.shikkhokplus.example.com'],
    ['/v1/me', ui],
    ['/v1/me', 'api.shikkhokplus.example.com'],
    ['/health', ui],
    ['/account-deletion', ui],
  ])('leaves %s on %s exactly as it was', (uri, host) => {
    const event = req(uri, host)
    expect(handler(event)).toBe(event.request)
    expect(event.request.uri).toBe(uri)
  })

  it('tolerates a request with no Host header', () => {
    const event = { request: { uri: '/', headers: {} } }
    expect(handler(event)).toBe(event.request)
  })
})

it('no API route can be shadowed by the /ui behaviours', () => {
  const spec = JSON.parse(readFileSync(resolve(process.cwd(), '..', 'openapi.json'), 'utf8')) as {
    paths: Record<string, unknown>
  }
  const shadowed = Object.keys(spec.paths).filter((p) => p === '/ui' || p.startsWith('/ui/'))
  expect(shadowed).toEqual([])
})
