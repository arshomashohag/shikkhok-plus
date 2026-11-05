/**
 * Collections: what was charged and collected, month by month, and one
 * batch's month seat by seat (`CollectionsViewModel.kt`,
 * `BatchMonthViewModel.kt`). Bar heights, totals and counts are the
 * server's; the client chooses which month to headline and filters seats
 * the server already sent.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'
import { mapHistoryLine, type HistoryLine } from './fees'

export interface MonthBar {
  period: string
  charged: Money
  collected: Money
  chargedBar: number
  collectedBar: number
  inProgress: boolean
}

export interface CollectionsReport {
  months: MonthBar[]
  outstanding: Money
  owingStudents: number
}

export function mapCollections(dto: Schemas['CollectionsResponse']): CollectionsReport {
  return {
    months: dto.months.map((m) => ({
      period: m.period,
      charged: Money.fromWire(m.charged),
      collected: Money.fromWire(m.collected),
      chargedBar: m.charged_bar,
      collectedBar: m.collected_bar,
      inProgress: m.in_progress,
    })),
    outstanding: Money.fromWire(dto.outstanding),
    owingStudents: dto.owing_students,
  }
}

/**
 * The month the screen leads with: the one chosen, else the latest month
 * that is no longer being collected, else the latest at all.
 */
export function headlineMonth(months: MonthBar[], chosen: string | null): MonthBar | null {
  return (
    months.find((m) => m.period === chosen) ??
    [...months].reverse().find((m) => !m.inProgress) ??
    months[months.length - 1] ??
    null
  )
}

export interface SeatCounts {
  paid: number
  checking: number
  owed: number
}

export interface BatchMonth {
  period: string
  collected: Money
  charged: Money
  counts: SeatCounts
  seats: MonthSeat[]
}

export type SeatKind = 'paid' | 'waived' | 'partial' | 'due' | 'overdue' | 'checking' | 'none'
export type MonthFilter = 'all' | 'paid' | 'checking' | 'owed'

export interface MonthSeat {
  enrollmentId: string
  displayName: string
  kind: SeatKind
  outstanding: Money
  daysOverdue: number | null
  verifying: Money | null
  line: HistoryLine | null
}

/** `BatchMonthViewModel.kindOf`: the server's state, with its overdue day count. */
export function seatKind(row: Schemas['RosterFeeRowResponse']): SeatKind {
  switch (row.state) {
    case 'paid':
      return 'paid'
    case 'waived':
      return 'waived'
    case 'partly_paid':
      return 'partial'
    case 'checking':
      return 'checking'
    case 'unpaid':
      return row.days_overdue !== null && row.days_overdue !== undefined ? 'overdue' : 'due'
    default:
      return 'none'
  }
}

export function mapBatchMonth(dto: Schemas['BatchFeesResponse']): BatchMonth {
  return {
    period: dto.period,
    collected: Money.fromWire(dto.collected),
    charged: Money.fromWire(dto.charged),
    counts: { paid: dto.counts.paid, checking: dto.counts.checking, owed: dto.counts.owed },
    seats: dto.seats.map((s) => ({
      enrollmentId: s.enrollment_id,
      displayName: s.display_name,
      kind: seatKind(s),
      outstanding: Money.fromWire(s.outstanding),
      daysOverdue: s.days_overdue ?? null,
      verifying: Money.fromWireOrNull(s.verifying),
      line: s.history_line ? mapHistoryLine(s.history_line) : null,
    })),
  }
}

/** Which filter a seat falls under; a seat never charged is under none but All. */
export function filterOf(kind: SeatKind): MonthFilter | null {
  switch (kind) {
    case 'paid':
    case 'waived':
      return 'paid'
    case 'checking':
      return 'checking'
    case 'partial':
    case 'due':
    case 'overdue':
      return 'owed'
    case 'none':
      return null
  }
}

export function visibleSeats(seats: MonthSeat[], filter: MonthFilter): MonthSeat[] {
  return filter === 'all' ? seats : seats.filter((s) => filterOf(s.kind) === filter)
}

/**
 * Whether the month's row offers "Record payment": a seat the server
 * reports as still owing (part paid, due or overdue). A seat being checked
 * already has a payment waiting, which the teacher decides on its own
 * screen; a settled seat has nothing to record against.
 */
export function canRecordFor(seat: Pick<MonthSeat, 'kind'>): boolean {
  return seat.kind === 'partial' || seat.kind === 'due' || seat.kind === 'overdue'
}
