/**
 * Server responses → what the account screens draw. Pure, and the test
 * target, as `InboxMapper`, `ProfileStateMapper` and `DeletionState` are
 * on Android. Nothing here decides anything the server owns: an inbox
 * item's kind, read state and target seat all come from the server.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money, toLatinDigits } from '../../../core/money'
import { accountPaths, familyPaths, type Reader } from '../../family/reader'
import { paths } from '../../teacher/paths'
import type { Lens } from '../../../session/session'

// ------------------------------------------------------------------ inbox

export type InboxKind =
  | 'fee_reminder'
  | 'payment_approved'
  | 'payment_partial'
  | 'payment_rejected'
  | 'payment_recorded'
  | 'notice'
  | 'exam_scheduled'
  | 'exam_cancelled'
  | 'marks_available'
  | 'claim_to_verify'

const KINDS: readonly InboxKind[] = [
  'fee_reminder',
  'payment_approved',
  'payment_partial',
  'payment_rejected',
  'payment_recorded',
  'notice',
  'exam_scheduled',
  'exam_cancelled',
  'marks_available',
  'claim_to_verify',
]

function isKind(kind: string): kind is InboxKind {
  return (KINDS as readonly string[]).includes(kind)
}

export interface InboxMessage {
  id: string
  kind: InboxKind
  batchName: string
  childName: string | null
  amount: Money | null
  period: string | null
  sentAt: string
  unread: boolean
  enrollmentId: string | null
  sourceId: string | null
  preview: string | null
}

export interface InboxModel {
  messages: InboxMessage[]
  unread: number
}

/** A kind this client does not know is dropped, as `InboxMapper.toMessage` does. */
export function mapInbox(dto: Schemas['InboxResponse']): InboxModel {
  return {
    unread: dto.unread,
    messages: (dto.items ?? []).flatMap((i) =>
      isKind(i.kind)
        ? [
            {
              id: i.notification_id,
              kind: i.kind,
              batchName: i.batch_name,
              childName: i.child_name ?? null,
              amount: Money.fromWireOrNull(i.amount),
              period: i.period ?? null,
              sentAt: i.created_at,
              unread: !i.read,
              enrollmentId: i.enrollment_id ?? null,
              sourceId: i.source_id ?? null,
              preview: i.preview ?? null,
            },
          ]
        : [],
    ),
  }
}

/** The string key for a message's title, `{1}` being "child · batch". */
export const TITLE_KEY: Record<InboxKind, string> = {
  fee_reminder: 'inbox_fee_reminder_title',
  payment_approved: 'inbox_payment_approved_title',
  payment_partial: 'inbox_payment_partial_title',
  payment_rejected: 'inbox_payment_rejected_title',
  payment_recorded: 'inbox_payment_recorded_title',
  notice: 'inbox_notice_title',
  exam_scheduled: 'inbox_exam_scheduled_title',
  exam_cancelled: 'inbox_exam_cancelled_title',
  marks_available: 'inbox_marks_available_title',
  claim_to_verify: 'inbox_claim_to_verify_title',
}

/** "Child · Batch", or just the batch for the reader's own seat. */
export function inboxSubject(m: { childName: string | null; batchName: string }): string {
  return [m.childName, m.batchName].filter(Boolean).join(' · ')
}

type T = (key: string, ...args: (string | number)[]) => string

/**
 * The second line, as `InboxScreen.body` builds it: the server's preview
 * when it sent one, else the amount (and month) the server reported.
 */
export function inboxBody(
  m: InboxMessage,
  t: T,
  monthName: (period: string) => string,
): string | null {
  if (m.preview) return m.preview
  if (!m.amount) return null
  const money = m.amount.format()
  if (!m.period) {
    return m.kind === 'fee_reminder' ? t('inbox_fee_reminder_body_no_period', money) : null
  }
  const key =
    m.kind === 'payment_approved'
      ? 'inbox_payment_approved_body'
      : m.kind === 'payment_partial'
        ? 'inbox_payment_partial_body'
        : m.kind === 'payment_rejected'
          ? 'inbox_payment_rejected_body'
          : m.kind === 'payment_recorded'
            ? 'inbox_payment_recorded_body'
            : m.kind === 'claim_to_verify'
              ? 'inbox_claim_to_verify_body'
              : 'inbox_fee_reminder_body'
  return t(key, money, monthName(m.period))
}

/** Where opening a message goes, and under which lens that screen lives. */
export interface InboxTarget {
  to: string
  /** Null: every lens can open it. */
  lens: Lens | null
}

/**
 * `InboxMapper.targetOf`: marks → the marksheet, a fee reminder → that
 * seat's fees, a payment to check → that payment (or the queue);
 * everything else → this message's own page. A message about a child is
 * read through the guardian lens, one about the reader's own seat
 * through the student lens (Android: `guardian = childName != null`).
 */
export function targetOf(m: InboxMessage): InboxTarget {
  const reader: Reader = m.childName !== null ? 'child' : 'me'
  const readerLens: Lens = reader === 'child' ? 'guardian' : 'student'
  if (m.kind === 'marks_available' && m.enrollmentId && m.sourceId) {
    return { to: familyPaths.marksheet(reader, m.enrollmentId, m.sourceId), lens: readerLens }
  }
  if (m.kind === 'fee_reminder' && m.enrollmentId) {
    return { to: familyPaths.fees(reader, m.enrollmentId), lens: readerLens }
  }
  if (m.kind === 'claim_to_verify') {
    return { to: m.sourceId ? paths.payment(m.sourceId) : paths.verify(), lens: 'teacher' }
  }
  return { to: accountPaths.inboxItem(m.id), lens: null }
}

/**
 * Where to go from the lens being looked through now. A target behind a
 * different lens (a guardian's fee reminder read while looking as a
 * teacher) opens the message's own page instead, which every lens has,
 * rather than a screen the router would bounce home from.
 */
export function targetFor(m: InboxMessage, current: Lens | null): string {
  const target = targetOf(m)
  return target.lens === null || target.lens === current ? target.to : accountPaths.inboxItem(m.id)
}

export type InboxContent =
  | { kind: 'notice'; body: string; postedAt: string; editedAt: string | null }
  | {
      kind: 'exam'
      title: string
      date: string
      subjectName: string
      totalMarks: number
      topics: string[]
      /** The teacher called it off; its date no longer stands. */
      cancelled: boolean
    }
  | {
      kind: 'payment'
      period: string
      claimed: Money
      approved: Money | null
      outcome: 'approved' | 'partial' | 'pending' | 'rejected'
      reason: string | null
    }

export type InboxDetail =
  | { state: 'unavailable' }
  | {
      state: 'available'
      kind: InboxKind
      batchName: string
      childName: string | null
      unread: boolean
      content: InboxContent | null
    }

/** `InboxMapper.afterDetail`: gone, or of an unknown kind → unavailable. */
export function mapDetail(dto: Schemas['NotificationDetailResponse']): InboxDetail {
  if (!dto.available || !isKind(dto.kind)) return { state: 'unavailable' }
  let content: InboxContent | null = null
  if (dto.notice) {
    content = {
      kind: 'notice',
      body: dto.notice.body,
      postedAt: dto.notice.posted_at,
      editedAt: dto.notice.edited_at ?? null,
    }
  } else if (dto.exam) {
    content = {
      kind: 'exam',
      title: dto.exam.title,
      date: dto.exam.date,
      subjectName: dto.exam.subject_name,
      totalMarks: dto.exam.total_marks,
      topics: (dto.exam.topics as unknown[]).map(String),
      cancelled: dto.exam.cancelled ?? false,
    }
  } else if (dto.payment) {
    content = {
      kind: 'payment',
      period: dto.payment.period,
      claimed: Money.fromWire(dto.payment.claimed),
      approved: Money.fromWireOrNull(dto.payment.approved),
      outcome: dto.payment.outcome,
      reason: dto.payment.reason ?? null,
    }
  }
  return {
    state: 'available',
    kind: dto.kind,
    batchName: dto.batch_name,
    childName: dto.child_name ?? null,
    unread: !dto.read,
    content,
  }
}

export const OUTCOME_KEY: Record<'approved' | 'partial' | 'pending' | 'rejected', string> = {
  approved: 'inbox_outcome_approved',
  partial: 'inbox_outcome_partial',
  pending: 'inbox_outcome_pending',
  rejected: 'inbox_outcome_rejected',
}

// ---------------------------------------------------------------- profile

export interface PostalAddress {
  house: string
  road: string
  city: string
  postcode: string
}

export function postalOf(me: Schemas['MeResponse']): PostalAddress {
  return {
    house: me.address_house ?? '',
    road: me.address_road ?? '',
    city: me.address_city ?? '',
    postcode: me.address_postcode ?? '',
  }
}

/** Four Latin digits once Bangla digits are mapped. Format only. */
export function postcodeIsValid(raw: string): boolean {
  return /^[0-9]{4}$/.test(toLatinDigits(raw.trim()))
}

/** `PostalAddress.isComplete`: Save is offered only for a whole address. */
export function isComplete(a: PostalAddress): boolean {
  return (
    a.house.trim() !== '' &&
    a.road.trim() !== '' &&
    a.city.trim() !== '' &&
    postcodeIsValid(a.postcode)
  )
}

/** `MeDto.shownAddress`: the four parts on one line, else the legacy one-line address. */
export function shownAddress(me: Schemas['MeResponse']): string | null {
  const a = postalOf(me)
  const place = [a.city.trim(), toLatinDigits(a.postcode.trim())].filter(Boolean).join(' ')
  const line = [a.house.trim(), a.road.trim(), place].filter(Boolean).join(', ')
  return line || me.address || null
}

/**
 * The PATCH body, as `ProfileViewModel.save` and `HttpProfileRepository`
 * build it: a blank name is sent as null (left as it is), and the address
 * only when it is complete.
 */
export function profileUpdate(
  selfName: string,
  address: PostalAddress,
): Schemas['ProfileUpdateRequest'] {
  const complete = isComplete(address)
  return {
    self_name: selfName.trim() || null,
    address_house: complete ? address.house.trim() : null,
    address_road: complete ? address.road.trim() : null,
    address_city: complete ? address.city.trim() : null,
    address_postcode: complete ? toLatinDigits(address.postcode.trim()) : null,
  }
}

// --------------------------------------------------------------- deletion

const LOCAL_NUMBER_DIGITS = 11

/**
 * `numberMatches` from `DeletionState.kt`: at least the full local number,
 * and the END of the stored one. `01611477203` and `8801611477203` both
 * match `+8801611477203`; a short tail like `477203` does not.
 */
export function numberMatches(typed: string, phone: string | null | undefined): boolean {
  if (!phone) return false
  const mine = toLatinDigits(phone).replace(/\D/g, '')
  const theirs = toLatinDigits(typed).replace(/\D/g, '')
  return theirs.length >= LOCAL_NUMBER_DIGITS && mine.endsWith(theirs)
}

/**
 * The confirmation for an email-only account, which has no number to
 * type: the whole address, ignoring case and surrounding spaces.
 */
export function emailMatches(typed: string, email: string | null | undefined): boolean {
  if (!email) return false
  return typed.trim().toLowerCase() === email.trim().toLowerCase()
}

export interface TeacherFootprint {
  batchCount: number
  studentCount: number
  outstanding: Money
}

/** A teacher's footprint, only when they own batches (`takeIf { it.batchCount > 0 }`). */
export function footprintOf(dto: Schemas['DeletionSummaryResponse']): TeacherFootprint | null {
  return dto.batch_count > 0
    ? {
        batchCount: dto.batch_count,
        studentCount: dto.student_count,
        outstanding: Money.fromWire(dto.outstanding),
      }
    : null
}

// --------------------------------------------------------------- children

export interface ChildRow {
  key: string
  name: string
  batchCount: number
  batches: { enrollmentId: string; batchName: string; teacherName: string | null }[]
}

/** The guardian home's children, grouped by the server (its `key`), not here. */
export function mapChildren(dto: Schemas['GuardianHomeResponse']): ChildRow[] {
  return (dto.children ?? []).map((c) => ({
    key: c.key,
    name: c.display_name,
    batchCount: c.batch_count,
    batches: (c.batches ?? []).map((b) => ({
      enrollmentId: b.enrollment_id,
      batchName: b.batch_name,
      teacherName: b.teacher_display_name ?? null,
    })),
  }))
}
