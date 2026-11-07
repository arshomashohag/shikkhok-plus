/**
 * The administrator's session: one access token and when it lapses.
 *
 * **Memory first, `sessionStorage` second, never `localStorage`.** The
 * copy in `sessionStorage` lets a reload keep the administrator signed
 * in; it belongs to this one tab and is gone when the tab closes, so a
 * forgotten window on a shared computer does not stay signed in for the
 * next person. There is no refresh token: the server issues an admin
 * token for an hour and the administrator signs in again after that.
 *
 * Nothing else is stored. Recovery codes, the authenticator secret and
 * every API response stay in memory only.
 */

/** The one `sessionStorage` key this app owns. */
export const SESSION_KEY = 'sp.admin.session'

/**
 * Treat the token as lapsed this long before the server would, so a
 * request does not set off with a token that expires on the way.
 */
export const EXPIRY_MARGIN_MS = 15_000

export interface AdminSession {
  /** The bearer token from `/v1/admin/auth/mfa`. */
  access: string
  /** When it lapses, in epoch milliseconds (already less the margin). */
  expiresAt: number
}

/** Why the session ended, for the sign-in screen to say. */
export type EndReason = 'expired' | 'signed-out'

type Listener = () => void

let current: AdminSession | null = null
let loaded = false
let endReason: EndReason | null = null
const listeners = new Set<Listener>()

function notify(): void {
  for (const listener of listeners) listener()
}

function store(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    // Storage blocked: the session lasts as long as this page.
    return null
  }
}

function parse(raw: string | null): AdminSession | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as Partial<AdminSession>
    if (typeof value.access === 'string' && value.access && typeof value.expiresAt === 'number')
      return { access: value.access, expiresAt: value.expiresAt }
  } catch {
    // Not ours, or damaged: treat as signed out.
  }
  return null
}

/**
 * The session as held, lapsed or not, without changing anything: the
 * snapshot React reads. The same object until the session changes.
 */
export function peekAdminSession(): AdminSession | null {
  if (!loaded) {
    loaded = true
    current = parse(store()?.getItem(SESSION_KEY) ?? null)
  }
  return current
}

/**
 * The session, or null when there is none or it has lapsed. A lapsed
 * session is cleared on the way, and the sign-in screen is told why.
 *
 * @param now The moment to judge expiry against, for tests
 */
export function readAdminSession(now: number = Date.now()): AdminSession | null {
  peekAdminSession()
  if (current && now >= current.expiresAt) {
    endAdminSession('expired')
    return null
  }
  return current
}

/**
 * Keep the token the sign-in returned.
 *
 * @param response The `AdminSessionResponse` fields that matter here
 * @param now When it was received, for tests
 * @return The session as stored
 */
export function saveAdminSession(
  response: { access_token: string; expires_in: number },
  now: number = Date.now(),
): AdminSession {
  const session = {
    access: response.access_token,
    expiresAt: now + response.expires_in * 1000 - EXPIRY_MARGIN_MS,
  }
  current = session
  loaded = true
  endReason = null
  try {
    store()?.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {
    // Quota or blocked storage: memory still holds it for this page.
  }
  notify()
  return session
}

/**
 * Forget the token, in memory and in this tab's storage.
 *
 * @param reason Why, so the sign-in screen can say so
 */
export function endAdminSession(reason: EndReason): void {
  const had = current !== null
  current = null
  loaded = true
  endReason = reason
  try {
    store()?.removeItem(SESSION_KEY)
  } catch {
    // Nothing stored, then.
  }
  if (had || reason === 'signed-out') notify()
}

/** Why the last session ended, until the next sign-in. */
export function lastEndReason(): EndReason | null {
  return endReason
}

/** Be told when the session starts or ends. */
export function subscribeAdminSession(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** For tests: forget everything, as a fresh page load would. */
export function resetAdminSessionForTests(): void {
  current = null
  loaded = false
  endReason = null
}
