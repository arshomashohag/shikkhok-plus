/**
 * The inbox's unread count, for a badge in the shell.
 *
 * One small store shared by every subscriber, so a badge and the inbox
 * screen agree: opening an item or "Mark all read" calls
 * {@link inboxChanged} and every badge re-reads. The count is the
 * server's `unread`, never a client tally. Nothing is stored: a reload
 * starts from null and asks again.
 */
import { useEffect, useSyncExternalStore } from 'react'
import { readInbox } from './api'

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
    count = (await readInbox()).unread
  } catch {
    // Keep the last known count: a badge is not worth an error.
  } finally {
    inFlight = false
    emit()
  }
}

/** Something changed the inbox (an item read, all read): re-read. */
export function inboxChanged(): void {
  void refresh()
}

/** Record the count a screen just read, without a second request. */
export function setUnreadCount(value: number): void {
  count = value
  emit()
}

/** For tests and sign-out: forget the cached count. */
export function resetUnreadCount(): void {
  count = null
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * The unread count, or null before the first answer. Re-reads when the
 * tab becomes visible again or the connection returns.
 */
export function useUnreadCount(): number | null {
  const value = useSyncExternalStore(subscribe, () => count)
  useEffect(() => {
    void refresh()
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    window.addEventListener('online', inboxChanged)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('online', inboxChanged)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])
  return value
}
