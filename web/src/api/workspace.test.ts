/** The workspace header: a remembered choice among what the server offers. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from './client'
import { clearTokens, saveTokens } from './tokens'
import { currentWorkspace, reconcileWorkspace, storeWorkspace, WORKSPACE_HEADER } from './workspace'

const headersOf = (mock: ReturnType<typeof vi.fn>) =>
  (mock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

describe('the workspace header', () => {
  it('is sent with the token once a workspace is chosen', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 900 })
    storeWorkspace('centre-1')
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await request('GET', '/v1/batches')
    expect(headersOf(fetchMock)[WORKSPACE_HEADER]).toBe('centre-1')
  })

  it('is left off with nothing chosen, and on an anonymous call', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    storeWorkspace('centre-1')
    await request('POST', '/v1/auth/otp', { anonymous: true, body: {} })
    expect(headersOf(fetchMock)[WORKSPACE_HEADER]).toBeUndefined()
  })
})

describe('reconcileWorkspace', () => {
  const offered = [{ owner_id: 'solo' }, { owner_id: 'centre-1' }]

  it('keeps a choice the server still offers', () => {
    storeWorkspace('centre-1')
    expect(reconcileWorkspace(offered)).toBe('centre-1')
  })

  it('forgets a choice the server no longer offers, falling back to the first', () => {
    storeWorkspace('revoked-centre')
    expect(reconcileWorkspace(offered)).toBe('solo')
    expect(currentWorkspace()).toBeNull()
  })

  it('is null when there is no workspace at all', () => {
    expect(reconcileWorkspace([])).toBeNull()
  })
})
