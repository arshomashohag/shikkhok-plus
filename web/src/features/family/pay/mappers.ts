/**
 * The family paying screens' mappers: the web counterparts of Android's
 * `PayMapper` and `PaymentsMapper`, and the test targets.
 *
 * **Nothing here computes money** [TC-9]. What is owed comes from the
 * server (`/v1/payments/owed`, the payables, the payments history); the
 * amount sent is what the person typed. The only checks are on the shape
 * of what was typed — an amount, a date, a long-enough transaction ID —
 * and the server decides everything else and says so by `message_key`.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money, MoneyFormatError } from '../../../core/money'
import type { FeeChipModel } from '../../../ui/components'

// ------------------------------------------------------------ the seats

export interface PaySeat {
  enrollmentId: string
  /** Whose seat this is, when a guardian reads it; null for the student's own. */
  childName: string | null
}

/** One teacher's batch: the unit a payment is for. Siblings in it pay together. */
export interface PayBatch {
  key: string
  name: string
  teacherName: string | null
  seats: PaySeat[]
}

function group(
  rows: {
    enrollmentId: string
    batchName: string
    teacherName: string | null
    childName: string | null
  }[],
): PayBatch[] {
  const batches = new Map<string, PayBatch>()
  for (const r of rows) {
    const key = `${r.batchName}|${r.teacherName ?? ''}`
    const batch = batches.get(key) ?? {
      key,
      name: r.batchName,
      teacherName: r.teacherName,
      seats: [],
    }
    batch.seats.push({ enrollmentId: r.enrollmentId, childName: r.childName })
    batches.set(key, batch)
  }
  return [...batches.values()]
}

/** A student's seats, grouped by batch (`PayMapper.batches`). */
export function myPayBatches(rows: Schemas['StudentBatchResponse'][]): PayBatch[] {
  return group(
    rows.map((r) => ({
      enrollmentId: r.enrollment_id,
      batchName: r.batch_name,
      teacherName: r.teacher_display_name ?? null,
      childName: null,
    })),
  )
}

/** A guardian's children's seats, grouped by batch, each named for its child. */
export function childPayBatches(home: Schemas['GuardianHomeResponse']): PayBatch[] {
  return group(
    (home.children ?? []).flatMap((child) =>
      (child.batches ?? []).map((b) => ({
        enrollmentId: b.enrollment_id,
        batchName: b.batch_name,
        teacherName: b.teacher_display_name ?? null,
        childName: child.display_name,
      })),
    ),
  )
}

/** The batch the screen opens on: the one holding the seat it was opened for. */
export function initialBatch(batches: PayBatch[], seat: string): PayBatch | null {
  return batches.find((b) => b.seats.some((s) => s.enrollmentId === seat)) ?? batches[0] ?? null
}

/**
 * Which seats start chosen (`PayMapper.initialSelection`): just the seat
 * the screen was opened for when it is in this batch, else every seat in
 * it, so siblings in one batch can pay together.
 */
export function initialSelection(batch: PayBatch, seat: string | null): string[] {
  const all = batch.seats.map((s) => s.enrollmentId)
  return seat !== null && all.includes(seat) ? [seat] : all
}

/** Toggle one seat, keeping the batch's order and never emptying the choice. */
export function toggleSeat(batch: PayBatch, selected: readonly string[], seat: string): string[] {
  const next = selected.includes(seat)
    ? selected.filter((s) => s !== seat)
    : batch.seats.map((s) => s.enrollmentId).filter((s) => s === seat || selected.includes(s))
  return next.length === 0 ? [...selected] : next
}

// --------------------------------------------------------------- the form

export type PayChoice =
  { kind: 'method'; method: Schemas['PaymentMethodResponse'] } | { kind: 'cash' }

export interface PayForm {
  amount: string
  paidOn: string
  transactionId: string
  fromAccount: string
  note: string
}

/** The shortest transaction ID any of the mobile services issues (PayMapper). */
export const MIN_TRANSACTION_ID = 6

export type FormProblem = 'transaction_id_short'

/**
 * The request the form describes, or why there is none yet
 * (`PayMapper.requestOf`). A form that is merely incomplete has neither a
 * request nor a problem: the button stays off and nothing is shouted.
 */
export function requestOf(
  selected: readonly string[],
  choice: PayChoice,
  form: PayForm,
): { request: Schemas['PaymentSubmitRequest'] | null; problem: FormProblem | null } {
  const amount = Money.fromTyped(form.amount)
  const reference = form.transactionId.trim()
  const account = form.fromAccount.trim()
  const kind = choice.kind === 'method' ? choice.method.kind : null
  if (kind === 'mobile' && reference.length > 0 && reference.length < MIN_TRANSACTION_ID) {
    return { request: null, problem: 'transaction_id_short' }
  }
  const missing =
    amount === null ||
    form.paidOn.trim() === '' ||
    selected.length === 0 ||
    (kind === 'mobile' && reference === '') ||
    (kind === 'bank' && account === '')
  if (missing || amount === null) return { request: null, problem: null }
  return {
    request: {
      enrollment_ids: [...selected],
      payment_method_id: choice.kind === 'method' ? choice.method.method_id : null,
      cash: choice.kind === 'cash',
      amount: amount.wire,
      paid_on: form.paidOn,
      transaction_id: kind === 'mobile' ? reference : null,
      from_account: kind === 'bank' ? account : null,
      note: form.note.trim() || null,
    },
    problem: null,
  }
}

export interface PaymentAttempt {
  /** The request without its key, to tell whether a retry is the same payment. */
  payment: string
  clientMutationId: string
}

/**
 * Keep the mutation id while the payment is unchanged (`PayMapper.attemptFor`).
 *
 * A send whose response was lost and is then retried presents the same
 * id, so the server answers with the original submission instead of
 * recording the money twice. Change any detail and it is a new payment
 * with a new id.
 */
export function attemptFor(
  previous: PaymentAttempt | null,
  request: Schemas['PaymentSubmitRequest'],
  freshId: () => string,
): PaymentAttempt {
  const payment = JSON.stringify(request)
  return previous && previous.payment === payment
    ? previous
    : { payment, clientMutationId: freshId() }
}

export type SentOutcome = 'pending' | 'approved' | 'rejected'

/** A resend the teacher already decided says so (`PayMapper.outcomeOf`). */
export function outcomeOf(status: Schemas['PaymentSubmittedResponse']['status']): SentOutcome {
  return status === 'approved' ? 'approved' : status === 'rejected' ? 'rejected' : 'pending'
}

/** "A", "A and B", "A, B and C" (PayScreen's `joined`). */
export function joinNames(names: readonly string[], and: string): string {
  if (names.length <= 1) return names[0] ?? ''
  return `${names.slice(0, -1).join(', ')} ${and} ${names[names.length - 1]}`
}

/** The amount field's starting value: what the server says is owed, when anything is. */
export function suggestedAmount(owed: Money): string {
  return owed.isZero() ? '' : owed.wire.replace(/\.00$/, '')
}

/** Today in Dhaka as `YYYY-MM-DD`, the default "date paid". */
export function dhakaToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Dhaka',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now)
}

// -------------------------------------------------------- payments (G2)

export type LineState = 'paid' | 'partly_paid' | 'waived' | 'verifying' | 'due'

export interface PaymentLine {
  enrollmentId: string
  batchName: string
  amount: Money
  state: LineState
  dueDate: string
  sentOn: string | null
  decidedOn: string | null
  channel: string | null
}

export interface PaymentsModel {
  childName: string
  year: number
  paidThisYear: Money
  months: { period: string; lines: PaymentLine[] }[]
}

const LINE_STATES: readonly LineState[] = ['paid', 'partly_paid', 'waived', 'verifying', 'due']

/**
 * A child's payments (`PaymentsMapper.afterLoad`). A line state the client
 * does not know fails the whole mapping, rather than being shown as
 * something it is not.
 */
export function mapPayments(dto: Schemas['PaymentsResponse']): PaymentsModel {
  return {
    childName: dto.display_name,
    year: dto.year,
    paidThisYear: Money.fromWire(dto.paid_this_year),
    months: (dto.months ?? []).map((m) => ({
      period: m.period,
      lines: m.lines.map((l) => {
        if (!LINE_STATES.includes(l.state as LineState)) {
          throw new MoneyFormatError(`Unknown payment line state '${l.state}'`)
        }
        return {
          enrollmentId: l.enrollment_id,
          batchName: l.batch_name,
          amount: Money.fromWire(l.amount),
          state: l.state as LineState,
          dueDate: l.due_date,
          sentOn: l.sent_on ?? null,
          decidedOn: l.decided_on ?? null,
          channel: l.channel ?? null,
        }
      }),
    })),
  }
}

/** The chip a payment line wears (PaymentsScreen's `chipOf`). */
export function lineChip(state: LineState): FeeChipModel {
  switch (state) {
    case 'paid':
      return { kind: 'paid' }
    case 'waived':
      return { kind: 'waived' }
    case 'partly_paid':
      return { kind: 'partial', left: null }
    case 'verifying':
      return { kind: 'verifying', amount: null }
    case 'due':
      return { kind: 'due', dueDate: null }
  }
}

/** What the payments screen leads with: the next thing owed, as the server ordered it. */
export interface NextPayable {
  batchName: string
  period: string
  amountDue: Money
  totalDue: Money
  laterPeriods: number
}

export function nextPayable(dto: Schemas['PayablesResponse']): NextPayable | null {
  const first = dto.payable?.[0]
  if (!first) return null
  return {
    batchName: first.batch_name,
    period: first.period,
    amountDue: Money.fromWire(first.amount_due),
    totalDue: Money.fromWire(first.total_due),
    laterPeriods: first.later_periods,
  }
}

/** "তাসনিম জাহান" → "তাসনিম", as Android's `firstName`. */
export function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name
}
