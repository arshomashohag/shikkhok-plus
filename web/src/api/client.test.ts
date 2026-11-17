/**
 * Token renewal. The security-critical property: a refresh token is never
 * presented twice, because the server treats a rotated-out token as theft
 * and revokes the whole family — which would sign the person out on every
 * device.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { request, requestText, revokeSession } from './client'
import {
  checkMyUsername,
  checkUsername,
  inviteMember,
  lookupAlreadyAdded,
  readHubPreview,
  removeContact,
  requestContactCode,
  setMyUsername,
  signInWithPassword,
  verifyCode,
} from './endpoints'
import { ApiError } from './errors'
import { clearTokens, readTokens, saveTokens } from './tokens'
import { clientVersion } from './platform'

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

// Pinned before `send()` changed [NFR8.7, functional-spec § 1 defect 5].
// A lookup aborted while it waits for renewal must not cost the rotated
// pair: the server rotated it, and the next renewal would otherwise
// present a rotated-out token and revoke the whole family.
describe('renewal survives an aborted caller [NFR8.7]', () => {
  it('stores the rotated pair, uses it next, and spends the refresh token once', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 10 })
    let release: () => void = () => undefined
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    mockFetch(async (url, init) => {
      if (url.endsWith('/v1/auth/refresh')) {
        await held
        return json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
      }
      // As a browser does: an aborted signal rejects with its reason.
      if (init.signal?.aborted) throw init.signal.reason
      return json(200, { status: 'available' })
    })

    const controller = new AbortController()
    const lookup = request('POST', '/v1/me/username-availability', {
      body: { username: 'nadia_k' },
      signal: controller.signal,
    })
    // Let `request()` reach the renewal and wait on it.
    await vi.waitFor(() => expect(calls.map((c) => c.url)).toEqual(['/v1/auth/refresh']))
    controller.abort('superseded')
    release()
    await expect(lookup).rejects.toBeDefined()

    expect(readTokens()).toMatchObject({ access: 'A2', refresh: 'R2' })
    await request('GET', '/v1/me')
    const last = calls[calls.length - 1]!
    expect(last.url).toBe('/v1/me')
    expect(auth(last.init)).toBe('Bearer A2')
    expect(calls.filter((c) => c.url.endsWith('/v1/auth/refresh'))).toHaveLength(1)
  })
})

// A superseded or timed-out lookup is cancelled, never "offline": the
// checker decides from its own flags, and the hint must not read as a
// lost connection [NFR8.8, functional-spec § 9 item 6].
describe('send() and an aborted signal [NFR8.8]', () => {
  /** As a browser does: an aborted signal rejects fetch with its reason. */
  const honourSignal = () =>
    mockFetch((_url, init) => {
      if (init.signal?.aborted) throw init.signal.reason
      return json(200, {})
    })

  it('a signal aborted with a string reason rejects with that reason', async () => {
    honourSignal()
    const controller = new AbortController()
    controller.abort('superseded')
    await expect(
      request('POST', '/v1/accounts/username-availability', {
        anonymous: true,
        body: { username: 'nadia_k' },
        signal: controller.signal,
      }),
    ).rejects.toBe('superseded')
  })

  it('a TimeoutError abort rejects with the reason, not error.network.unreachable', async () => {
    honourSignal()
    const reason = new DOMException('', 'TimeoutError')
    const error = await request('GET', '/x', {
      anonymous: true,
      signal: AbortSignal.abort(reason),
    }).catch((e: unknown) => e)
    expect(error).toBe(reason)
    expect(error).not.toBeInstanceOf(ApiError)
  })

  it('a reason-less abort still rejects as an AbortError', async () => {
    honourSignal()
    const controller = new AbortController()
    controller.abort()
    const error = await request('GET', '/x', { anonymous: true, signal: controller.signal }).catch(
      (e: unknown) => e,
    )
    // jsdom's DOMException is another realm's, so the name is what is checked.
    expect(error).not.toBeInstanceOf(ApiError)
    expect((error as { name?: string }).name).toBe('AbortError')
  })

  it('a plain fetch rejection with no abort still maps to error.network.unreachable', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    const controller = new AbortController()
    const error = await request('GET', '/x', { anonymous: true, signal: controller.signal }).catch(
      (e: unknown) => e,
    )
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).messageKey).toBe('error.network.unreachable')
  })
})

// Each new call's method, path and body, and no query string where a
// username, login, contact, password or code travels [NFR3.1] [NFR1.2].
describe('the identity API functions [frontend-components § 4]', () => {
  const sent = (i = 0) => {
    const call = calls[i]!
    const url = new URL(call.url, 'http://x')
    return {
      method: call.init.method,
      path: url.pathname,
      search: url.search,
      body: call.init.body ? (JSON.parse(call.init.body as string) as unknown) : undefined,
      auth: auth(call.init),
    }
  }

  beforeEach(() => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    mockFetch(() => json(200, { status: 'available' }))
  })

  it('signInWithPassword sends one login and no phone or email key, anonymously', async () => {
    for (const login of ['Rahim.Uddin', '01711234567', 'rina@example.com']) {
      await signInWithPassword(login, 'correct horse')
    }
    for (const [i, login] of ['Rahim.Uddin', '01711234567', 'rina@example.com'].entries()) {
      const s = sent(i)
      expect(s).toMatchObject({ method: 'POST', path: '/v1/auth/password', search: '' })
      expect(s.body).toEqual({ login, password: 'correct horse' })
      expect(s.body).not.toHaveProperty('phone')
      expect(s.body).not.toHaveProperty('email')
      expect(s.auth).toBeUndefined()
    }
  })

  it('verifyCode carries a username only when one is passed', async () => {
    await verifyCode({ phone: '01711234567' }, '123456')
    await verifyCode({ email: 'rina@example.com' }, '123456', 'rahim_math')
    expect(sent(0).body).toEqual({ phone: '01711234567', code: '123456' })
    expect(sent(0).body).not.toHaveProperty('username')
    expect(sent(1)).toMatchObject({ method: 'POST', path: '/v1/auth/verify', search: '' })
    expect(sent(1).body).toEqual({
      email: 'rina@example.com',
      code: '123456',
      username: 'rahim_math',
    })
  })

  it('checkUsername posts the name anonymously, with no query string', async () => {
    const controller = new AbortController()
    await checkUsername('nadia_k', controller.signal)
    expect(sent()).toMatchObject({
      method: 'POST',
      path: '/v1/accounts/username-availability',
      search: '',
      body: { username: 'nadia_k' },
    })
    expect(sent().auth).toBeUndefined()
    expect(calls[0]!.init.signal).toBe(controller.signal)
  })

  it('checkMyUsername posts the name as the signed-in account, with no query string', async () => {
    await checkMyUsername('nadia_k')
    expect(sent()).toMatchObject({
      method: 'POST',
      path: '/v1/me/username-availability',
      search: '',
      body: { username: 'nadia_k' },
      auth: 'Bearer A1',
    })
  })

  it('setMyUsername omits the password for a first choice and sends it for a change', async () => {
    await setMyUsername('nadia_k', null)
    await setMyUsername('nadia_k2', 'correct horse')
    expect(sent(0)).toMatchObject({ method: 'PUT', path: '/v1/me/username', search: '' })
    expect(sent(0).body).toEqual({ username: 'nadia_k' })
    expect(sent(1).body).toEqual({ username: 'nadia_k2', password: 'correct horse' })
  })

  it('requestContactCode sends a password only for a replacement', async () => {
    await requestContactCode({ phone: '01711234567' })
    await requestContactCode({ email: 'new@example.com' }, 'correct horse')
    expect(sent(0)).toMatchObject({ method: 'POST', path: '/v1/me/contact', search: '' })
    expect(sent(0).body).toEqual({ phone: '01711234567' })
    expect(sent(1).body).toEqual({ email: 'new@example.com', password: 'correct horse' })
  })

  it('removeContact posts the kind and the password, with no query string', async () => {
    await removeContact('email', 'correct horse')
    expect(sent()).toMatchObject({
      method: 'POST',
      path: '/v1/me/contact/remove',
      search: '',
      body: { kind: 'email', password: 'correct horse' },
    })
  })

  it('lookupAlreadyAdded keeps U2’s query shape, for a phone and now an email', async () => {
    await lookupAlreadyAdded({ phone: '01711234567' })
    await lookupAlreadyAdded({ email: 'rina@example.com' })
    expect(sent(0)).toMatchObject({ method: 'GET', path: '/v1/accounts/already-added' })
    expect(new URLSearchParams(sent(0).search).get('phone')).toBe('01711234567')
    expect(new URLSearchParams(sent(1).search).get('email')).toBe('rina@example.com')
    expect(new URLSearchParams(sent(1).search).has('phone')).toBe(false)
  })

  it('inviteMember sends email and/or phone in the body', async () => {
    await inviteMember({ display_name: 'Rina', role: 'teacher', email: 'rina@example.com' })
    expect(sent()).toMatchObject({ method: 'POST', path: '/v1/centre/members', search: '' })
    expect(sent().body).toEqual({
      display_name: 'Rina',
      role: 'teacher',
      email: 'rina@example.com',
    })
  })

  it('a refusal comes back as an ApiError carrying its key', async () => {
    mockFetch(() =>
      json(409, {
        error: { code: 'CONFLICT', message_key: 'account.username.unavailable', retryable: false },
      }),
    )
    await expect(setMyUsername('nadia_k', null)).rejects.toMatchObject({
      status: 409,
      messageKey: 'account.username.unavailable',
    })
    await expect(removeContact('phone', 'x')).rejects.toBeInstanceOf(ApiError)
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

// The server records which app an account uses from these two headers at
// sign-in and renewal; sending them on every call keeps that simple.
describe('client platform headers', () => {
  const header = (init: RequestInit, name: string) => (init.headers as Record<string, string>)[name]

  it('sends the platform and version on every request, signed in or not', async () => {
    mockFetch(() => json(200, {}))
    await request('POST', '/v1/auth/verify', { anonymous: true, body: {} })
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    await request('GET', '/v1/me')
    for (const call of calls) {
      expect(header(call.init, 'X-Client-Platform')).toBe('web')
      expect(header(call.init, 'X-Client-Version')).toBe(__APP_VERSION__)
    }
    expect(__APP_VERSION__).toMatch(/^[0-9A-Za-z.+-]{1,32}$/)
  })

  it('sends them on a token renewal too', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 1 })
    mockFetch((url) =>
      url.endsWith('/v1/auth/refresh')
        ? json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
        : json(200, {}),
    )
    await request('GET', '/v1/me')
    const refresh = calls.find((c) => c.url.endsWith('/v1/auth/refresh'))!
    expect(header(refresh.init, 'X-Client-Platform')).toBe('web')
    expect(header(refresh.init, 'X-Client-Version')).toBe(__APP_VERSION__)
  })

  it('keeps the version inside the charset and length the server accepts', () => {
    expect(clientVersion('0.1.0')).toBe('0.1.0')
    expect(clientVersion('1.2.3-beta+exp.sha.5114f85')).toBe('1.2.3-beta+exp.sha.5114f85')
    expect(clientVersion('1.0 (build 7)/x')).toBe('1.0build7x')
    expect(clientVersion('9'.repeat(40))).toHaveLength(32)
    expect(clientVersion('///')).toBe('0')
  })
})

describe('requestText', () => {
  it('reads the hub preview as text, signed in, renewing on a 401', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    let previews = 0
    mockFetch((url) => {
      if (url.endsWith('/v1/auth/refresh'))
        return json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
      previews += 1
      if (previews === 1)
        return json(401, { error: { code: 'X', message_key: 'x', retryable: false } })
      return new Response('<!doctype html><p>page</p>', { status: 200 })
    })

    await expect(readHubPreview('bn')).resolves.toBe('<!doctype html><p>page</p>')
    const reads = calls.filter((c) => c.url.includes('/v1/hub/listing/preview'))
    expect(reads.map((c) => c.url)).toEqual([
      '/v1/hub/listing/preview?locale=bn',
      '/v1/hub/listing/preview?locale=bn',
    ])
    expect(auth(reads[0]!.init)).toBe('Bearer A1')
    expect(auth(reads[1]!.init)).toBe('Bearer A2')
    expect((reads[1]!.init.headers as Record<string, string>).Accept).toBe('text/html')
  })

  it('throws the server refusal as an ApiError, never returning its body', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    mockFetch(() =>
      json(403, { error: { code: 'FORBIDDEN', message_key: 'error.forbidden', retryable: false } }),
    )
    const failure = requestText('GET', '/v1/hub/listing/preview').catch((e: unknown) => e)
    const error = await failure
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).messageKey).toBe('error.forbidden')
  })
})
