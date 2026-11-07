import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  EXPIRY_MARGIN_MS,
  SESSION_KEY,
  endAdminSession,
  lastEndReason,
  peekAdminSession,
  readAdminSession,
  resetAdminSessionForTests,
  saveAdminSession,
  subscribeAdminSession,
} from './session'

const T0 = Date.UTC(2026, 10, 7, 8, 0, 0)

beforeEach(() => {
  resetAdminSessionForTests()
  sessionStorage.clear()
  localStorage.clear()
})
afterEach(() => {
  resetAdminSessionForTests()
  sessionStorage.clear()
  localStorage.clear()
})

describe('admin session storage', () => {
  it('keeps the token in memory and sessionStorage only, never localStorage', () => {
    const saved = saveAdminSession({ access_token: 'tok', expires_in: 3600 }, T0)
    expect(saved).toEqual({ access: 'tok', expiresAt: T0 + 3600_000 - EXPIRY_MARGIN_MS })
    expect(readAdminSession(T0)).toEqual(saved)
    expect(JSON.parse(sessionStorage.getItem(SESSION_KEY)!)).toEqual(saved)
    expect(localStorage.length).toBe(0)
  })

  it('survives a reload of the tab, from sessionStorage', () => {
    saveAdminSession({ access_token: 'tok', expires_in: 3600 }, T0)
    resetAdminSessionForTests() // a fresh page: memory is empty
    expect(readAdminSession(T0 + 60_000)?.access).toBe('tok')
  })

  it('treats the token as lapsed a little before the server does, and clears it', () => {
    saveAdminSession({ access_token: 'tok', expires_in: 3600 }, T0)
    expect(readAdminSession(T0 + 3600_000 - EXPIRY_MARGIN_MS - 1)).not.toBeNull()
    expect(readAdminSession(T0 + 3600_000 - EXPIRY_MARGIN_MS)).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
    expect(peekAdminSession()).toBeNull()
    expect(lastEndReason()).toBe('expired')
  })

  it('forgets a lapsed token found in storage after a reload', () => {
    saveAdminSession({ access_token: 'tok', expires_in: 60 }, T0)
    resetAdminSessionForTests()
    expect(readAdminSession(T0 + 3600_000)).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  })

  it('logs out: memory and storage both cleared, and listeners told', () => {
    let told = 0
    const stop = subscribeAdminSession(() => told++)
    saveAdminSession({ access_token: 'tok', expires_in: 3600 }, T0)
    endAdminSession('signed-out')
    stop()
    expect(told).toBe(2)
    expect(readAdminSession(T0)).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
    expect(lastEndReason()).toBe('signed-out')
  })

  it('ignores a damaged or foreign value', () => {
    sessionStorage.setItem(SESSION_KEY, '{"access":42}')
    expect(readAdminSession(T0)).toBeNull()
    resetAdminSessionForTests()
    sessionStorage.setItem(SESSION_KEY, 'not json')
    expect(readAdminSession(T0)).toBeNull()
  })

  it('a new log-in clears the reason the last session ended', () => {
    endAdminSession('expired')
    saveAdminSession({ access_token: 'tok', expires_in: 3600 }, T0)
    expect(lastEndReason()).toBeNull()
  })
})
