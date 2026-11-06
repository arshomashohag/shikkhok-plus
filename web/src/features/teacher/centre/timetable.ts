/**
 * The timetable's own decisions: which week, grouping by day, the people
 * and rooms a manager may pick, and how a clash is worded. Every rule about
 * what may be assigned is the server's; these only shape what it sent.
 */
import type { Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'

export type TimetableClass = Schemas['TimetableClassResponse']

/** `YYYY-MM-DD` for a local date. */
export function isoDay(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** A `YYYY-MM-DD` date, plus some days, as a local date. */
function dayPlus(iso: string, days: number): Date {
  const [y = '1970', m = '1', d = '1'] = iso.split('-')
  return new Date(Number(y), Number(m) - 1, Number(d) + days)
}

/** The seven days starting at `start`, as `YYYY-MM-DD`. */
export function weekFrom(start: string): string[] {
  return Array.from({ length: 7 }, (_, i) => isoDay(dayPlus(start, i)))
}

/** Move a week start by whole weeks. */
export function shiftWeek(start: string, weeks: number): string {
  return isoDay(dayPlus(start, 7 * weeks))
}

/** The classes grouped by day, every day of the week present. */
export function byDay(days: string[], classes: TimetableClass[]): [string, TimetableClass[]][] {
  return days.map((day) => [day, classes.filter((c) => c.date === day)])
}

/** The members a class may be given: live, and not having declined. */
export function assignable(members: Schemas['MemberResponse'][]): Schemas['MemberResponse'][] {
  return members.filter((m) => !m.revoked && m.decision !== 'declined')
}

/** The rooms a class may be given: those still in use. */
export function liveRooms(rooms: Schemas['RoomResponse'][]): Schemas['RoomResponse'][] {
  return rooms.filter((r) => !r.archived)
}

/** The other classes on the same day a class could swap teachers with. */
export function swapCandidates(target: TimetableClass, all: TimetableClass[]): TimetableClass[] {
  return all.filter(
    (c) => c.session_id !== target.session_id && c.date === target.date && c.status !== 'cancelled',
  )
}

/** The clash's batch and time, when the server named them. */
export function clashOf(error: unknown): { batch: string; time: string } | null {
  if (!(error instanceof ApiError) || error.code !== 'CLASS_CLASH') return null
  const batch = error.details?.batch
  const time = error.details?.start_time
  return batch && time ? { batch, time } : null
}
