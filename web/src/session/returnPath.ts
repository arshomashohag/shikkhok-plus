/**
 * Where a signed-out visitor was going, kept across sign-in.
 *
 * A hub page's "Report this page" link opens `/hub-report?…` on this app,
 * and its "Ask to join" link opens `/hub-enquiry?…` [H5]; the reader is
 * often signed out. The signed-out routes remember the
 * address here and send them to sign-in; the first landing after any way
 * in (password, code, sign-up, two-step) takes them on to it.
 *
 * **`sessionStorage`, not route state**: sign-in moves between
 * `/signin`, `/signin/code` and `/signup` by links that deliberately carry
 * no route state (`SignIn.tsx`), and a tab reload mid-sign-in should not
 * lose the destination either. Nothing typed is kept: only the address,
 * which came from the link. Storage that throws (blocked, private mode)
 * means the reader lands home instead, which is where they landed before.
 */

const KEY = 'sp.return'

/** The public links that may be returned to: exactly these paths, with any query. */
const RETURNABLE: readonly string[] = ['/hub-report', '/hub-enquiry']

/**
 * Only a report or join-request address on this app: the exact path, or
 * the exact path and a query. Never `//other.host`, a sign-in page, or a
 * path that merely starts the same (`/hub-enquiries`, `/hub-enquiryx`).
 */
function safe(path: unknown): string | null {
  if (typeof path !== 'string') return null
  return RETURNABLE.some((p) => path === p || path.startsWith(`${p}?`)) ? path : null
}

/** Remember where to go after sign-in; anything but a returnable address is ignored. */
export function rememberReturn(path: string): void {
  if (!safe(path)) return
  try {
    window.sessionStorage.setItem(KEY, path)
  } catch {
    // Storage blocked: the reader lands home after sign-in.
  }
}

/** The remembered address, if any, without forgetting it. */
export function peekReturn(): string | null {
  try {
    return safe(window.sessionStorage.getItem(KEY))
  } catch {
    return null
  }
}

/** Forget the remembered address once it has been used. */
export function forgetReturn(): void {
  try {
    window.sessionStorage.removeItem(KEY)
  } catch {
    // Nothing was stored.
  }
}
