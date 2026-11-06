/**
 * The "Record payment" sheet's rules: a teacher records money received by
 * hand for one seat (`POST /v1/enrollments/{id}/payments`).
 *
 * The web counterpart of `RecordPaymentSheet` in `FeesViewModel.kt`.
 * **Every figure is the server's.** The amount starts at what the server
 * says the seat owes; comparing what the teacher TYPED with it only decides
 * whether to ask carry-or-waive, exactly as the approval sheet does
 * (`review.ts`). The server re-checks the choice and refuses one that does
 * not apply, so nothing here is a business rule the server does not also
 * enforce.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'
import { DEFAULT_SERVICES } from './methods'
import type { AmountSide, Disposition } from './review'

/** Money handed over in person: the default channel. */
export const CASH = 'cash'

/** Cash first, then the mobile services a family may send to directly. */
export const RECORD_CHANNELS: readonly string[] = [CASH, ...DEFAULT_SERVICES]

export const RECORD_NOTE_MAX = 500
export const RECORD_REFERENCE_MAX = 64

export interface RecordInput {
  typed: string
  channel: string
  reference: string
  note: string
  disposition: Disposition | null
  /** One per draft, reused on every resend so the server replays. */
  clientMutationId: string
}

export interface RecordState {
  received: Money | null
  side: AmountSide
  needsDisposition: boolean
  canConfirm: boolean
}

/**
 * The sheet's starting point: what the seat owes now, as the server said,
 * paid in cash. Nothing owed starts blank rather than at ৳0, which the
 * server would refuse.
 */
export function openRecord(owed: Money, clientMutationId: string): RecordInput {
  return {
    typed: owed.isZero() ? '' : owed.wire.replace(/\.00$/, ''),
    channel: CASH,
    reference: '',
    note: '',
    disposition: null,
    clientMutationId,
  }
}

export function recordState(owed: Money, input: RecordInput): RecordState {
  const received = Money.fromTyped(input.typed)
  const positive = received !== null && !received.isZero()
  const order = positive ? received.compare(owed) : null
  const side: AmountSide =
    order === null ? 'invalid' : order === 0 ? 'exact' : order < 0 ? 'short' : 'over'
  const needsDisposition = side === 'short'
  return {
    received: positive ? received : null,
    side,
    needsDisposition,
    canConfirm: side !== 'invalid' && (!needsDisposition || input.disposition !== null),
  }
}

/** Change the amount; a carry-or-waive that no longer applies is dropped. */
export function typeRecordAmount(owed: Money, input: RecordInput, typed: string): RecordInput {
  const before = recordState(owed, input).side
  const next = { ...input, typed }
  return recordState(owed, next).side === before ? next : { ...next, disposition: null }
}

/** The request for a confirmed sheet, or null while it cannot be sent. */
export function recordBody(
  owed: Money,
  input: RecordInput,
  extraFeeId?: string,
): Schemas['ReceivedPaymentRequest'] | null {
  const state = recordState(owed, input)
  if (!state.canConfirm || !state.received) return null
  return {
    amount: state.received.wire,
    channel: input.channel,
    reference: trimmed(input.reference, RECORD_REFERENCE_MAX),
    note: trimmed(input.note, RECORD_NOTE_MAX),
    shortfall_disposition: state.needsDisposition ? input.disposition : null,
    client_mutation_id: input.clientMutationId,
    ...(extraFeeId ? { purpose: 'extra' as const, extra_fee_id: extraFeeId } : {}),
  }
}

function trimmed(text: string, max: number): string | null {
  const value = text.trim().slice(0, max)
  return value === '' ? null : value
}
