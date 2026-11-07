/** The read hook every screen draws from: keys, staleness and aborts. */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STALE_AFTER_MS, useDebounced, useResource } from './useResource'

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

function showTab() {
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

afterEach(() => {
  vi.useRealTimers()
})

describe('useResource', () => {
  it('drops the previous key’s data and starts from loading when the key changes', async () => {
    const load = vi.fn((key: string) => Promise.resolve(`lines of ${key}`))
    const { result, rerender } = renderHook(({ k }) => useResource(() => load(k), [k]), {
      initialProps: { k: '2026-10' },
    })
    await waitFor(() => expect(result.current.resource.state).toBe('loaded'))
    rerender({ k: '2026-09' })
    // Never October's lines under September's heading.
    expect(result.current.resource.state).toBe('loading')
    await waitFor(() =>
      expect(result.current.resource).toMatchObject({ state: 'loaded', data: 'lines of 2026-09' }),
    )
  })

  it('keeps the previous data, marked refreshing, on a reload of the same key', async () => {
    const next = deferred<string>()
    const load = vi.fn().mockResolvedValueOnce('first').mockReturnValueOnce(next.promise)
    const { result } = renderHook(() => useResource(() => load(), []))
    await waitFor(() => expect(result.current.resource.state).toBe('loaded'))
    act(() => result.current.reload())
    expect(result.current.resource).toMatchObject({ data: 'first', refreshing: true })
    await act(async () => next.resolve('second'))
    expect(result.current.resource).toMatchObject({ data: 'second', refreshing: false })
  })

  it('may keep the previous key’s data when asked, for a narrowing search', async () => {
    const next = deferred<string>()
    const load = vi.fn().mockResolvedValueOnce('all').mockReturnValueOnce(next.promise)
    const { result, rerender } = renderHook(
      ({ q }) => useResource(() => load(q), [q], { keepPreviousOnKeyChange: true }),
      { initialProps: { q: '' } },
    )
    await waitFor(() => expect(result.current.resource.state).toBe('loaded'))
    rerender({ q: 'ra' })
    expect(result.current.resource).toMatchObject({ data: 'all', refreshing: true })
  })

  it('aborts the read in flight when the key changes and ignores its answer', async () => {
    const signals: AbortSignal[] = []
    const first = deferred<string>()
    const load = vi.fn((signal: AbortSignal, key: string) => {
      signals.push(signal)
      return key === 'a' ? first.promise : Promise.resolve('b data')
    })
    const { result, rerender } = renderHook(
      ({ k }) => useResource((signal) => load(signal, k), [k]),
      { initialProps: { k: 'a' } },
    )
    rerender({ k: 'b' })
    expect(signals[0]?.aborted).toBe(true)
    await waitFor(() => expect(result.current.resource).toMatchObject({ data: 'b data' }))
    await act(async () => first.resolve('a data, late'))
    expect(result.current.resource).toMatchObject({ data: 'b data' })
  })

  it('aborts the read in flight on unmount', () => {
    let seen: AbortSignal | null = null
    const { unmount } = renderHook(() =>
      useResource((signal) => {
        seen = signal
        return new Promise<string>(() => {})
      }, []),
    )
    unmount()
    expect((seen as AbortSignal | null)?.aborted).toBe(true)
  })

  it('does not re-read on returning to the tab while the data is recent, and does once stale', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const load = vi.fn().mockResolvedValue('x')
    renderHook(() => useResource(() => load(), []))
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1))
    await act(async () => {
      await Promise.resolve()
    })
    act(() => showTab())
    expect(load).toHaveBeenCalledTimes(1)
    act(() => {
      vi.advanceTimersByTime(STALE_AFTER_MS + 1)
    })
    act(() => showTab())
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  })

  it('re-reads on coming back online', async () => {
    const load = vi.fn().mockResolvedValue('x')
    renderHook(() => useResource(() => load(), []))
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1))
    await act(async () => {
      await Promise.resolve()
    })
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  })
})

describe('useDebounced', () => {
  it('settles on the last value once it stops changing', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 300), {
      initialProps: { v: '' },
    })
    rerender({ v: 'r' })
    rerender({ v: 'ra' })
    act(() => {
      vi.advanceTimersByTime(299)
    })
    expect(result.current).toBe('')
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe('ra')
  })
})
