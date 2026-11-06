/**
 * Exam and other fees: the calls, the mappers and the raise form's rules.
 *
 * **Every figure is the server's.** A fee's totals, each student's paid and
 * owed amounts and their status arrive computed; the form sends what the
 * teacher typed and the server refuses anything it cannot raise. Nothing
 * here adds, subtracts or compares money.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'

const enc = encodeURIComponent

export type FeeKind = 'exam' | 'other'
export type ChargeStatus = 'paid' | 'partly_paid' | 'unpaid' | 'waived'

// ------------------------------------------------------------------ calls

export const listExtraFees = (batchId: string) =>
  request<Schemas['BatchExtraFeesResponse']>('GET', `/v1/batches/${enc(batchId)}/extra-fees`)

export const readExtraFee = (feeId: string) =>
  request<Schemas['ExtraFeeDetailResponse']>('GET', `/v1/extra-fees/${enc(feeId)}`)

export const raiseExtraFee = (batchId: string, body: Schemas['ExtraFeeRaiseRequest']) =>
  request<Schemas['ExtraFeeSummaryResponse']>('POST', `/v1/batches/${enc(batchId)}/extra-fees`, {
    body,
  })

// ---------------------------------------------------------------- mappers

export interface FeeSummary {
  id: string
  kind: FeeKind
  label: string
  examTitle: string | null
  amount: Money
  dueOn: string
  studentCount: number
  paidCount: number
  owingCount: number
  chargedTotal: Money
  collectedTotal: Money
  owedTotal: Money
}

export interface FeeStudent {
  enrollmentId: string
  name: string
  charged: Money
  paid: Money
  owed: Money
  status: ChargeStatus
}

export interface FeeDetail extends FeeSummary {
  students: FeeStudent[]
}

export function mapFeeSummary(dto: Schemas['ExtraFeeSummaryResponse']): FeeSummary {
  return {
    id: dto.extra_fee_id,
    kind: dto.purpose,
    label: dto.label,
    examTitle: dto.exam_title ?? null,
    amount: Money.fromWire(dto.amount),
    dueOn: dto.due_on,
    studentCount: dto.student_count,
    paidCount: dto.paid_count,
    owingCount: dto.owing_count,
    chargedTotal: Money.fromWire(dto.charged_total),
    collectedTotal: Money.fromWire(dto.collected_total),
    owedTotal: Money.fromWire(dto.owed_total),
  }
}

export function mapFeeDetail(dto: Schemas['ExtraFeeDetailResponse']): FeeDetail {
  return {
    ...mapFeeSummary(dto),
    students: dto.students.map((s) => ({
      enrollmentId: s.enrollment_id,
      name: s.display_name,
      charged: Money.fromWire(s.charged),
      paid: Money.fromWire(s.paid),
      owed: Money.fromWire(s.owed),
      status: s.status,
    })),
  }
}

// ------------------------------------------------------------ raise form

/** What happens to one student: the fee, a waiver, or left out. */
export type SeatChoice = 'charge' | 'waive' | 'leave_out'

export const FEE_LABEL_MAX = 80

export interface RaiseInput {
  kind: FeeKind
  label: string
  /** An exam id, or '' for none. */
  examId: string
  typed: string
  /** ISO date, `YYYY-MM-DD`. */
  dueOn: string
  /** Students not charged in full, by enrollment id. */
  seats: Record<string, SeatChoice>
  /** One per opened form, reused on every resend so the server replays. */
  clientMutationId: string
}

export function openRaise(clientMutationId: string, dueOn: string): RaiseInput {
  return {
    kind: 'exam',
    label: '',
    examId: '',
    typed: '',
    dueOn,
    seats: {},
    clientMutationId,
  }
}

/** How many of these students the fee would reach: everyone not left out. */
export function chargedCount(input: RaiseInput, studentIds: readonly string[]): number {
  return studentIds.filter((id) => input.seats[id] !== 'leave_out').length
}

/**
 * The request for the form, or null while it cannot be sent. The server
 * re-checks every field; this only stops a send that is certain to fail.
 */
export function raiseBody(
  input: RaiseInput,
  studentIds: readonly string[],
): Schemas['ExtraFeeRaiseRequest'] | null {
  const amount = Money.fromTyped(input.typed)
  const label = input.label.trim()
  if (!amount || label === '' || label.length > FEE_LABEL_MAX || input.dueOn === '') return null
  if (chargedCount(input, studentIds) === 0) return null
  const choices = Object.entries(input.seats)
  return {
    purpose: input.kind,
    label,
    exam_id: input.kind === 'exam' && input.examId !== '' ? input.examId : null,
    amount: amount.wire,
    due_on: input.dueOn,
    seat_amounts: choices
      .filter(([, choice]) => choice === 'waive')
      .map(([enrollment_id]) => ({ enrollment_id, amount: '0.00' })),
    excluded_enrollment_ids: choices
      .filter(([, choice]) => choice === 'leave_out')
      .map(([id]) => id),
    client_mutation_id: input.clientMutationId,
  }
}
