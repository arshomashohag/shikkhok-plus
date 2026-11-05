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

function asApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError(0, 'UNEXPECTED', UNEXPECTED_KEY, true)
}

/**
 * @param load Fetches and maps; a mapping failure (a money value that is
 *   not a string, say) surfaces as `error.unexpected`, loudly
 * @param deps Reload when these change
 */
export function useResource<T>(load: () => Promise<T>, deps: readonly unknown[]): UseResource<T> {
  const [resource, setResource] = useState<Resource<T>>({ state: 'loading' })
  const [nonce, setNonce] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    let live = true
    setResource((r) => (r.state === 'loaded' ? { ...r, refreshing: true } : { state: 'loading' }))
    loadRef.current().then(
      (data) => {
        if (live)
          setResource({
            state: 'loaded',
            data,
            refreshing: false,
            error: null,
            loadedAt: new Date(),
          })
      },
      (e: unknown) => {
        if (!live) return
        if (!(e instanceof ApiError)) console.error(e)
        const error = asApiError(e)
        setResource((r) =>
          r.state === 'loaded' ? { ...r, refreshing: false, error } : { state: 'failed', error },
        )
      },
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps])

  // Coming back online, or back to the tab, re-reads: a teacher who left
  // the window open overnight should not approve against yesterday.
  useEffect(() => {
    const again = () => setNonce((n) => n + 1)
    const onVisible = () => {
      if (document.visibilityState === 'visible') again()
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
