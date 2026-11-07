/**
 * Roster and notice responses → what the students area draws. Pure, and
 * the test target, like `RosterStateMapper.kt`.
 *
 * Nothing here decides who may be removed or what "inactive" does: the
 * server sends `is_removable`, and refuses a removal with a code that
 * names the remedy. The client only words it.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money, toLatinDigits } from '../../../core/money'
import type { FeeChipModel } from '../../../ui/components'
import { feeChipFor } from '../mappers'

/** `unknown`: a state this client does not know yet (a newer server). */
export type LinkState = 'pending' | 'accepted' | 'declined' | 'absent' | 'unknown'
const LINK_STATES: readonly LinkState[] = ['pending', 'accepted', 'declined', 'absent']
const STATUSES = ['dormant', 'active', 'inactive'] as const
export type SeatStatus = (typeof STATUSES)[number] | 'unknown'

/** A response this client does not understand: shown as `error.unexpected`. */
export class RosterShapeError extends Error {
  override name = 'RosterShapeError'
}

export interface Seat {
  enrollmentId: string
  displayName: string
  guardianPhone: string | null
  /** A fee set for this student alone; null when the batch fee applies. */
  customFee: Money | null
  studentState: LinkState
  guardianState: LinkState
  status: SeatStatus
  /**
   * The date the teacher marked the seat inactive from, if any. Only
   * whether it is set is used: a seat nobody accepted stays `dormant` in
   * `status` even after it is marked, so this is what says "already done".
   */
  inactiveFrom: string | null
  isRemovable: boolean
  /** Either link declined: usually a mistyped number. */
  declined: boolean
  chip: FeeChipModel | null
}

function linkState(raw: string): LinkState {
  return (LINK_STATES as readonly string[]).includes(raw) ? (raw as LinkState) : 'unknown'
}

/**
 * Map the roster, joining each seat's fee chip by enrollment id.
 *
 * A seat status or link state this client does not know (a server newer
 * than this tab) maps to `unknown` and the row is drawn without that
 * phrase, rather than the whole roster failing. That guesses nothing that
 * matters: who may be removed is the server's `is_removable`, and every
 * action is checked again by the server. `unknown` is never read as
 * declined, pending or inactive.
 *
 * @throws RosterShapeError For a seat with no student link — a broken
 *   response rather than a newer one, so the screen says something went
 *   wrong rather than drawing a row it cannot explain
 */
export function mapSeats(
  rows: Schemas['RosterRowResponse'][],
  fees: Schemas['BatchFeesResponse'] | null,
): Seat[] {
  const byId = new Map((fees?.seats ?? []).map((s) => [s.enrollment_id, s]))
  return rows.map((r) => {
    const status: SeatStatus = (STATUSES as readonly string[]).includes(r.status)
      ? (r.status as SeatStatus)
      : 'unknown'
    const studentState = linkState(r.student_state)
    const guardianState = linkState(r.guardian_state)
    if (studentState === 'absent') throw new RosterShapeError('a seat with no student link')
    return {
      enrollmentId: r.enrollment_id,
      displayName: r.display_name,
      guardianPhone: r.guardian_phone ?? null,
      customFee: Money.fromWireOrNull(r.fee_amount),
      studentState,
      guardianState,
      status,
      inactiveFrom: r.inactive_from ?? null,
      isRemovable: r.is_removable,
      declined: studentState === 'declined' || guardianState === 'declined',
      chip: feeChipFor(byId.get(r.enrollment_id)),
    }
  })
}

/** One piece of a seat's second line: a string key and its arguments. */
export type Phrase = [key: string, ...args: (string | number)[]]

/**
 * The line under a student's name, as `StudentsTab.kt`'s `subline`:
 * a custom fee, the guardian (or that there is none, or that they
 * declined), and whether the student has answered.
 *
 * @param formatPhone Renders a phone number; injected so this stays pure
 */
export function seatLine(seat: Seat, formatPhone: (raw: string) => string): Phrase[] {
  if (seat.declined) return [['batch_declined_by_number']]
  const parts: Phrase[] = []
  if (seat.customFee) parts.push(['batch_custom_fee', seat.customFee.format()])
  if (seat.guardianPhone === null) parts.push(['batch_no_guardian'])
  else if (seat.guardianState === 'declined') parts.push(['batch_guardian_declined'])
  else parts.push(['batch_guardian', formatPhone(seat.guardianPhone)])
  if (seat.studentState === 'pending') parts.push(['batch_not_answered'])
  if (seat.status === 'inactive') parts.push(['roster_status_inactive'])
  return parts
}

/** What to offer when the server refuses a removal, by its error code. */
export type RemovalRemedy = 'mark-inactive' | 'none'

export function removalRemedy(code: string): RemovalRemedy | null {
  if (code === 'ENROLLMENT_CLAIMED') return 'mark-inactive'
  if (code === 'ENROLLMENT_ERASED') return 'none'
  return null
}

/**
 * Today in Bangladesh, as the server's calendar date (`YYYY-MM-DD`). Used
 * as the date a seat goes inactive, which is "from today" on Android too.
 */
export function bangladeshToday(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Dhaka',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now)
}

export interface Notice {
  id: string
  body: string
  postedAt: string
  edited: boolean
}

/** The server's order is kept: it decides which notice leads. */
export function mapNotices(rows: Schemas['AnnouncementResponse'][]): Notice[] {
  return rows.map((n) => ({
    id: n.announcement_id,
    body: n.body,
    postedAt: n.created_at,
    edited: n.edited,
  }))
}

/** "Rahim is already in this batch", matched as `SameNameHint` does. */
export function sameNameMatch(typed: string, existing: readonly string[]): string | null {
  const wanted = typed.trim().toLocaleLowerCase()
  if (!wanted) return null
  return existing.find((n) => n.trim().toLocaleLowerCase() === wanted) ?? null
}

/** Android's `phoneError`: a digit count when it is close, else the general rule. */
export function phoneProblem(raw: string, valid: boolean): Phrase | null {
  if (raw.trim() === '' || valid) return null
  const latin = toLatinDigits(raw).trim()
  const digits = latin.replace(/\D/g, '').length
  if (digits !== 11 && digits >= 1 && digits <= 13 && latin.startsWith('0')) {
    return ['phone_digit_count', digits]
  }
  return ['phone_invalid']
}
