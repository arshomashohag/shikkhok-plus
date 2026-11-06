/** Whether the teacher screens are acting on a coaching centre right now. */
import { useOptionalSession } from './session'

/**
 * True when the teacher lens is open on a centre workspace. Read without
 * throwing, so a screen rendered outside a ready session (as in its unit
 * tests) simply shows the solo layout.
 */
export function useInCentre(): boolean {
  const session = useOptionalSession()
  if (!session) return false
  const workspaces = session.me.workspaces ?? []
  const current = workspaces.find((w) => w.owner_id === session.workspace) ?? workspaces[0]
  return session.lens === 'teacher' && current?.kind === 'centre'
}
