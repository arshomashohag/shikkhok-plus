/**
 * One seat's fees, as the teacher reads them: the cycles, the six-month
 * strip and each month's latest payment line. Mirrors `FeeStateMapper`,
 * `MonthStripMapper` and `HistoryLine.kt`.
 *
 * A status the client does not know (a server newer than this tab's
 * JavaScript) becomes `unknown`: shown as "Unknown status", never guessed
 * at as paid or unpaid, and never failing the whole screen. That is safe
 * because nothing here decides money — every figure on the row is still
 * the server's — and the status only words it. A money value that is not
 * a decimal string still fails loudly: that is a contract break, not a
 * newer vocabulary.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'

export type CycleStatus = 'paid' | 'partly_paid' | 'unpaid' | 'waived' | 'unknown'
export type StripKind = 'paid' | 'partly_paid' | 'unpaid' | 'waived' | 'checking' | 'unknown'
export type ClaimOutcome = 'pending' | 'approved_full' | 'approved_partial' | 'rejected' | 'unknown'

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

const CYCLE = ['paid', 'partly_paid', 'unpaid', 'waived'] as const
const STRIP = ['paid', 'partly_paid', 'unpaid', 'waived', 'checking'] as const
const OUTCOMES = ['pending', 'approved_full', 'approved_partial', 'rejected'] as const

function known<T extends string>(allowed: readonly T[], value: string): T | 'unknown' {
  return (allowed as readonly string[]).includes(value) ? (value as T) : 'unknown'
}

export function mapHistoryLine(dto: Schemas['HistoryLineResponse']): HistoryLine {
  return {
    amount: Money.fromWire(dto.amount),
    channel: dto.channel,
    paidOn: dto.paid_on,
    outcome: known(OUTCOMES, dto.status),
    decisionNote: dto.decision_note ?? null,
    coveredNames: dto.covered_names ?? [],
  }
}

export function mapFeeHistory(dto: Schemas['FeeHistoryResponse']): FeeHistory {
  // Nothing CHARGED yet is not the same as everything paid.
  if (dto.cycles.length === 0) return { kind: 'empty' }
  const rows = dto.cycles
    .map((c) => {
      const status = known(CYCLE, c.status)
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
    kind: known(STRIP, dto.state),
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
  unknown: '?',
}

/** The string naming a strip state. */
export const STRIP_WORD: Record<StripKind, string> = {
  paid: 'fees_status_paid',
  partly_paid: 'fees_status_partly_paid',
  unpaid: 'fees_status_unpaid',
  waived: 'fees_status_waived',
  checking: 'fee_strip_checking',
  unknown: 'web_status_unknown',
}

/** The string naming a fee cycle's status. */
export const CYCLE_WORD: Record<CycleStatus, string> = {
  paid: 'fees_status_paid',
  partly_paid: 'fees_status_partly_paid',
  unpaid: 'fees_status_unpaid',
  waived: 'fees_status_waived',
  unknown: 'web_status_unknown',
}

/** The string for a payment line's outcome (`HistoryLineText.kt`). */
export const HISTORY_FORMAT: Record<ClaimOutcome, string> = {
  pending: 'history_line_pending',
  approved_full: 'history_line_approved_full',
  approved_partial: 'history_line_approved_partial',
  rejected: 'history_line_rejected',
  unknown: 'web_history_line_unknown',
}
