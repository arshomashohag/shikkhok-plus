/**
 * Where the session's tokens live, and how they are renewed.
 *
 * **Storage.** Both tokens sit in `localStorage` under one key. That is
 * readable by any script running on this origin, which is why the page
 * ships a strict Content-Security-Policy with no inline or third-party
 * script, and why the app adds no third-party SDK. Moving the refresh
 * token into an `HttpOnly` cookie needs a backend change (the refresh
 * route reads it from the body today) and is recorded as follow-up work
 * in web/README.md rather than half-done here.
 *
 * **Renewal is serialised across tabs.** The server rotates refresh
 * tokens and treats a rotated-out token presented again as theft: the
 * whole token family is revoked [team: token lifecycle]. Two tabs that
 * each notice an expired access token and each refresh with the same
 * refresh token would therefore sign the person out everywhere. So a
 * renewal runs under a Web Lock shared by every tab of this origin, and
 * inside the lock it re-reads storage first: if another tab has already
 * rotated, this tab adopts the new pair instead of spending the old one.
 */
import { ApiError, errorFrom, networkError } from './errors'
import { CLIENT_HEADERS } from './platform'

const STORAGE_KEY = 'sp.session'
const LOCK_NAME = 'sp.session.refresh'

/** Renew this long before the access token's stated expiry. */
const EARLY_RENEWAL_MS = 30_000

export interface StoredTokens {
  access: string
  refresh: string
  /** Epoch ms after which the access token should not be sent. */
  accessExpiresAt: number
}

/** The server's token response. */
export interface TokenResponse {
  access_token: string
  refresh_token: string
  expires_in: number
}

type Listener = (tokens: StoredTokens | null) => void
const listeners = new Set<Listener>()

function safeStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function readTokens(): StoredTokens | null {
  const raw = safeStorage()?.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<StoredTokens>
    if (
      typeof parsed.access === 'string' &&
      typeof parsed.refresh === 'string' &&
      typeof parsed.accessExpiresAt === 'number'
    ) {
      return parsed as StoredTokens
    }
  } catch {
    // Corrupt entry: treat as signed out.
  }
  return null
}

function notify(tokens: StoredTokens | null): void {
  for (const l of listeners) l(tokens)
}

/** Store a fresh pair from the server. */
export function saveTokens(response: TokenResponse, now = Date.now()): StoredTokens {
  const tokens: StoredTokens = {
    access: response.access_token,
    refresh: response.refresh_token,
    accessExpiresAt: now + response.expires_in * 1000,
  }
  safeStorage()?.setItem(STORAGE_KEY, JSON.stringify(tokens))
  notify(tokens)
  return tokens
}

/** Forget the session, in this tab and (through `storage`) in every other. */
export function clearTokens(): void {
  safeStorage()?.removeItem(STORAGE_KEY)
  notify(null)
}

/** Subscribe to sign-in / rotation / sign-out, including other tabs'. */
export function onTokensChanged(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === STORAGE_KEY) notify(readTokens())
  })
}

export function isFresh(tokens: StoredTokens, now = Date.now()): boolean {
  return tokens.accessExpiresAt - EARLY_RENEWAL_MS > now
}

/** Run `fn` holding the cross-tab renewal lock, where the browser has one. */
async function withLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = (navigator as Navigator & { locks?: LockManager }).locks
  if (!locks) return fn()
  return locks.request(LOCK_NAME, fn)
}

let inFlight: Promise<StoredTokens> | null = null

/**
 * Renew the access token.
 *
 * @param base The API origin
 * @param spent The refresh token the caller saw; if storage now holds a
 *   different one, another tab has rotated and that pair is adopted
 * @throws ApiError 401 when the session is over; the tokens are cleared
 */
export function renew(base: string, spent: string): Promise<StoredTokens> {
  if (!inFlight) {
    inFlight = withLock(async () => {
      const current = readTokens()
      if (!current) throw new ApiError(401, 'UNAUTHENTICATED', 'auth.token.not_valid', false)
      if (current.refresh !== spent && isFresh(current)) return current

      let response: Response
      try {
        response = await fetch(`${base}/v1/auth/refresh`, {
          method: 'POST',
          headers: {
            ...CLIENT_HEADERS,
            'Content-Type': 'application/json',
            // Required present by the route; the server reads the body.
            Authorization: `Bearer ${current.access}`,
          },
          body: JSON.stringify({ refresh_token: current.refresh }),
        })
      } catch {
        throw networkError()
      }
      if (!response.ok) {
        const error = await errorFrom(response)
        if (response.status === 401 || response.status === 403) clearTokens()
        throw error
      }
      return saveTokens((await response.json()) as TokenResponse)
    }).finally(() => {
      inFlight = null
    })
  }
  return inFlight
}
