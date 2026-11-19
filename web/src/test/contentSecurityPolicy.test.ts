// @vitest-environment node
/**
 * The Content-Security-Policy each build writes into its page, read from
 * the build configurations themselves rather than restated.
 *
 * Hub photos are uploaded straight to the media bucket by a presigned POST
 * and previewed from it by presigned GETs [H3 task 2], so the bucket's
 * regional endpoint (`VITE_MEDIA_ORIGIN`) joins `connect-src` and
 * `img-src` of the main app, and `img-src` of the admin app. An approved
 * photo's thumbnail is served from the public site [R1], so the site's
 * origin joins the main app's `img-src` too. Nothing else may widen.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ConfigEnv, Plugin, UserConfig } from 'vite'
import mainConfig from '../../vite.config'
import adminConfig from '../../vite.admin.config'

const MEDIA = 'https://shikkhokplus-staging-media.s3.ap-south-1.amazonaws.com'
const SITE = 'https://shikkhokplus.example.test'
const API = 'https://api.shikkhokplus.example.test'

type ConfigFn = (env: ConfigEnv) => UserConfig

/** Build one configuration and return the CSP its plugin writes. */
function policy(config: unknown, plugin: string): Map<string, string[]> {
  const resolved = (config as ConfigFn)({ mode: 'production', command: 'build' })
  const found = (resolved.plugins ?? [])
    .flat()
    .find((p): p is Plugin => !!p && (p as Plugin).name === plugin)
  if (!found) throw new Error(`no ${plugin} plugin`)
  const transform = found.transformIndexHtml as (html: string) => string
  const directives = new Map<string, string[]>()
  for (const part of transform('__CSP__').split('; ')) {
    const [name, ...sources] = part.split(' ')
    directives.set(name ?? '', sources)
  }
  return directives
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('main app CSP', () => {
  it('adds the media endpoint to connect-src and img-src, and the site to img-src', () => {
    vi.stubEnv('VITE_API_BASE_URL', API)
    vi.stubEnv('VITE_SITE_URL', SITE)
    vi.stubEnv('VITE_MEDIA_ORIGIN', MEDIA)
    const csp = policy(mainConfig, 'shikkhok-csp')

    expect(csp.get('connect-src')).toEqual(["'self'", API, MEDIA])
    expect(csp.get('img-src')).toEqual(["'self'", 'data:', MEDIA, SITE])
    expect(csp.get('form-action')).toEqual(["'self'"])
    expect(csp.get('default-src')).toEqual(["'self'"])
  })

  it('names nothing extra when the build names no bucket or site', () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('VITE_SITE_URL', '')
    vi.stubEnv('VITE_MEDIA_ORIGIN', '')
    const csp = policy(mainConfig, 'shikkhok-csp')

    expect(csp.get('connect-src')).toEqual(["'self'"])
    expect(csp.get('img-src')).toEqual(["'self'", 'data:'])
  })

  it.each([
    'http://shikkhokplus-staging-media.s3.ap-south-1.amazonaws.com',
    'https://shikkhokplus-staging-media.s3.amazonaws.com',
    'https://evil.example.test',
    `${MEDIA}/path`,
  ])('refuses a media origin that is not a regional S3 endpoint: %s', (origin) => {
    vi.stubEnv('VITE_MEDIA_ORIGIN', origin)
    expect(() => policy(mainConfig, 'shikkhok-csp')).toThrow(/VITE_MEDIA_ORIGIN/)
  })
})

describe('admin app CSP', () => {
  it('adds the media endpoint to img-src and nothing else', () => {
    vi.stubEnv('VITE_MEDIA_ORIGIN', MEDIA)
    const csp = policy(adminConfig, 'shikkhok-admin-csp')

    expect(csp.get('img-src')).toEqual(["'self'", MEDIA])
    expect(csp.get('connect-src')).toEqual(["'self'"])
  })

  it('stays same-origin when the build names no bucket', () => {
    vi.stubEnv('VITE_MEDIA_ORIGIN', '')
    const csp = policy(adminConfig, 'shikkhok-admin-csp')

    expect(csp.get('img-src')).toEqual(["'self'"])
  })

  it('refuses a media origin that is not a regional S3 endpoint', () => {
    vi.stubEnv('VITE_MEDIA_ORIGIN', 'https://evil.example.test')
    expect(() => policy(adminConfig, 'shikkhok-admin-csp')).toThrow(/VITE_MEDIA_ORIGIN/)
  })
})
