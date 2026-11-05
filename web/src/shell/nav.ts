/**
 * The tabs each lens sees — the same sets `ShikkhokNavHost.kt` builds,
 * so a person who uses both clients finds things in the same place.
 */
import type { Lens } from '../session/session'

export interface Tab {
  to: string
  label: string
  icon: 'home' | 'layers' | 'wallet' | 'users' | 'mail' | 'more' | 'verify'
  /**
   * Only in the desktop side rail. A wide window has room for a direct
   * entry the phone's five-slot bar does not, as the web boards draw it;
   * the screen itself is the same one Today's "See all" opens.
   */
  desktopOnly?: boolean
}

export function tabsFor(lens: Lens | null): Tab[] {
  const more: Tab = { to: '/more', label: 'nav_more', icon: 'more' }
  switch (lens) {
    case 'teacher':
      return [
        { to: '/today', label: 'nav_today', icon: 'home' },
        { to: '/batches', label: 'nav_batches', icon: 'layers' },
        { to: '/students', label: 'nav_students', icon: 'users' },
        { to: '/dues', label: 'nav_dues', icon: 'wallet' },
        { to: '/verify', label: 'web_nav_verify', icon: 'verify', desktopOnly: true },
        more,
      ]
    case 'student':
      return [{ to: '/my-batches', label: 'nav_my_batches', icon: 'layers' }, more]
    case 'guardian':
      return [{ to: '/children', label: 'nav_children', icon: 'users' }, more]
    case null:
      return [{ to: '/invitations', label: 'nav_invitations', icon: 'mail' }, more]
  }
}

/** Where a lens lands after sign-in. Teachers start on Batches, as on Android. */
export function homeFor(lens: Lens | null): string {
  switch (lens) {
    case 'teacher':
      return '/batches'
    case 'student':
      return '/my-batches'
    case 'guardian':
      return '/children'
    case null:
      return '/invitations'
  }
}
