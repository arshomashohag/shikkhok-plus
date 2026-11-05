/**
 * Exam responses → what the exam screens draw. Pure, and the test target
 * (the web counterpart of MarksStateMapper.kt).
 *
 * Marks are JSON numbers, not money. Every decision is the server's: an
 * exam's state, whether it is writable, which seats joined after it, and
 * whether it may be published. Nothing here averages or ranks.
 */
import type { Schemas } from '../../../api/endpoints'
import { toLatinDigits } from '../../../core/money'

export type ExamState = 'needs_marks' | 'upcoming' | 'complete'

export interface ExamItem {
  examId: string
  title: string
  subjectName: string
  date: string
  totalMarks: number
  enteredCount: number
  expectedCount: number
  state: ExamState
  published: boolean
  /** Called off by the teacher; kept on the list, flagged, and never written again. */
  cancelled: boolean
  cancellationReason: string | null
  topics: string[]
}

export function mapExam(dto: Schemas['ExamListItemResponse']): ExamItem {
  return {
    examId: dto.exam_id,
    title: dto.title,
    subjectName: dto.subject_name,
    date: dto.date,
    totalMarks: dto.total_marks,
    enteredCount: dto.entered_count,
    expectedCount: dto.expected_count,
    state: dto.state,
    published: dto.published ?? false,
    // A server from before cancelling existed sends no flag: not cancelled.
    cancelled: dto.cancelled ?? false,
    cancellationReason: dto.cancellation_reason ?? null,
    topics: (dto.topics ?? []).map(String),
  }
}

/**
 * Whether "Cancel exam" is offered: an exam still on whose results are
 * not out. The server refuses a published one (`marks.exam.published`)
 * and answers a second cancel with the exam as it is, so this only
 * decides whether to show the button.
 */
export function canCancel(exam: Pick<ExamItem, 'cancelled' | 'published'>): boolean {
  return !exam.cancelled && !exam.published
}

/**
 * The tab's groups, as ExamsTab.kt: needs marks, coming up, marked (newest
 * first), then cancelled. A cancelled exam leaves the three working groups
 * whatever its marking state, so it never asks for marks.
 */
export function groupExams(exams: ExamItem[]): { titleKey: string; exams: ExamItem[] }[] {
  const on = exams.filter((e) => !e.cancelled)
  return [
    { titleKey: 'batch_exams_needs_marks', exams: on.filter((e) => e.state === 'needs_marks') },
    { titleKey: 'batch_exams_coming', exams: on.filter((e) => e.state === 'upcoming') },
    {
      titleKey: 'batch_exams_done',
      exams: on.filter((e) => e.state === 'complete').reverse(),
    },
    { titleKey: 'exam_cancelled_chip', exams: exams.filter((e) => e.cancelled) },
  ].filter((g) => g.exams.length > 0)
}

export type ResultState = 'marked' | 'absent' | 'not_entered' | 'joined_after'

/** The string for each state the server may report. */
export const STATE_KEYS: Record<ResultState, string> = {
  marked: 'mark_state_marked',
  absent: 'mark_state_absent',
  not_entered: 'mark_state_not_entered',
  joined_after: 'mark_state_joined_after',
}

export class UnknownResultState extends Error {
  override name = 'UnknownResultState'
}

function knownState(raw: string): ResultState {
  if (raw in STATE_KEYS) return raw as ResultState
  // As MarksStateMapper: a state this client cannot name fails the screen
  // rather than rendering a guess.
  throw new UnknownResultState(raw)
}

export interface ResultRow {
  enrollmentId: string
  displayName: string
  state: ResultState
  marks: number | null
  /** The server said the exam is writable, and this seat sat it. */
  editable: boolean
  /** Something was recorded, so there is a history to show. */
  hasHistory: boolean
}

export interface ExamResults {
  exam: ExamItem
  rows: ResultRow[]
  writable: boolean
  /** Seats still without a mark or Absent, from the server's own counts. */
  toEnter: number
}

export function mapResults(dto: Schemas['ExamResultsResponse']): ExamResults {
  const exam = mapExam(dto.exam)
  return {
    exam,
    writable: dto.writable,
    toEnter: Math.max(0, exam.expectedCount - exam.enteredCount),
    rows: dto.results.map((r) => {
      const state = knownState(r.result_state)
      return {
        enrollmentId: r.enrollment_id,
        displayName: r.display_name,
        state,
        marks: r.marks ?? null,
        editable: dto.writable && state !== 'joined_after',
        hasHistory: state === 'marked' || state === 'absent',
      }
    }),
  }
}

/** Entered / markable, as the counter in the bar ("6/20"). */
export function progressOf(rows: ResultRow[]): { done: number; of: number } {
  const markable = rows.filter((r) => r.editable)
  return { done: markable.filter((r) => r.state !== 'not_entered').length, of: markable.length }
}

export interface HistoryEntry {
  state: ResultState
  marks: number | null
  recordedAt: string
  superseded: boolean
}

export function mapHistory(rows: Schemas['CorrectionEntryResponse'][]): HistoryEntry[] {
  return rows.map((r) => ({
    state: knownState(r.result_state),
    marks: r.marks ?? null,
    recordedAt: r.recorded_at,
    superseded: r.superseded,
  }))
}

const MAX_DIGITS = 3
const MAX_DECIMALS = 2

/**
 * Keep a typed mark to the shape the keypad allows (typedNext in
 * MarkEntryScreen.kt): digits, one point, at most three whole digits and
 * two decimals. Bangla digits are read as Latin. Format only: whether the
 * number is within the exam's total is the server's answer.
 */
export function cleanTyped(raw: string): string {
  let out = ''
  for (const ch of toLatinDigits(raw)) {
    const point = out.indexOf('.')
    if (ch === '.') {
      if (point < 0) out = (out || '0') + '.'
    } else if (/[0-9]/.test(ch)) {
      if (point >= 0 ? out.length - point - 1 < MAX_DECIMALS : out.length < MAX_DIGITS) out += ch
    }
  }
  return out
}

/** The number a cleaned entry stands for, or null when nothing is typed. */
export function typedMark(typed: string): number | null {
  const trimmed = typed.replace(/\.$/, '')
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

/** "04", the roll the design prints beside each name. */
export function rollLabel(index: number): string {
  return String(index + 1).padStart(2, '0')
}

const MAX_TOPICS = 20
const MAX_TOPIC_LENGTH = 120

/** One topic per line, blank lines dropped (topicsOf in ExamCreateForm.kt). */
export function topicsOf(text: string): string[] {
  return text
    .split('\n')
    .map((t) => t.trim())
    .filter(Boolean)
}

export function topicsValid(topics: string[]): boolean {
  return topics.length <= MAX_TOPICS && topics.every((t) => t.length <= MAX_TOPIC_LENGTH)
}
