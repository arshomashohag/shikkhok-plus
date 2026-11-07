import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/errors'
import { json } from '../test/render'
import { adminRequest } from './client'
import {
  lastEndReason,
  peekAdminSession,
  resetAdminSessionForTests,
  saveAdminSession,
  SESSION_KEY,
} from './session'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  resetAdminSessionForTests()
  sessionStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  resetAdminSessionForTests()
  sessionStorage.clear()
})

function answer(response: Response) {
  fetchMock = vi.fn(async () => response)
  vi.stubGlobal('fetch', fetchMock)
}

const sentHeaders = () =>
  (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>

describe('adminRequest', () => {
  it('sends the admin bearer to the same origin, without cookies or caching', async () => {
    saveAdminSession({ access_token: 'ADMIN', expires_in: 3600 })
    answer(json(200, { ok: true }))
    await expect(adminRequest('GET', '/v1/admin/overview')).resolves.toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/v1/admin/overview')
    expect(sentHeaders().Authorization).toBe('Bearer ADMIN')
    expect(init.credentials).toBe('omit')
    expect(init.cache).toBe('no-store')
  })

  it('sends no token on the sign-in routes', async () => {
    saveAdminSession({ access_token: 'ADMIN', expires_in: 3600 })
    answer(json(200, {}))
    await adminRequest('POST', '/v1/admin/auth/otp', { body: { phone: '01711' }, anonymous: true })
    expect(sentHeaders().Authorization).toBeUndefined()
  })

  it('ends the session on a 401, so the app returns to log-in', async () => {
    saveAdminSession({ access_token: 'ADMIN', expires_in: 3600 })
    answer(
      json(401, {
        error: { code: 'NOT_AUTHENTICATED', message_key: 'auth.token.not_valid', retryable: false },
      }),
    )
    const error = await adminRequest('GET', '/v1/admin/teachers').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).messageKey).toBe('auth.token.not_valid')
    expect(peekAdminSession()).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
    expect(lastEndReason()).toBe('expired')
  })

  it('keeps the session on a 403: the screen says why', async () => {
    saveAdminSession({ access_token: 'ADMIN', expires_in: 3600 })
    answer(
      json(403, {
        error: { code: 'FORBIDDEN', message_key: 'authz.lens.not_available', retryable: false },
      }),
    )
    await expect(adminRequest('GET', '/v1/admin/overview')).rejects.toMatchObject({ status: 403 })
    expect(peekAdminSession()).not.toBeNull()
  })

  it('does not send a request at all without a session', async () => {
    answer(json(200, {}))
    await expect(adminRequest('GET', '/v1/admin/overview')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('turns no connection into the offline error', async () => {
    saveAdminSession({ access_token: 'ADMIN', expires_in: 3600 })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    await expect(adminRequest('GET', '/v1/admin/overview')).rejects.toMatchObject({ status: 0 })
  })
})
