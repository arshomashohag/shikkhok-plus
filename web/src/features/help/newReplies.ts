/**
 * How many help-centre questions carry a reply not yet seen, for the
 * badge on More's Help centre row.
 *
 * The same shape as the inbox's unread count (`account/area/unread.ts`):
 * one small store, the server's `new_replies` and never a client tally,
 * re-read when the tab becomes visible or the connection returns, and
 * nothing stored. It is read only where the row is drawn, so no screen
 * but More pays for it.
 */
import { useEffect, useSyncExternalStore } from 'react'
import { listTickets } from './api'

let count: number | null = null
let inFlight = false
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

async function refresh() {
  if (inFlight) return
  inFlight = true
  try {
    count = (await listTickets()).new_replies
  } catch {
    // Keep the last known count: a badge is not worth an error.
  } finally {
    inFlight = false
    emit()
  }
}

/** A ticket was opened or answered: re-read. */
export function helpChanged(): void {
  void refresh()
}

/** Record the count a screen just read, without a second request. */
export function setNewReplies(value: number): void {
  count = value
  emit()
}

/** For tests and sign-out: forget the cached count. */
export function resetNewReplies(): void {
  count = null
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The count, or null before the first answer. */
export function useNewReplies(): number | null {
  const value = useSyncExternalStore(subscribe, () => count)
  useEffect(() => {
    void refresh()
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    window.addEventListener('online', helpChanged)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('online', helpChanged)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])
  return value
}
