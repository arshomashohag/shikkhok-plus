/**
 * The centre teacher's two decisions the client may make itself: which
 * marks to send, and how many days to show. Whether a class may still be
 * written, and whether it is still theirs, is the server's.
 */
import type { Schemas } from '../../api/endpoints'

export type Roster = Schemas['ClassRosterResponse']

/** Every seat's mark to send: unmarked seats default to present. */
export function marksFrom(
  roster: Roster,
  absent: ReadonlySet<string>,
): Schemas['AttendanceSubmitRequest']['seats'] {
  return roster.seats.map((seat) => ({
    enrollment_id: seat.enrollment_id,
    present: !absent.has(seat.enrollment_id),
  }))
}

/** The seats already recorded absent, as the starting selection. */
export function absentFrom(roster: Roster): Set<string> {
  return new Set(roster.seats.filter((s) => s.present === false).map((s) => s.enrollment_id))
}
