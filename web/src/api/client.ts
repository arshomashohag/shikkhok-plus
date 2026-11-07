/**
 * The one place this client talks HTTP.
 *
 * Every request carries the access token when there is one, renews it
 * first when it is about to lapse, and renews-and-repeats once on a 401 —
 * the web counterpart of `SessionRenewal.kt`. Every request, renewal
 * included, says which app it comes from (`platform.ts`). Failures come
 * back as {@link ApiError}, so a screen switches on `messageKey` and
 * `retryable` and never on an HTTP status.
 */
import { ApiError, errorFrom, networkError } from './errors'
import { CLIENT_HEADERS } from './platform'
import { isFresh, readTokens, renew } from './tokens'
import { currentWorkspace, WORKSPACE_HEADER } from './workspace'

/** Empty for same-origin; otherwise the https origin of the API. */
export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
  /** For the unauthenticated auth routes. */
  anonymous?: boolean
  signal?: AbortSignal
}

function urlFor(path: string, query?: RequestOptions['query']): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined) params.set(k, String(v))
  }
  const qs = params.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

async function send(
  method: Method,
  path: string,
  options: RequestOptions,
  token: string | null,
): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json', ...CLIENT_HEADERS }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) {
    headers.Authorization = `Bearer ${token}`
    const workspace = currentWorkspace()
    if (workspace) headers[WORKSPACE_HEADER] = workspace
  }
  try {
    return await fetch(urlFor(path, options.query), {
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
}

/**
 * Make one API call and decode its JSON body.
 *
 * @throws ApiError For every failure, including no connection (status 0)
 */
export async function request<T>(
  method: Method,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let tokens = options.anonymous ? null : readTokens()
  if (tokens && !isFresh(tokens)) tokens = await renew(API_BASE, tokens.refresh)

  let response = await send(method, path, options, tokens?.access ?? null)
  if (response.status === 401 && tokens) {
    tokens = await renew(API_BASE, tokens.refresh)
    response = await send(method, path, options, tokens.access)
  }
  if (!response.ok) throw await errorFrom(response)
  if (response.status === 204) return undefined as T
  const text = await response.text()
  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    throw new ApiError(response.status, 'UNEXPECTED', 'error.unexpected', false)
  }
}
