/**
 * One seat's progress dashboard, teacher reader (`DashboardViewModel.kt`).
 * Every percentage, average, direction and amount is the server's; the
 * client draws bars at the percent it was sent.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'
import { mapMonthCell, type MonthCell } from './fees'

export type Direction = 'up' | 'down' | 'same'

export interface Dashboard {
  attendancePercent: number | null
  present: number
  held: number
  examAveragePercent: number | null
  direction: Direction | null
  owed: Money
  attendance: { period: string; percent: number | null; inProgress: boolean }[]
  exams: {
    examId: string
    title: string
    date: string
    subject: string | null
    marks: number | null
    total: number
    percent: number | null
    average: number | null
    highest: number | null
  }[]
  feeMonths: MonthCell[]
}

export function mapDashboard(dto: Schemas['DashboardResponse']): Dashboard {
  const d = dto.tiles.direction
  return {
    attendancePercent: dto.tiles.attendance_percent ?? null,
    present: dto.tiles.present,
    held: dto.tiles.held,
    examAveragePercent: dto.tiles.exam_average_percent ?? null,
    direction: d === 'up' || d === 'down' || d === 'same' ? d : null,
    owed: Money.fromWire(dto.tiles.owed),
    attendance: dto.attendance_by_month.map((m) => ({
      period: m.period,
      percent: m.percent ?? null,
      inProgress: m.in_progress,
    })),
    exams: dto.exams.map((e) => ({
      examId: e.exam_id,
      title: e.title,
      date: e.date,
      subject: e.subject ?? null,
      marks: e.marks ?? null,
      total: e.total,
      percent: e.percent ?? null,
      average: e.batch_average ?? null,
      highest: e.batch_highest ?? null,
    })),
    feeMonths: dto.fee_months.map((m) => mapMonthCell({ period: m.period, state: m.state })),
  }
}

/** `DashboardScreen.arrow`: the server's direction, as a glyph. */
export const ARROW: Record<Direction, string> = { up: '↑', down: '↓', same: '→' }
