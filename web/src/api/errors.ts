/**
 * The client side of the server's error taxonomy.
 *
 * Every error response is `{ error: { code, message_key, retryable } }`.
 * **Retryability is the server's to say** — the client is told, never
 * infers — and the text shown is the string the `message_key` names,
 * never anything the server wrote in English.
 */

/** The message key for "could not reach the server". */
export const OFFLINE_KEY = 'error.network.unreachable'

/** The message key for anything the client cannot classify. */
export const UNEXPECTED_KEY = 'error.unexpected'

export class ApiError extends Error {
  override name = 'ApiError'

  constructor(
    /** HTTP status; 0 when the request never reached the server. */
    readonly status: number,
    /** The server's stable machine code, e.g. `CONFLICT`. */
    readonly code: string,
    /** Names the string to show. */
    readonly messageKey: string,
    /** Whether trying again can help — as the server said. */
    readonly retryable: boolean,
    /** Typed per code; rendered, never interpreted. */
    readonly details: Record<string, string> | null = null,
  ) {
    super(`${status} ${code} ${messageKey}`)
  }

  /** True when the request never reached the server. */
  get offline(): boolean {
    return this.status === 0
  }
}

/** The failure for a request that never got an answer. */
export function networkError(): ApiError {
  return new ApiError(0, 'NETWORK', OFFLINE_KEY, true)
}

/**
 * Turn a non-2xx response into an {@link ApiError}.
 *
 * A body that is not the envelope — a proxy's HTML 502, say — becomes
 * `error.unexpected`, retryable only for a 5xx.
 */
export async function errorFrom(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json()
    const error = (body as { error?: Record<string, unknown> } | null)?.error
    if (
      error &&
      typeof error.code === 'string' &&
      typeof error.message_key === 'string' &&
      typeof error.retryable === 'boolean'
    ) {
      return new ApiError(
        response.status,
        error.code,
        error.message_key,
        error.retryable,
        (error.details as Record<string, string> | null | undefined) ?? null,
      )
    }
  } catch {
    // Fall through: not JSON.
  }
  return new ApiError(response.status, 'UNEXPECTED', UNEXPECTED_KEY, response.status >= 500)
}
