/**
 * Token renewal. The security-critical property: a refresh token is never
 * presented twice, because the server treats a rotated-out token as theft
 * and revokes the whole family — which would sign the person out on every
 * device.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { request, revokeSession } from './client'
import { ApiError } from './errors'
import { clearTokens, readTokens, saveTokens } from './tokens'

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let calls: { url: string; init: RequestInit }[] = []
function mockFetch(handler: Handler) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return handler(url, init)
    }),
  )
}

const auth = (init: RequestInit) => (init.headers as Record<string, string>).Authorization

beforeEach(() => {
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

describe('request', () => {
  it('sends the access token and decodes JSON', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    mockFetch(() => json(200, { ok: true }))
    await expect(request('GET', '/v1/me')).resolves.toEqual({ ok: true })
    expect(auth(calls[0]!.init)).toBe('Bearer A1')
  })

  it('renews first when the access token is about to lapse', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 10 })
    mockFetch((url) =>
      url.endsWith('/v1/auth/refresh')
        ? json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
        : json(200, {}),
    )
    await request('GET', '/v1/me')
    expect(calls.map((c) => c.url)).toEqual(['/v1/auth/refresh', '/v1/me'])
    expect(JSON.parse(calls[0]!.init.body as string)).toEqual({ refresh_token: 'R1' })
    expect(auth(calls[1]!.init)).toBe('Bearer A2')
    expect(readTokens()?.refresh).toBe('R2')
  })

  it('renews and repeats once on a 401', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    let first = true
    mockFetch((url) => {
      if (url.endsWith('/v1/auth/refresh'))
        return json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
      if (first) {
        first = false
        return json(401, {
          error: { code: 'UNAUTHENTICATED', message_key: 'auth.token.not_valid', retryable: false },
        })
      }
      return json(200, { ok: 1 })
    })
    await expect(request('GET', '/v1/me')).resolves.toEqual({ ok: 1 })
    expect(calls).toHaveLength(3)
  })

  it('spends a refresh token once even when many calls need it at the same moment', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 1 })
    mockFetch((url) =>
      url.endsWith('/v1/auth/refresh')
        ? json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
        : json(200, {}),
    )
    await Promise.all([request('GET', '/a'), request('GET', '/b'), request('GET', '/c')])
    expect(calls.filter((c) => c.url.endsWith('/refresh'))).toHaveLength(1)
  })

  it('adopts a pair another tab already rotated instead of spending the old one', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 1 })
    // Another tab rotates between this tab reading R1 and taking the lock.
    vi.stubGlobal('navigator', {
      ...navigator,
      locks: {
        request: async (_name: string, fn: () => Promise<unknown>) => {
          saveTokens({ access_token: 'A9', refresh_token: 'R9', expires_in: 900 })
          return fn()
        },
      },
    })
    mockFetch(() => json(200, {}))
    await request('GET', '/v1/me')
    expect(calls.map((c) => c.url)).toEqual(['/v1/me'])
    expect(auth(calls[0]!.init)).toBe('Bearer A9')
  })

  it('ends the session when the server refuses the refresh', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 1 })
    mockFetch(() =>
      json(401, {
        error: { code: 'UNAUTHENTICATED', message_key: 'auth.token.not_valid', retryable: false },
      }),
    )
    await expect(request('GET', '/v1/me')).rejects.toMatchObject({
      status: 401,
      messageKey: 'auth.token.not_valid',
    })
    expect(readTokens()).toBeNull()
  })

  it('keeps the session when the refresh fails for lack of a connection', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 1 })
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    const error = await request('GET', '/v1/me').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).offline).toBe(true)
    expect(readTokens()?.refresh).toBe('R1')
  })

  it('reads the server error envelope and never shows its own English', async () => {
    mockFetch(() =>
      json(409, {
        error: { code: 'CONFLICT', message_key: 'fees.payment.approval_zero', retryable: false },
      }),
    )
    await expect(request('POST', '/v1/x', { anonymous: true, body: {} })).rejects.toMatchObject({
      status: 409,
      code: 'CONFLICT',
      messageKey: 'fees.payment.approval_zero',
      retryable: false,
    })
  })

  it('treats a non-envelope 502 as unexpected and retryable', async () => {
    mockFetch(() => new Response('<html>Bad gateway</html>', { status: 502 }))
    await expect(request('GET', '/health', { anonymous: true })).rejects.toMatchObject({
      messageKey: 'error.unexpected',
      retryable: true,
    })
  })
})

describe('revokeSession [audit C-21]', () => {
  it('sends the refresh token to the logout route', async () => {
    mockFetch(() => new Response(null, { status: 204 }))
    await revokeSession('the-refresh-token')
    expect(calls.map((c) => c.url)).toEqual(['/v1/auth/logout'])
    expect(JSON.parse(calls[0]!.init.body as string)).toEqual({
      refresh_token: 'the-refresh-token',
    })
  })

  it('never throws when offline, so signing out still works', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    await expect(revokeSession('t')).resolves.toBeUndefined()
  })
})
