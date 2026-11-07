/**
 * The admin session for React: re-renders when it starts or ends, and
 * ends it by itself the moment the token lapses, so an idle tab goes
 * back to sign-in rather than failing its next request.
 */
import { useEffect, useSyncExternalStore } from 'react'
import {
  endAdminSession,
  peekAdminSession,
  subscribeAdminSession,
  type AdminSession,
} from './session'

export function useAdminSession(): AdminSession | null {
  const session = useSyncExternalStore(subscribeAdminSession, peekAdminSession)

  useEffect(() => {
    if (!session) return
    const timer = window.setTimeout(
      () => endAdminSession('expired'),
      Math.max(0, session.expiresAt - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [session])

  return session && session.expiresAt > Date.now() ? session : null
}

/**
 * "14:32" in Dhaka time, as every time in the product is, with Western
 * digits in both languages.
 */
export function formatUntil(epochMs: number, lang: 'en' | 'bn'): string {
  return new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    timeZone: 'Asia/Dhaka',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(epochMs))
}
