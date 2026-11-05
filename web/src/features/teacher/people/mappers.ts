/**
 * Response-to-screen mapping for a teacher's students [0018]. Pure, so
 * each decision is tested without rendering.
 *
 * Decides nothing about the domain: which seats are active, which may be
 * deleted, and what is owed all come from the server unchanged [TC-9].
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'

export type LinkState = 'pending' | 'accepted' | 'declined' | 'absent'

export interface SeatLine {
  enrollmentId: string
  batchId: string
  batchName: string
  fee: Money | null
  outstanding: Money
  active: boolean
  removable: boolean
}

export interface Student {
  id: string
  name: string
  studentPhone: string | null
  guardianPhone: string | null
  studentState: LinkState
  guardianState: LinkState
  seats: SeatLine[]
  totalOutstanding: Money
  removable: boolean
}

const LINK_STATES: readonly LinkState[] = ['pending', 'accepted', 'declined', 'absent']

function linkState(raw: string): LinkState {
  return (LINK_STATES as readonly string[]).includes(raw) ? (raw as LinkState) : 'pending'
}

/** One student, with every amount decoded loudly from its wire string. */
export function mapStudent(dto: Schemas['StudentResponse']): Student {
  return {
    id: dto.student_id,
    name: dto.display_name,
    studentPhone: dto.student_phone ?? null,
    guardianPhone: dto.guardian_phone ?? null,
    studentState: linkState(dto.student_state),
    guardianState: linkState(dto.guardian_state),
    seats: dto.enrollments.map((seat) => ({
      enrollmentId: seat.enrollment_id,
      batchId: seat.batch_id,
      batchName: seat.batch_name,
      fee: Money.fromWireOrNull(seat.fee_amount ?? null),
      outstanding: Money.fromWire(seat.outstanding),
      active: seat.status === 'active',
      removable: seat.is_removable,
    })),
    totalOutstanding: Money.fromWire(dto.total_outstanding),
    removable: dto.is_removable,
  }
}

/** The batches a student is not in yet, to offer "Add to another batch". */
export function otherBatches<T extends { id: string }>(student: Student, batches: T[]): T[] {
  const seated = new Set(student.seats.map((s) => s.batchId))
  return batches.filter((b) => !seated.has(b.id))
}

/** The string key naming a link's state. */
export function linkKey(state: LinkState): string {
  switch (state) {
    case 'accepted':
      return 'student_link_accepted'
    case 'declined':
      return 'student_link_declined'
    case 'absent':
      return 'student_detail_no_guardian'
    case 'pending':
      return 'student_link_pending'
  }
}
