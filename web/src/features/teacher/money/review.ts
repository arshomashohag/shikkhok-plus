/**
 * One payment, as the teacher reviews it, and the approval sheet's rules.
 *
 * The web counterpart of `PaymentReviewViewModel.kt` and
 * `ReviewUiState.kt`'s `ApprovalSheet`. Every figure is the server's: the
 * sheet compares the amount the teacher TYPED with what is owed together
 * only to decide which question to ask (carry or waive? which child?), and
 * the server re-checks every choice and refuses one that does not apply.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'
import { mapReview, type PaymentReview } from '../mappers'

export const REVIEW_NOTE_MAX = 500

/** The server's code for "someone decided this while you were looking". */
export const ALREADY_DECIDED_CODE = 'PAYMENT_ALREADY_DECIDED'

export type ReviewStatus = 'pending' | 'approved' | 'rejected'

export interface PaymentMethodLine {
  kind: 'bank' | 'cash' | 'legacy' | 'mobile'
  provider: string | null
  /** The mobile number or bank account number the money was sent to. */
  number: string | null
}

/** An exam or other fee, as a payment names it. */
export interface FeeRef {
  id: string
  label: string
  kind: 'exam' | 'other'
  dueOn: string
}

/** What a payment is for: the months (`null`) or one fee. */
export type PaymentFor = FeeRef | null

export interface PaymentDetail extends PaymentReview {
  status: ReviewStatus
  decidedAt: string | null
  decisionNote: string | null
  /** `student` or `guardian`: who sent it, when the server says. */
  submitterRole: 'student' | 'guardian' | null
  method: PaymentMethodLine
  /** Per child, what was approved, once decided. */
  approved: Record<string, Money | null>
  /** What it is applied to (or, in a preview, would be). */
  appliedTo: PaymentFor
  /** What the family chose. */
  requested: PaymentFor
  /** The extra fees every covered child was charged, which it could go to. */
  options: FeeRef[]
}

function feeRef(dto: Schemas['ExtraFeeRefResponse'] | null | undefined): PaymentFor {
  return dto
    ? { id: dto.extra_fee_id, label: dto.label, kind: dto.purpose, dueOn: dto.due_on }
    : null
}

/** Whether two "payment for" values name the same thing. */
export function samePurpose(a: PaymentFor, b: PaymentFor): boolean {
  return (a?.id ?? null) === (b?.id ?? null)
}

/**
 * The purpose fields for an approval, sent only when the teacher chose
 * something other than what the payment is applied to now: `preview` is
 * `'monthly'`, a fee id, or null for no change.
 */
export function purposeFields(
  preview: string | null,
): Pick<Schemas['PaymentApprovalRequest'], 'purpose' | 'extra_fee_id'> {
  if (preview === null) return {}
  return preview === 'monthly'
    ? { purpose: 'monthly', extra_fee_id: null }
    : { purpose: 'extra', extra_fee_id: preview }
}

export function mapPaymentDetail(dto: Schemas['PaymentReviewResponse']): PaymentDetail {
  const role = dto.submitted_by
  return {
    ...mapReview(dto),
    status: dto.status,
    decidedAt: dto.decided_at ?? null,
    decisionNote: dto.decision_note ?? null,
    submitterRole: role === 'student' || role === 'guardian' ? role : null,
    method: {
      kind: dto.method.kind,
      provider: dto.method.provider ?? dto.method.channel ?? null,
      number:
        dto.method.kind === 'bank'
          ? (dto.method.account_number ?? null)
          : (dto.method.mobile_number ?? null),
    },
    approved: Object.fromEntries(
      dto.children.map((c) => [c.enrollment_id, Money.fromWireOrNull(c.approved_amount)]),
    ),
    appliedTo: dto.purpose === 'extra' ? feeRef(dto.extra_fee) : null,
    requested: dto.requested_purpose === 'extra' ? feeRef(dto.requested_extra_fee) : null,
    options: (dto.extra_fee_options ?? [])
      .map((o) => feeRef(o))
      .filter((o): o is FeeRef => o !== null),
  }
}

/**
 * Whether decision controls may show: a pending payment, or a decided one
 * the teacher has chosen to change (`ReviewUiState.Loaded.canDecide`).
 */
export function canDecide(detail: Pick<PaymentDetail, 'status'>, correcting: boolean): boolean {
  return detail.status === 'pending' || correcting
}

// --------------------------------------------------------------- the sheet

export type AmountSide = 'invalid' | 'exact' | 'short' | 'over'
export type Disposition = 'carried' | 'waived'

export interface SheetInput {
  typed: string
  disposition: Disposition | null
  /** The child who carries a shortfall or receives a credit. */
  childId: string | null
  note: string
}

export interface SheetState {
  received: Money | null
  side: AmountSide
  needsDisposition: boolean
  needsChild: boolean
  /** The server's difference, only while the amount is the one reported. */
  shownDifference: Money | null
  canConfirm: boolean
}

/** The sheet's starting point: the amount the payer reported. */
export function openSheet(review: PaymentReview, note = ''): SheetInput {
  return {
    typed: review.totalAmount.wire.replace(/\.00$/, ''),
    disposition: null,
    childId: null,
    note: note.slice(0, REVIEW_NOTE_MAX),
  }
}

/**
 * Change the typed amount. A choice that no longer applies to the new
 * amount's side is dropped, as `PaymentReviewViewModel.typeAmount` does.
 */
export function typeAmount(review: PaymentReview, input: SheetInput, typed: string): SheetInput {
  const before = sheetState(review, input).side
  const next = { ...input, typed }
  return sheetState(review, next).side === before
    ? next
    : { ...next, disposition: null, childId: null }
}

export function sheetState(review: PaymentReview, input: SheetInput): SheetState {
  const received = Money.fromTyped(input.typed)
  const order = received ? received.compare(review.owedTogether) : null
  const side: AmountSide =
    order === null ? 'invalid' : order === 0 ? 'exact' : order < 0 ? 'short' : 'over'
  const needsDisposition = side === 'short'
  const needsChild = review.children.length > 1 && (side === 'short' || side === 'over')
  const shownDifference =
    received !== null && received.compare(review.totalAmount) === 0 ? review.difference : null
  return {
    received,
    side,
    needsDisposition,
    needsChild,
    shownDifference,
    canConfirm:
      side !== 'invalid' &&
      (!needsDisposition || input.disposition !== null) &&
      (!needsChild || input.childId !== null),
  }
}

/**
 * The approval request for a confirmed sheet, or null while it cannot be
 * sent. Exactly `PaymentReviewViewModel.confirmApproval`'s body: the bearer
 * is named only when several children share the payment, as the carrier
 * of a shortfall or the recipient of a credit, never both.
 */
export function sheetBody(
  review: PaymentReview,
  input: SheetInput,
  correcting: boolean,
): Schemas['PaymentApprovalRequest'] | null {
  const state = sheetState(review, input)
  if (!state.canConfirm || !state.received) return null
  const bearer = state.needsChild ? input.childId : null
  return {
    received_amount: state.received.wire,
    shortfall_disposition: state.needsDisposition ? input.disposition : null,
    carried_by_enrollment_id: state.side === 'short' ? bearer : null,
    credit_to_enrollment_id: state.side === 'over' ? bearer : null,
    note: noteOrNull(input.note),
    correcting,
  }
}

/** Approve as reported: only for a payment the server says matches. */
export function asReportedBody(
  review: PaymentReview,
  note: string,
  correcting: boolean,
): Schemas['PaymentApprovalRequest'] | null {
  if (review.comparison !== 'matches') return null
  return { received_amount: review.totalAmount.wire, note: noteOrNull(note), correcting }
}

export function rejectionBody(
  note: string,
  correcting: boolean,
): Schemas['PaymentRejectionRequest'] {
  return { note: noteOrNull(note), correcting }
}

function noteOrNull(note: string): string | null {
  const trimmed = note.trim().slice(0, REVIEW_NOTE_MAX)
  return trimmed === '' ? null : trimmed
}
