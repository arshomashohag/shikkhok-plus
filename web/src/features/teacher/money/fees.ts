/**
 * One seat's fees, as the teacher reads them: the cycles, the six-month
 * strip and each month's latest payment line. Mirrors `FeeStateMapper`,
 * `MonthStripMapper` and `HistoryLine.kt`. A status the client does not
 * know fails the whole mapping rather than being guessed at.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money, MoneyFormatError } from '../../../core/money'

export type CycleStatus = 'paid' | 'partly_paid' | 'unpaid' | 'waived'
export type StripKind = 'paid' | 'partly_paid' | 'unpaid' | 'waived' | 'checking'
export type ClaimOutcome = 'pending' | 'approved_full' | 'approved_partial' | 'rejected'

export interface HistoryLine {
  amount: Money
  channel: string
  paidOn: string
  outcome: ClaimOutcome
  decisionNote: string | null
  coveredNames: string[]
}

export interface FeeCycleRow {
  period: string
  status: CycleStatus
  /** Paid or waived: nothing more is expected for it. */
  settled: boolean
  charged: Money
  outstanding: Money
  dueDate: string
}

export interface MonthCell {
  period: string
  kind: StripKind
  line: HistoryLine | null
}

export type FeeHistory =
  | { kind: 'empty' }
  | { kind: 'loaded'; totalOutstanding: Money; rows: FeeCycleRow[]; months: MonthCell[] }

const CYCLE: readonly CycleStatus[] = ['paid', 'partly_paid', 'unpaid', 'waived']
const STRIP: readonly StripKind[] = ['paid', 'partly_paid', 'unpaid', 'waived', 'checking']
const OUTCOMES: readonly ClaimOutcome[] = [
  'pending',
  'approved_full',
  'approved_partial',
  'rejected',
]

function known<T extends string>(allowed: readonly T[], value: string, what: string): T {
  if ((allowed as readonly string[]).includes(value)) return value as T
  throw new MoneyFormatError(`Unknown ${what} '${value}'`)
}

export function mapHistoryLine(dto: Schemas['HistoryLineResponse']): HistoryLine {
  return {
    amount: Money.fromWire(dto.amount),
    channel: dto.channel,
    paidOn: dto.paid_on,
    outcome: known(OUTCOMES, dto.status, 'claim status'),
    decisionNote: dto.decision_note ?? null,
    coveredNames: dto.covered_names ?? [],
  }
}

export function mapFeeHistory(dto: Schemas['FeeHistoryResponse']): FeeHistory {
  // Nothing CHARGED yet is not the same as everything paid.
  if (dto.cycles.length === 0) return { kind: 'empty' }
  const rows = dto.cycles
    .map((c) => {
      const status = known(CYCLE, c.status, 'fee status')
      return {
        period: c.period,
        status,
        settled: status === 'paid' || status === 'waived',
        charged: Money.fromWire(c.charged),
        outstanding: Money.fromWire(c.outstanding),
        dueDate: c.due_date,
      }
    })
    .sort((a, b) => (a.period < b.period ? 1 : a.period > b.period ? -1 : 0))
  return {
    kind: 'loaded',
    totalOutstanding: Money.fromWire(dto.total_outstanding),
    rows,
    months: (dto.month_states ?? []).map(mapMonthCell),
  }
}

export function mapMonthCell(dto: Schemas['MonthStateResponse']): MonthCell {
  return {
    period: dto.period,
    kind: known(STRIP, dto.state, 'month state'),
    line: dto.history_line ? mapHistoryLine(dto.history_line) : null,
  }
}

/** The strip's glyph per state, as `FeeHistoryScreen.glyph`: shape, not just colour. */
export const STRIP_GLYPH: Record<StripKind, string> = {
  paid: '✓',
  partly_paid: '½',
  unpaid: '!',
  waived: '○',
  checking: '…',
}

/** The string naming a strip state. */
export const STRIP_WORD: Record<StripKind, string> = {
  paid: 'fees_status_paid',
  partly_paid: 'fees_status_partly_paid',
  unpaid: 'fees_status_unpaid',
  waived: 'fees_status_waived',
  checking: 'fee_strip_checking',
}

/** The string for a payment line's outcome (`HistoryLineText.kt`). */
export const HISTORY_FORMAT: Record<ClaimOutcome, string> = {
  pending: 'history_line_pending',
  approved_full: 'history_line_approved_full',
  approved_partial: 'history_line_approved_partial',
  rejected: 'history_line_rejected',
}
