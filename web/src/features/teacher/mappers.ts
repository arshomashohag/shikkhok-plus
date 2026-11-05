/**
 * Server responses → what the teacher screens draw.
 *
 * **Every function here is a pure mapping and the test target**, the web
 * counterpart of the Android `*StateMapper` objects. They convert money
 * strings to {@link Money} (failing loudly on anything else) and choose
 * which chip a row wears from the state the server reported. None of them
 * adds, subtracts or compares an amount: the server sent every figure
 * and every decision [TC-9] [D-31].
 */
import type { Schemas } from '../../api/endpoints'
import { Money } from '../../core/money'
import type { FeeChipModel } from '../../ui/components'

// ------------------------------------------------------------------ Today

export interface TodayClass {
  sessionId: string
  batchId: string
  batchName: string
  subjectName: string | null
  startTime: string
  status: 'cancelled' | 'held' | 'scheduled'
  isNext: boolean
  startsInMinutes: number | null
  topic: string | null
  topicLogged: boolean
  examTitle: string | null
}

export interface ReviewChild {
  claimId: string
  enrollmentId: string
  displayName: string
  period: string
  owed: Money
}

export interface PaymentReview {
  submissionId: string
  batchName: string
  submittedBy: string | null
  submitterPhone: string | null
  submittedAt: string
  paidOn: string
  totalAmount: Money
  owedTogether: Money
  difference: Money
  comparison: 'matches' | 'over' | 'short'
  transactionId: string | null
  fromAccount: string | null
  channelLabel: string | null
  payerNote: string | null
  children: ReviewChild[]
  duplicateOf: {
    displayName: string
    amount: Money
    status: 'approved' | 'pending' | 'rejected'
    decidedAt: string | null
  } | null
}

export interface TodayModel {
  date: string
  hasBatches: boolean
  outstanding: { total: Money; overdue: Money; overdueStudents: number; batchCount: number }
  classes: TodayClass[]
  toVerify: PaymentReview[]
  toVerifyCount: number
}

export function mapToday(dto: Schemas['TodayResponse']): TodayModel {
  return {
    date: dto.date,
    hasBatches: dto.has_batches,
    outstanding: {
      total: Money.fromWire(dto.outstanding.total),
      overdue: Money.fromWire(dto.outstanding.overdue),
      overdueStudents: dto.outstanding.overdue_students,
      batchCount: dto.outstanding.batch_count,
    },
    classes: dto.classes.map((c) => ({
      sessionId: c.session_id,
      batchId: c.batch_id,
      batchName: c.batch_name,
      subjectName: c.subject_name ?? null,
      startTime: c.start_time,
      status: c.status,
      isNext: c.is_next,
      startsInMinutes: c.starts_in_minutes ?? null,
      topic: c.topic ?? null,
      topicLogged: c.topic_logged,
      examTitle: c.exam_title ?? null,
    })),
    toVerify: dto.to_verify.map(mapReview),
    toVerifyCount: dto.to_verify_count,
  }
}

/** The channel a payment came through, as the payer would name it. */
export function channelLabel(method: Schemas['PaymentDestinationResponse']): string | null {
  return method.provider ?? method.channel ?? null
}

export function mapReview(dto: Schemas['PaymentReviewResponse']): PaymentReview {
  return {
    submissionId: dto.submission_id,
    batchName: dto.batch_name,
    submittedBy: dto.submitted_by ?? null,
    submitterPhone: dto.submitter_phone ?? null,
    submittedAt: dto.submitted_at,
    paidOn: dto.paid_on,
    totalAmount: Money.fromWire(dto.total_amount),
    owedTogether: Money.fromWire(dto.owed_together),
    difference: Money.fromWire(dto.difference),
    comparison: dto.comparison,
    transactionId: dto.transaction_id ?? null,
    fromAccount: dto.from_account ?? null,
    channelLabel: channelLabel(dto.method),
    payerNote: dto.payer_note ?? null,
    children: dto.children.map((c) => ({
      claimId: c.claim_id,
      enrollmentId: c.enrollment_id,
      displayName: c.display_name,
      period: c.period,
      owed: Money.fromWire(c.owed),
    })),
    duplicateOf: dto.duplicate_of
      ? {
          displayName: dto.duplicate_of.display_name,
          amount: Money.fromWire(dto.duplicate_of.amount),
          status: dto.duplicate_of.status,
          decidedAt: dto.duplicate_of.decided_at ?? null,
        }
      : null,
  }
}

/** The name a review card leads with: the first child, else the sender. */
export function reviewName(review: PaymentReview): string {
  return review.children[0]?.displayName ?? review.submittedBy ?? ''
}

// ---------------------------------------------------------------- Batches

export interface BatchSummary {
  id: string
  name: string
  active: boolean
  enrollmentCount: number
  acceptedCount: number
  defaultFee: Money | null
  feeDueDay: number | null
  schedule: { weekday: number; startTime: string; endTime: string }[]
  subjects: string[]
}

export function mapBatch(dto: Schemas['BatchResponse']): BatchSummary {
  return {
    id: dto.id,
    name: dto.name,
    active: dto.active,
    enrollmentCount: dto.enrollment_count,
    acceptedCount: dto.accepted_count,
    defaultFee: Money.fromWireOrNull(dto.default_fee),
    feeDueDay: dto.fee_due_day ?? null,
    schedule: dto.schedule.map((s) => ({
      weekday: s.weekday,
      startTime: s.start_time,
      endTime: s.end_time,
    })),
    subjects: (dto.subjects as string[]).map(String),
  }
}

/** The order a Bangladeshi week runs, Saturday first, server-numbered (0 = Monday). */
export const WEEK_ORDER: readonly number[] = [5, 6, 0, 1, 2, 3, 4]

export function sortedDays(schedule: BatchSummary['schedule']): number[] {
  const days = new Set(schedule.map((s) => s.weekday))
  return WEEK_ORDER.filter((d) => days.has(d))
}

// ----------------------------------------------------------------- Roster

export interface RosterSeat {
  enrollmentId: string
  displayName: string
  guardianPhone: string | null
  fee: Money | null
  studentState: string
  guardianState: string
  status: string
  chip: FeeChipModel | null
}

/**
 * One seat's chip, from the fee row the server sent. The precedence is
 * `BatchDetailMapper.chipFor`'s: a payment being checked first, then
 * overdue (the server says how many days), then the month's status.
 */
export function feeChipFor(row: Schemas['RosterFeeRowResponse'] | undefined): FeeChipModel | null {
  if (!row) return null
  const verifying = Money.fromWireOrNull(row.verifying)
  if (verifying) return { kind: 'verifying', amount: verifying }
  if (row.days_overdue !== null && row.days_overdue !== undefined) {
    return { kind: 'overdue', days: row.days_overdue, amount: Money.fromWire(row.outstanding) }
  }
  switch (row.current_status) {
    case 'partly_paid':
      return { kind: 'partial', left: Money.fromWire(row.outstanding) }
    case 'paid':
      return { kind: 'paid' }
    case 'waived':
      return { kind: 'waived' }
    case 'unpaid':
      return { kind: 'due', dueDate: row.due_date ?? null }
    default:
      return null
  }
}

export function mapRoster(
  rows: Schemas['RosterRowResponse'][],
  fees: Schemas['BatchFeesResponse'] | null,
): RosterSeat[] {
  const byId = new Map((fees?.seats ?? []).map((s) => [s.enrollment_id, s]))
  return rows.map((r) => ({
    enrollmentId: r.enrollment_id,
    displayName: r.display_name,
    guardianPhone: r.guardian_phone ?? null,
    fee: Money.fromWireOrNull(r.fee_amount),
    studentState: r.student_state,
    guardianState: r.guardian_state,
    status: r.status,
    chip: feeChipFor(byId.get(r.enrollment_id)),
  }))
}

// ------------------------------------------------------------------- Dues

export type DuesBucket = 'over_30' | 'late' | 'not_late'

export interface DuesRow {
  enrollmentId: string
  displayName: string
  batchId: string
  batchName: string
  bucket: DuesBucket
  daysLate: number | null
  outstanding: Money
  oldestPeriod: string | null
  latestPeriod: string | null
  lastRemindedAt: string | null
  remindable: boolean
}

export interface DuesModel {
  total: Money
  lateTotal: Money
  count: number
  remindable: number
  groups: { bucket: DuesBucket; count: number; share: number; total: Money }[]
  rows: DuesRow[]
}

/** Server bucket order, most urgent first, as the design lists them. */
export const BUCKET_ORDER: readonly DuesBucket[] = ['over_30', 'late', 'not_late']

export function mapDues(dto: Schemas['DuesResponse']): DuesModel {
  return {
    total: Money.fromWire(dto.summary.total),
    lateTotal: Money.fromWire(dto.summary.late_total),
    count: dto.summary.count,
    remindable: dto.summary.remindable,
    groups: dto.summary.groups.map((g) => ({
      bucket: g.bucket,
      count: g.count,
      share: g.share,
      total: Money.fromWire(g.total),
    })),
    rows: (dto.rows ?? []).map((r) => ({
      enrollmentId: r.enrollment_id,
      displayName: r.display_name,
      batchId: r.batch_id,
      batchName: r.batch_name,
      bucket: r.bucket,
      daysLate: r.days_late ?? null,
      outstanding: Money.fromWire(r.outstanding),
      oldestPeriod: r.oldest_unpaid_period ?? null,
      latestPeriod: r.latest_unpaid_period ?? null,
      lastRemindedAt: r.last_reminded_at ?? null,
      remindable: r.remindable,
    })),
  }
}

/** The chip a dues row wears: overdue with the server's day count, else due. */
export function duesChip(row: DuesRow): FeeChipModel {
  return row.bucket === 'not_late' || row.daysLate === null
    ? { kind: 'due', dueDate: null, amount: null }
    : { kind: 'overdue', days: row.daysLate, amount: null }
}

// ----------------------------------------------------------------- Verify

export interface QueueModel {
  pending: PaymentReview[]
  decidedRecently: {
    submissionId: string
    displayName: string
    batchName: string
    amount: Money
    status: 'approved' | 'pending' | 'rejected'
    decidedAt: string
  }[]
}

export function mapQueue(dto: Schemas['VerificationQueueResponse']): QueueModel {
  return {
    pending: dto.pending.map(mapReview),
    decidedRecently: dto.decided_recently.map((d) => ({
      submissionId: d.submission_id,
      displayName: d.display_name,
      batchName: d.batch_name,
      amount: Money.fromWire(d.amount),
      status: d.status,
      decidedAt: d.decided_at,
    })),
  }
}
