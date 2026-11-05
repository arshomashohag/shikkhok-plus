/**
 * Family read responses → what the seat screens draw. Pure, and the test
 * target, as `StudentStateMapper.kt` and `MarksStateMapper.kt` are on
 * Android.
 *
 * **Nothing here computes a figure.** Ranks, averages, the highest mark,
 * the run of results and its direction all come from the server; the
 * client joins two responses by exam id and chooses which words to show.
 * A suppressed marksheet stays suppressed: no partial comparison is built
 * from what was withheld.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'
import type { FeeChipModel } from '../../../ui/components'
import { studentFeeChip } from '../../student/mappers'
import { parseYearMonth, type YearMonth } from '../../teacher/classes/mappers'

// ------------------------------------------------------------------ seat

/** Who and what the seat is, from the reader's own seat list. */
export interface SeatIdentity {
  batchName: string
  teacherName: string | null
  /** The child's name for a guardian; null for a student's own seat. */
  childName: string | null
}

export function identityFromMine(
  rows: Schemas['StudentBatchResponse'][],
  seat: string,
): SeatIdentity | null {
  const row = rows.find((r) => r.enrollment_id === seat)
  return row
    ? { batchName: row.batch_name, teacherName: row.teacher_display_name ?? null, childName: null }
    : null
}

export function identityFromChildren(
  rows: Schemas['GuardianChildResponse'][],
  seat: string,
): SeatIdentity | null {
  const row = rows.find((r) => r.enrollment_id === seat)
  return row
    ? {
        batchName: row.batch_name,
        teacherName: row.teacher_display_name ?? null,
        childName: row.display_name,
      }
    : null
}

// -------------------------------------------------------------- teaching

export interface NextClass {
  date: string
  startTime: string
  endTime: string | null
  moved: boolean
  startsInMinutes: number | null
  subjectName: string | null
}

export interface FeeLine {
  period: string
  charged: Money | null
  dueDate: string
  paidOn: string | null
  chip: FeeChipModel
  /** The server's status says something is owed and nothing is being checked. */
  payable: boolean
}

export interface FamilyExam {
  examId: string
  title: string
  subjectName: string
  date: string
  totalMarks: number
  topics: string[]
  done: boolean
}

export interface Notice {
  id: string
  body: string
  postedAt: string
  edited: boolean
}

export interface SeatView {
  subjects: string[]
  teacherName: string | null
  next: NextClass | null
  following: NextClass[]
  fee: FeeLine | null
  doneExams: FamilyExam[]
  upcomingExams: FamilyExam[]
  notices: Notice[]
}

function nextClass(dto: Schemas['UpcomingSessionResponse']): NextClass {
  return {
    date: dto.date,
    startTime: dto.start_time,
    endTime: dto.end_time ?? null,
    moved: dto.moved,
    startsInMinutes: dto.starts_in_minutes ?? null,
    subjectName: dto.subject_name ?? null,
  }
}

/** Statuses the server reports for a month that still has something owed. */
const PAYABLE_STATUSES: readonly string[] = ['unpaid', 'partly_paid']

export function mapFee(dto: Schemas['CurrentFeeResponse']): FeeLine {
  return {
    period: dto.period,
    charged: Money.fromWireOrNull(dto.charged),
    dueDate: dto.due_date,
    paidOn: dto.paid_on ?? null,
    chip: studentFeeChip(dto),
    payable: !dto.verifying && PAYABLE_STATUSES.includes(dto.status),
  }
}

export function mapExam(dto: Schemas['FamilyExamResponse']): FamilyExam {
  return {
    examId: dto.exam_id,
    title: dto.title,
    subjectName: dto.subject_name,
    date: dto.date,
    totalMarks: dto.total_marks,
    topics: (dto.topics as string[]).map(String),
    done: dto.state === 'done',
  }
}

/** The server's order is kept throughout: it already sorts what it sends. */
export function mapTeaching(dto: Schemas['FamilyBatchViewResponse']): SeatView {
  const exams = (dto.exams ?? []).map(mapExam)
  return {
    subjects: (dto.teacher?.subjects as string[] | undefined)?.map(String) ?? [],
    teacherName: dto.teacher?.display_name ?? null,
    next: dto.next_session ? nextClass(dto.next_session) : null,
    following: (dto.following_sessions ?? []).map(nextClass),
    fee: dto.current_fee ? mapFee(dto.current_fee) : null,
    doneExams: exams.filter((e) => e.done),
    upcomingExams: exams.filter((e) => !e.done),
    notices: dto.announcements.map((a) => ({
      id: a.announcement_id,
      body: a.body,
      postedAt: a.created_at,
      edited: a.edited,
    })),
  }
}

// -------------------------------------------------------------- progress

export type ResultState = 'marked' | 'absent' | 'not_entered' | 'joined_after'

/** `MarksStateMapper.RESULT_STATE_KEYS`, to string resources. */
export const RESULT_STATE_LABEL: Record<ResultState, string> = {
  marked: 'mark_state_marked',
  absent: 'mark_state_absent',
  not_entered: 'mark_state_not_entered',
  joined_after: 'mark_state_joined_after',
}

export interface ProgressRow {
  examId: string
  title: string
  subjectName: string | null
  date: string
  totalMarks: number
  state: ResultState
  /** Null whenever the state is not `marked`: an absence is never a zero. */
  marks: number | null
  rank: number | null
  rankedOutOf: number | null
  batchAverage: number | null
}

export function mapProgress(rows: Schemas['ProgressEntryResponse'][]): ProgressRow[] {
  return rows.map((r) => ({
    examId: r.exam_id,
    title: r.title,
    subjectName: r.subject_name ?? null,
    date: r.date,
    totalMarks: r.total_marks,
    state: r.result_state,
    marks: r.result_state === 'marked' ? (r.marks ?? null) : null,
    rank: r.rank ?? null,
    rankedOutOf: r.ranked_out_of ?? null,
    batchAverage: r.batch_average ?? null,
  }))
}

/** One result per exam id, for the Exams tab's join. */
export function resultsByExam(rows: ProgressRow[]): Map<string, ProgressRow> {
  return new Map(rows.map((r) => [r.examId, r]))
}

export interface ProgressSummary {
  direction: 'up' | 'down' | 'same'
  run: number
  firstMarks: number
  lastMarks: number
  totalMarks: number
  aboveAverage: boolean | null
}

export function mapSummary(dto: Schemas['ProgressSummaryResponse'] | null): ProgressSummary | null {
  return dto
    ? {
        direction: dto.direction,
        run: dto.run,
        firstMarks: dto.first_marks,
        lastMarks: dto.last_marks,
        totalMarks: dto.total_marks,
        aboveAverage: dto.above_average ?? null,
      }
    : null
}

// ------------------------------------------------------------- marksheet

export type Marksheet =
  | {
      published: true
      examTitle: string
      totalMarks: number
      ownState: ResultState
      ownMarks: number | null
      rank: number | null
      markedCount: number
      average: number
      highest: number
      bands: { low: number; high: number; count: number }[]
    }
  | {
      published: false
      examTitle: string
      totalMarks: number
      ownState: ResultState
      ownMarks: number | null
      reason: 'marking_incomplete' | 'too_few_results'
    }

export function mapMarksheet(
  dto: Schemas['PublishedMarksheetResponse'] | Schemas['SuppressedMarksheetResponse'],
): Marksheet {
  const ownMarks = dto.viewer_result_state === 'marked' ? (dto.viewer_marks ?? null) : null
  if ('reason' in dto) {
    return {
      published: false,
      examTitle: dto.exam_title,
      totalMarks: dto.total_marks,
      ownState: dto.viewer_result_state,
      ownMarks,
      reason: dto.reason,
    }
  }
  return {
    published: true,
    examTitle: dto.exam_title,
    totalMarks: dto.total_marks,
    ownState: dto.viewer_result_state,
    ownMarks,
    rank: dto.viewer_rank ?? null,
    markedCount: dto.marked_count,
    average: dto.average,
    highest: dto.highest,
    bands: dto.bands.map((b) => ({ low: b.low, high: b.high, count: b.count })),
  }
}

/** The class average as Android prints it: one decimal place. */
export function formatAverage(value: number): string {
  return value.toFixed(1)
}

// --------------------------------------------------------------- classes

export type ClassMark = 'present' | 'absent' | 'not_marked' | 'not_enrolled'
export type ClassState = 'taken' | 'today' | 'upcoming' | 'not_recorded' | 'cancelled'

export const MARK_LABEL: Record<ClassMark, string> = {
  present: 'family_present',
  absent: 'family_absent',
  not_marked: 'family_not_marked',
  not_enrolled: 'family_not_enrolled_then',
}

export const STATE_LABEL: Record<ClassState, string> = {
  taken: 'calendar_state_taken',
  today: 'calendar_state_today',
  upcoming: 'calendar_state_upcoming',
  not_recorded: 'calendar_state_not_recorded',
  cancelled: 'calendar_state_cancelled',
}

export interface FamilyClass {
  sessionId: string
  date: string
  startTime: string
  endTime: string | null
  subjectName: string | null
  state: ClassState
  topic: string | null
  notes: string | null
  mark: ClassMark
}

export interface FamilyMonth extends YearMonth {
  first: YearMonth
  last: YearMonth
  today: string
  /** Newest first, as the design's "Topics covered" list reads. */
  classes: FamilyClass[]
}

const STATES: readonly ClassState[] = ['taken', 'today', 'upcoming', 'not_recorded', 'cancelled']
const MARKS: readonly ClassMark[] = ['present', 'absent', 'not_marked', 'not_enrolled']

export function mapFamilyMonth(dto: Schemas['MonthViewResponse']): FamilyMonth {
  const shown = { year: dto.year, month: dto.month }
  const classes: FamilyClass[] = []
  for (const day of dto.days) {
    for (const c of day.classes) {
      const state = c.state as ClassState
      if (!STATES.includes(state)) continue
      classes.push({
        sessionId: c.session_id,
        date: c.date,
        startTime: c.start_time,
        endTime: c.end_time ?? null,
        subjectName: c.subject_name ?? null,
        state,
        topic: c.topic?.trim() ? c.topic : null,
        notes: c.notes?.trim() ? c.notes : null,
        mark: MARKS.includes(c.mark as ClassMark) ? (c.mark as ClassMark) : 'not_marked',
      })
    }
  }
  classes.sort((a, b) => `${b.date}T${b.startTime}`.localeCompare(`${a.date}T${a.startTime}`))
  return {
    ...shown,
    first: parseYearMonth(dto.first_month) ?? shown,
    last: parseYearMonth(dto.last_month) ?? shown,
    today: dto.today,
    classes,
  }
}

/** `{2026, 11}` → `2026-11`, for the `?month=` a class link carries. */
export function monthKey({ year, month }: YearMonth): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

/** Bangladesh's month today, for a class link that carries none. */
export function dhakaMonth(now = new Date()): YearMonth {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Dhaka',
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(now)
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value)
  return { year: get('year'), month: get('month') }
}
