/**
 * The admin app's one place for HTTP.
 *
 * Every call goes to the origin the admin app was loaded from, so a
 * token never leaves the admin host and no CORS is involved; the page's
 * CSP allows nothing else (`vite.admin.config.ts`). Signed-in calls carry
 * the admin bearer token. **A 401 ends the session**: there is no
 * refresh token to renew with, so the administrator is taken back to
 * sign-in, and the screen they were on is where they land afterwards.
 *
 * Failures are the same {@link ApiError} the main app uses, parsed from
 * the same envelope, so a screen switches on `messageKey` and
 * `retryable`, never on a status.
 */
import { ApiError, errorFrom, networkError, UNEXPECTED_KEY } from '../api/errors'
import { endAdminSession, readAdminSession } from './session'

type Method = 'GET' | 'POST' | 'PUT'

export interface AdminRequestOptions {
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
  /** For the three sign-in routes, which take no token. */
  anonymous?: boolean
  signal?: AbortSignal
}

/** What a call without a usable token fails with, before it is sent. */
export function signedOutError(): ApiError {
  return new ApiError(401, 'NOT_AUTHENTICATED', 'auth.token.not_valid', false)
}

function urlFor(path: string, query?: AdminRequestOptions['query']): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined) params.set(k, String(v))
  }
  const qs = params.toString()
  return `${path}${qs ? `?${qs}` : ''}`
}

/**
 * Make one admin API call and decode its JSON body.
 *
 * @throws ApiError For every failure, including no connection (status 0)
 */
export async function adminRequest<T>(
  method: Method,
  path: string,
  options: AdminRequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (!options.anonymous) {
    const session = readAdminSession()
    if (!session) throw signedOutError()
    headers.Authorization = `Bearer ${session.access}`
  }

  let response: Response
  try {
    response = await fetch(urlFor(path, options.query), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
      credentials: 'omit',
      cache: 'no-store',
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw networkError()
  }

  if (!response.ok) {
    const error = await errorFrom(response)
    if (response.status === 401 && !options.anonymous) endAdminSession('expired')
    throw error
  }
  if (response.status === 204) return undefined as T
  const text = await response.text()
  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    throw new ApiError(response.status, 'UNEXPECTED', UNEXPECTED_KEY, false)
  }
}
