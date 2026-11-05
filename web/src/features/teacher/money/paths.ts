/**
 * Money-area paths not (yet) in the shared `teacher/paths.ts`.
 *
 * `seatFees` and `seatProgress` take the student's and batch's names as
 * query parameters because neither seat response carries them (Android
 * passes them as route arguments for the same reason). Both are optional:
 * a link from elsewhere that has only the id still opens the screen.
 */
import { paths } from '../paths'

function withNames(base: string, name?: string, batch?: string): string {
  const q = new URLSearchParams()
  if (name) q.set('name', name)
  if (batch) q.set('batch', batch)
  const s = q.toString()
  return s ? `${base}?${s}` : base
}

export const moneyPaths = {
  seatFees: (enrollmentId: string, name?: string, batch?: string) =>
    withNames(paths.seatFees(enrollmentId), name, batch),
  seatProgress: (enrollmentId: string, name?: string, batch?: string) =>
    withNames(`/seats/${encodeURIComponent(enrollmentId)}/progress`, name, batch),
}
