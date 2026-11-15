/**
 * Response-to-screen mapping for a teacher's students [0018]. Pure, so
 * each decision is tested without rendering.
 *
 * Decides nothing about the domain: which seats are active, which may be
 * deleted, and what is owed all come from the server unchanged [TC-9].
 */
import type { Schemas } from '../../../api/endpoints'
import { formatPhone, normalisePhone } from '../../../core/format'
import { Money } from '../../../core/money'
import { readIdentifier } from '../../auth/identifier'

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
  /** Recorded by the teacher; someone else's address [FR6.1]. */
  studentEmail: string | null
  guardianEmail: string | null
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
    studentEmail: dto.student_email ?? null,
    guardianEmail: dto.guardian_email ?? null,
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

/** A contact for a cell: the formatted phone, else the email, else null. */
function phoneElseEmail(phone: string | null, email: string | null): string | null {
  if (phone) return formatPhone(phone)
  return email
}

/**
 * The student's contact, for the detail header and the list cell: the
 * phone, else the email [functional-spec W7 step 7].
 */
export function studentContactLine(
  s: Pick<Student, 'studentPhone' | 'studentEmail'>,
): string | null {
  return phoneElseEmail(s.studentPhone, s.studentEmail)
}

/**
 * The guardian's contacts for the detail screen's guardian line: the
 * phone, then the email; both when both are recorded.
 */
export function guardianContactLine(
  s: Pick<Student, 'guardianPhone' | 'guardianEmail'>,
): string | null {
  const parts = [s.guardianPhone ? formatPhone(s.guardianPhone) : null, s.guardianEmail].filter(
    (p): p is string => Boolean(p),
  )
  return parts.length > 0 ? parts.join(' · ') : null
}

/** The guardian's contact for a list cell, one value: the phone, else the email. */
export function guardianCellLine(
  s: Pick<Student, 'guardianPhone' | 'guardianEmail'>,
): string | null {
  return phoneElseEmail(s.guardianPhone, s.guardianEmail)
}

/** What the Edit sheet holds, as stored or as typed. */
export interface StudentFields {
  name: string
  studentPhone: string
  guardianPhone: string
  studentEmail: string
  guardianEmail: string
}

/** The stored record as the Edit sheet pre-fills it. */
export function editFields(s: Student): StudentFields {
  return {
    name: s.name,
    studentPhone: s.studentPhone ? formatPhone(s.studentPhone) : '',
    guardianPhone: s.guardianPhone ? formatPhone(s.guardianPhone) : '',
    studentEmail: s.studentEmail ?? '',
    guardianEmail: s.guardianEmail ?? '',
  }
}

/** A phone as compared and sent, or '' for blank; null when malformed. */
function phoneValue(raw: string): string | null {
  if (!raw.trim()) return ''
  return normalisePhone(raw)
}

/**
 * A typed email as compared and sent: '' for blank (absent), null when
 * the shared email check refuses it [NFR3.12].
 */
export function typedEmail(raw: string): string | null {
  if (!raw.trim()) return ''
  const read = readIdentifier('email', raw)
  return read && 'email' in read ? read.email : null
}

/** Which typed contact fields are malformed; blank is never malformed. */
export function editProblems(typed: StudentFields): Partial<Record<keyof StudentFields, true>> {
  const problems: Partial<Record<keyof StudentFields, true>> = {}
  if (phoneValue(typed.studentPhone) === null) problems.studentPhone = true
  if (phoneValue(typed.guardianPhone) === null) problems.guardianPhone = true
  if (typedEmail(typed.studentEmail) === null) problems.studentEmail = true
  if (typedEmail(typed.guardianEmail) === null) problems.guardianEmail = true
  return problems
}

/**
 * The patch for the Edit sheet, or null when nothing changed
 * [functional-spec W7 step 5] [review R-04]. Pure.
 *
 * Unchanged fields are omitted; a changed value is sent; an emptied
 * contact — phone or email — is sent as an explicit `null`, which
 * `StudentUpdateRequest` documents as "clear it". The server refuses
 * clearing one that was accepted or erased. Expects well-formed input
 * (see {@link editProblems}).
 */
export function studentEdit(
  original: StudentFields,
  typed: StudentFields,
): Schemas['StudentUpdateRequest'] | null {
  const patch: Schemas['StudentUpdateRequest'] = {}
  const name = typed.name.trim()
  if (name && name !== original.name.trim()) patch.display_name = name

  const contact = (
    key: 'student_phone' | 'guardian_phone' | 'student_email' | 'guardian_email',
    was: string | null,
    now: string | null,
  ) => {
    if (now === null || was === now) return
    patch[key] = now === '' ? null : now
  }
  contact('student_phone', phoneValue(original.studentPhone), phoneValue(typed.studentPhone))
  contact('guardian_phone', phoneValue(original.guardianPhone), phoneValue(typed.guardianPhone))
  contact('student_email', typedEmail(original.studentEmail), typedEmail(typed.studentEmail))
  contact('guardian_email', typedEmail(original.guardianEmail), typedEmail(typed.guardianEmail))
  return Object.keys(patch).length > 0 ? patch : null
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
