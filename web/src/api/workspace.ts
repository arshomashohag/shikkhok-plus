/**
 * Which workspace teacher requests act on: a tutor's own batches, or a
 * coaching centre they manage.
 *
 * **A choice, never a grant** [TC-11]. The server resolves every workspace
 * the account manages from its own data and refuses a header naming any
 * other; this module only remembers which of the offered ones was picked,
 * so the client sends `X-Workspace-Id` on every request. With nothing
 * stored the header is left off and the server uses the first workspace,
 * which is what every client sent before centres existed.
 */
const KEY = 'sp.workspace'

export const WORKSPACE_HEADER = 'X-Workspace-Id'

/** The stored workspace id, or null. */
export function currentWorkspace(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

/** Remember a workspace, or forget it with null. */
export function storeWorkspace(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(KEY, id)
    else window.localStorage.removeItem(KEY)
  } catch {
    // Storage blocked: requests go without the header and use the default.
  }
}

/**
 * Keep the stored choice only while the server still offers it, so a
 * revoked centre falls back to the default instead of failing every call.
 *
 * @return The workspace in effect, or null for the server's default
 */
export function reconcileWorkspace(offered: readonly { owner_id: string }[]): string | null {
  const stored = currentWorkspace()
  if (stored && offered.some((w) => w.owner_id === stored)) return stored
  storeWorkspace(null)
  return offered[0]?.owner_id ?? null
}
