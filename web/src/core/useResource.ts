/**
 * Load one thing from the server, with the four states every screen in
 * the design draws: loading, loaded, empty (the screen's own call) and
 * failed — and "failed while showing what was already loaded", which is
 * the design's "offline with saved copy" state for as long as the tab is
 * open. Nothing is persisted: see vite.config.ts on why API data never
 * reaches browser storage.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, UNEXPECTED_KEY } from '../api/errors'

export type Resource<T> =
  | { state: 'loading' }
  | { state: 'loaded'; data: T; refreshing: boolean; error: ApiError | null; loadedAt: Date }
  | { state: 'failed'; error: ApiError }

export interface UseResource<T> {
  resource: Resource<T>
  reload: () => void
}

export interface ResourceOptions {
  /**
   * Keep showing the previous key's data, marked `refreshing`, while the
   * new key loads. Only for lists whose rows stay valid across keys (a
   * search as it narrows); never for a screen that acts on what it shows,
   * where last month's lines under this month's heading are a wrong-month
   * payment waiting to happen.
   */
  keepPreviousOnKeyChange?: boolean
}

/**
 * How long a successful read counts as current. Returning to the tab
 * re-reads only once it is older than this, so an alt-tab does not
 * re-issue every mounted read.
 */
export const STALE_AFTER_MS = 30_000

function asApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError(0, 'UNEXPECTED', UNEXPECTED_KEY, true)
}

function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError'
}

function sameDeps(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((v, i) => Object.is(v, b[i]))
}

/**
 * @param load Fetches and maps; a mapping failure (a money value that is
 *   not a string, say) surfaces as `error.unexpected`, loudly. It receives
 *   a signal that aborts when the screen unmounts, the key changes or a
 *   newer read replaces this one; pass it to the request.
 * @param deps Reload when these change. A change of key drops what was
 *   shown and starts from loading (see {@link ResourceOptions}).
 */
export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  options: ResourceOptions = {},
): UseResource<T> {
  const [resource, setResource] = useState<Resource<T>>({ state: 'loading' })
  const [nonce, setNonce] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load
  const keepRef = useRef(options.keepPreviousOnKeyChange ?? false)
  keepRef.current = options.keepPreviousOnKeyChange ?? false
  const lastDeps = useRef<readonly unknown[] | null>(null)
  // What the focus and online listeners need, without re-subscribing.
  const status = useRef<{ inFlight: boolean; loadedAt: number | null; failed: boolean }>({
    inFlight: false,
    loadedAt: null,
    failed: false,
  })

  useEffect(() => {
    const keyChanged = lastDeps.current !== null && !sameDeps(lastDeps.current, deps)
    lastDeps.current = deps
    const controller = new AbortController()
    status.current.inFlight = true
    setResource((r) =>
      r.state === 'loaded' && (!keyChanged || keepRef.current)
        ? { ...r, refreshing: true }
        : { state: 'loading' },
    )
    if (keyChanged) status.current.loadedAt = null
    loadRef.current(controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return
        status.current = { inFlight: false, loadedAt: Date.now(), failed: false }
        setResource({
          state: 'loaded',
          data,
          refreshing: false,
          error: null,
          loadedAt: new Date(),
        })
      },
      (e: unknown) => {
        if (controller.signal.aborted || isAbort(e)) return
        if (!(e instanceof ApiError)) console.error(e)
        status.current = { ...status.current, inFlight: false, failed: true }
        const error = asApiError(e)
        setResource((r) =>
          r.state === 'loaded' ? { ...r, refreshing: false, error } : { state: 'failed', error },
        )
      },
    )
    return () => {
      controller.abort()
      status.current.inFlight = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps])

  // Coming back online re-reads; so does coming back to the tab once what
  // is shown is out of date: a teacher who left the window open overnight
  // should not approve against yesterday. A read still on its way is left.
  useEffect(() => {
    const again = () => {
      if (!status.current.inFlight) setNonce((n) => n + 1)
    }
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      const s = status.current
      const fresh = s.loadedAt !== null && Date.now() - s.loadedAt < STALE_AFTER_MS
      if (fresh && !s.failed) return
      again()
    }
    window.addEventListener('online', again)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('online', again)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { resource, reload }
}

/**
 * The value, once it has stopped changing for `ms`: a search box asks the
 * server once per pause rather than once per keystroke.
 */
export function useDebounced<T>(value: T, ms = 300): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms)
    return () => window.clearTimeout(timer)
  }, [value, ms])
  return settled
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}
