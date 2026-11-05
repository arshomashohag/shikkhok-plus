/**
 * Server responses → what the classes screens draw. Pure, and the test
 * target, like the Android `CalendarMapper` and `ClassTapRouter`.
 *
 * Every state here is the server's: a day is "taken" or "upcoming"
 * because the calendar said so, and a class opens for recording or
 * planning because the server set `recordable` or `plannable`. The only
 * arithmetic is calendar layout (which weekday the 1st falls on).
 */
import type { Schemas } from '../../../api/endpoints'

export type ClassState = 'taken' | 'today' | 'upcoming' | 'not_recorded' | 'cancelled'

export interface ClassItem {
  sessionId: string
  date: string
  startTime: string
  endTime: string | null
  subjectName: string | null
  state: ClassState
  topic: string | null
  notes: string | null
  plannable: boolean
  recordable: boolean
  topicVersion: number
  attendanceVersion: number
}

export interface CalendarDay {
  date: string
  state: ClassState
  classes: ClassItem[]
}

export interface YearMonth {
  year: number
  month: number
}

export interface MonthModel extends YearMonth {
  first: YearMonth
  last: YearMonth
  today: string
  days: Map<string, CalendarDay>
}

const STATES: readonly ClassState[] = ['taken', 'today', 'upcoming', 'not_recorded', 'cancelled']

function state(raw: string): ClassState | null {
  return STATES.includes(raw as ClassState) ? (raw as ClassState) : null
}

export function mapClass(dto: Schemas['CalendarClassResponse']): ClassItem | null {
  const s = state(dto.state)
  if (!s) return null
  return {
    sessionId: dto.session_id,
    date: dto.date,
    startTime: dto.start_time,
    endTime: dto.end_time ?? null,
    subjectName: dto.subject_name ?? null,
    state: s,
    topic: dto.topic ?? null,
    notes: dto.notes ?? null,
    plannable: dto.plannable,
    recordable: dto.recordable,
    topicVersion: dto.topic_version,
    attendanceVersion: dto.attendance_version,
  }
}

/** `2026-11` → `{ year: 2026, month: 11 }`; null when malformed. */
export function parseYearMonth(raw: string): YearMonth | null {
  const m = /^(\d{4})-(\d{2})$/.exec(raw)
  return m ? { year: Number(m[1]), month: Number(m[2]) } : null
}

export function mapMonth(dto: Schemas['MonthViewResponse']): MonthModel {
  const shown = { year: dto.year, month: dto.month }
  const days = new Map<string, CalendarDay>()
  for (const d of dto.days) {
    const s = state(d.state)
    if (!s) continue
    days.set(d.date, {
      date: d.date,
      state: s,
      classes: d.classes.map(mapClass).filter((c): c is ClassItem => c !== null),
    })
  }
  return {
    ...shown,
    first: parseYearMonth(dto.first_month) ?? shown,
    last: parseYearMonth(dto.last_month) ?? shown,
    today: dto.today,
    days,
  }
}

/** Which screen a class opens — `ClassTapRouter.forClass`. */
export type ClassTarget = 'record' | 'plan' | 'read'

export function classTarget(c: Pick<ClassItem, 'recordable' | 'plannable'>): ClassTarget {
  if (c.recordable) return 'record'
  if (c.plannable) return 'plan'
  return 'read'
}

export function compareMonths(a: YearMonth, b: YearMonth): number {
  return a.year * 12 + a.month - (b.year * 12 + b.month)
}

export function shiftMonth(ym: YearMonth, delta: number): YearMonth {
  const index = ym.year * 12 + (ym.month - 1) + delta
  return { year: Math.floor(index / 12), month: (index % 12) + 1 }
}

/**
 * The month as weeks of day numbers, Sunday first as the Android calendar
 * draws it, with null for the blanks before the 1st and after the last.
 */
export function monthGrid({ year, month }: YearMonth): (number | null)[][] {
  const leading = new Date(Date.UTC(year, month - 1, 1)).getUTCDay()
  const length = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const cells: (number | null)[] = [
    ...Array<null>(leading).fill(null),
    ...Array.from({ length }, (_, i) => i + 1),
  ]
  while (cells.length % 7 !== 0) cells.push(null)
  const weeks: (number | null)[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

export function isoDay({ year, month }: YearMonth, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/** `2026-11-05` → `{ year: 2026, month: 11 }`. */
export function monthOf(isoDate: string): YearMonth {
  return { year: Number(isoDate.slice(0, 4)), month: Number(isoDate.slice(5, 7)) }
}

/**
 * The "Continue: …" suggestion: the topic of the most recent other class
 * that has one, as `RecordClassViewModel.open` picks it. A convenience the
 * teacher may ignore, not a decision.
 */
export function lastTopic(
  sessions: Schemas['SessionResponse'][],
  excludeSessionId: string,
): string | null {
  let best: { key: string; topic: string } | null = null
  for (const s of sessions) {
    const topic = s.topic?.trim()
    if (s.session_id === excludeSessionId || !s.topic_logged || !topic) continue
    const key = `${s.date}T${s.start_time}`
    if (!best || key > best.key) best = { key, topic }
  }
  return best?.topic ?? null
}

export interface Seat {
  enrollmentId: string
  displayName: string
  present: boolean
}

/** A seat nobody marked yet starts present, as on Android. */
export function mapSeats(dto: Schemas['SessionRosterResponse']): Seat[] {
  return dto.seats.map((s) => ({
    enrollmentId: s.enrollment_id,
    displayName: s.display_name,
    present: s.present ?? true,
  }))
}

/**
 * The record as the server now holds it, from an attendance conflict's
 * `details.current_state` ("<enrollment>:present,<enrollment>:absent").
 */
export function parseConflictState(raw: string | undefined): Map<string, boolean> {
  const out = new Map<string, boolean>()
  for (const part of (raw ?? '').split(',')) {
    const [id, mark] = part.split(':')
    if (id && (mark === 'present' || mark === 'absent')) out.set(id, mark === 'present')
  }
  return out
}

/** One time range for every class day, read from the first slot, as `ScheduleEditor`. */
export interface ScheduleDraft {
  days: number[]
  start: string
  end: string
}

export function draftFromSlots(
  slots: Schemas['ScheduleSlotWire'][],
  fallback = { start: '16:00', end: '17:30' },
): ScheduleDraft {
  const first = slots[0]
  return {
    days: [...new Set(slots.map((s) => s.weekday))],
    start: first ? first.start_time.slice(0, 5) : fallback.start,
    end: first ? first.end_time.slice(0, 5) : fallback.end,
  }
}

export function slotsFromDraft(draft: ScheduleDraft): Schemas['ScheduleSlotWire'][] {
  return [...draft.days]
    .sort((a, b) => a - b)
    .map((weekday) => ({ weekday, start_time: draft.start, end_time: draft.end }))
}
