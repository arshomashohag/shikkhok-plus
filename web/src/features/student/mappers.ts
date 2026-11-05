/**
 * Student screens' mappers. The fee chip comes from the status the server
 * reported for the current period and its `verifying` flag; nothing here
 * compares an amount or a date.
 */
import type { Schemas } from '../../api/endpoints'
import { Money } from '../../core/money'
import type { FeeChipModel } from '../../ui/components'

export interface StudentBatch {
  enrollmentId: string
  batchName: string
  teacherName: string | null
  isNext: boolean
  schedule: { weekday: number; startTime: string }[]
  nextSession: {
    date: string
    startTime: string
    moved: boolean
    startsInMinutes: number | null
    subjectName: string | null
  } | null
  lastResult: { title: string; marks: number; totalMarks: number; rank: number | null } | null
  fee: { period: string; chip: FeeChipModel } | null
}

export function studentFeeChip(fee: Schemas['CurrentFeeResponse']): FeeChipModel {
  if (fee.verifying) return { kind: 'verifying', amount: null }
  switch (fee.status) {
    case 'paid':
      return { kind: 'paid' }
    case 'waived':
      return { kind: 'waived' }
    case 'partly_paid':
      return { kind: 'partial', left: Money.fromWire(fee.outstanding) }
    default:
      return { kind: 'due', dueDate: fee.due_date }
  }
}

export function mapStudentBatch(dto: Schemas['StudentBatchResponse']): StudentBatch {
  return {
    enrollmentId: dto.enrollment_id,
    batchName: dto.batch_name,
    teacherName: dto.teacher_display_name ?? null,
    isNext: dto.is_next ?? false,
    schedule: dto.schedule.map((s) => ({ weekday: s.weekday, startTime: s.start_time })),
    nextSession: dto.next_session
      ? {
          date: dto.next_session.date,
          startTime: dto.next_session.start_time,
          moved: dto.next_session.moved,
          startsInMinutes: dto.next_session.starts_in_minutes ?? null,
          subjectName: dto.next_session.subject_name ?? null,
        }
      : null,
    lastResult: dto.last_result
      ? {
          title: dto.last_result.title,
          marks: dto.last_result.marks,
          totalMarks: dto.last_result.total_marks,
          rank: dto.last_result.rank ?? null,
        }
      : null,
    fee: dto.current_fee
      ? { period: dto.current_fee.period, chip: studentFeeChip(dto.current_fee) }
      : null,
  }
}
