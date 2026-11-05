/**
 * Whether the window is desktop-wide: the width at which the bottom bar
 * becomes the side rail (`app.css`, 900px). A screen that lays out
 * differently there -- a table instead of a list, its main action in the
 * page header instead of a floating button -- renders one form or the
 * other rather than both, so nothing is duplicated for a screen reader.
 *
 * False where `matchMedia` does not exist (tests, very old browsers):
 * the phone layout is the one that works everywhere.
 */
import { useSyncExternalStore } from 'react'

export const WIDE_QUERY = '(min-width: 900px)'

function query(): MediaQueryList | null {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(WIDE_QUERY)
    : null
}

function subscribe(onChange: () => void): () => void {
  const mql = query()
  if (!mql) return () => {}
  mql.addEventListener('change', onChange)
  return () => mql.removeEventListener('change', onChange)
}

export function useWide(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => query()?.matches ?? false,
    () => false,
  )
}
