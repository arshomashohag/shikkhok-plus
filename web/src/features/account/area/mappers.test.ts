import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { MoneyFormatError } from '../../../core/money'
import {
  footprintOf,
  inboxBody,
  inboxSubject,
  isComplete,
  mapChildren,
  mapDetail,
  mapInbox,
  numberMatches,
  profileUpdate,
  shownAddress,
  targetFor,
  targetOf,
  type InboxMessage,
} from './mappers'

const t = (key: string, ...args: (string | number)[]) => `${key}(${args.join(',')})`

function item(patch: Partial<Schemas['NotificationResponse']>): Schemas['NotificationResponse'] {
  return {
    notification_id: 'n1',
    kind: 'fee_reminder',
    batch_name: 'Physics · Batch A',
    child_name: null,
    amount: '1200.00',
    period: '2026-10',
    created_at: '2026-11-05T03:00:00Z',
    read: false,
    enrollment_id: 'seat1',
    source_id: null,
    preview: null,
    ...patch,
  }
}

const one = (patch: Partial<Schemas['NotificationResponse']>): InboxMessage => {
  const [m] = mapInbox({ unread: 1, items: [item(patch)] }).messages
  if (!m) throw new Error('dropped')
  return m
}

describe('mapInbox', () => {
  it('keeps the server’s unread count and read state', () => {
    const model = mapInbox({
      unread: 3,
      items: [item({}), item({ notification_id: 'n2', read: true })],
    })
    expect(model.unread).toBe(3)
    expect(model.messages.map((m) => m.unread)).toEqual([true, false])
  })

  it('drops a kind this client does not know, as InboxMapper does', () => {
    const model = mapInbox({
      unread: 1,
      items: [item({ kind: 'something_new' as Schemas['NotificationResponse']['kind'] })],
    })
    expect(model.messages).toEqual([])
  })

  it('keeps the two kinds added for recorded payments and cancelled exams', () => {
    const model = mapInbox({
      unread: 2,
      items: [
        item({ kind: 'payment_recorded' }),
        item({
          notification_id: 'n2',
          kind: 'exam_cancelled',
          amount: null,
          period: null,
          preview: 'Monthly · 2026-11-20',
        }),
      ],
    })
    expect(model.messages.map((m) => m.kind)).toEqual(['payment_recorded', 'exam_cancelled'])
    expect(inboxBody(model.messages[1] as InboxMessage, t, (p) => p)).toBe('Monthly · 2026-11-20')
  })

  it('refuses a number where money belongs', () => {
    expect(() =>
      mapInbox({ unread: 0, items: [item({ amount: 1200 as unknown as string })] }),
    ).toThrow(MoneyFormatError)
  })
})

describe('inbox wording', () => {
  it('titles a guardian’s message with the child, then the batch', () => {
    expect(inboxSubject({ childName: 'Tasnim', batchName: 'Batch A' })).toBe('Tasnim · Batch A')
    expect(inboxSubject({ childName: null, batchName: 'Batch A' })).toBe('Batch A')
  })

  it('prefers the server’s preview', () => {
    expect(inboxBody(one({ preview: 'Bring the worksheet' }), t, (p) => p)).toBe(
      'Bring the worksheet',
    )
  })

  it.each([
    ['fee_reminder', 'inbox_fee_reminder_body(৳1,200,2026-10)'],
    ['payment_approved', 'inbox_payment_approved_body(৳1,200,2026-10)'],
    ['payment_partial', 'inbox_payment_partial_body(৳1,200,2026-10)'],
    ['payment_rejected', 'inbox_payment_rejected_body(৳1,200,2026-10)'],
    ['payment_recorded', 'inbox_payment_recorded_body(৳1,200,2026-10)'],
    ['claim_to_verify', 'inbox_claim_to_verify_body(৳1,200,2026-10)'],
  ] as const)('words a %s from the amount and month the server sent', (kind, line) => {
    expect(inboxBody(one({ kind }), t, (p) => p)).toBe(line)
  })

  it('a fee reminder without a month still says the amount; others say nothing', () => {
    expect(inboxBody(one({ period: null }), t, (p) => p)).toBe(
      'inbox_fee_reminder_body_no_period(৳1,200)',
    )
    expect(inboxBody(one({ kind: 'payment_approved', period: null }), t, (p) => p)).toBeNull()
    expect(inboxBody(one({ kind: 'notice', amount: null }), t, (p) => p)).toBeNull()
  })
})

describe('targetOf — InboxMapper.targetOf', () => {
  it('marks open the marksheet, for the reader the message is about', () => {
    expect(targetOf(one({ kind: 'marks_available', source_id: 'exam1' }))).toEqual({
      to: '/my/seat1/exams/exam1/marksheet',
      lens: 'student',
    })
    expect(
      targetOf(one({ kind: 'marks_available', source_id: 'exam1', child_name: 'Ayan' })),
    ).toEqual({
      to: '/child/seat1/exams/exam1/marksheet',
      lens: 'guardian',
    })
  })

  it('a fee reminder opens that seat’s fees', () => {
    expect(targetOf(one({ child_name: 'Ayan' }))).toEqual({
      to: '/child/seat1/fees',
      lens: 'guardian',
    })
  })

  it('a payment to check opens that payment, or the queue without one', () => {
    expect(targetOf(one({ kind: 'claim_to_verify', source_id: 'sub1' }))).toEqual({
      to: '/verify/sub1',
      lens: 'teacher',
    })
    expect(targetOf(one({ kind: 'claim_to_verify' }))).toEqual({ to: '/verify', lens: 'teacher' })
  })

  it.each([
    'notice',
    'exam_scheduled',
    'payment_approved',
    'payment_partial',
    'payment_rejected',
  ] as const)('a %s opens its own page', (kind) => {
    expect(targetOf(one({ kind }))).toEqual({ to: '/inbox/n1', lens: null })
  })

  it('marks with no seat or exam fall back to the message itself', () => {
    expect(targetOf(one({ kind: 'marks_available', source_id: null }))).toEqual({
      to: '/inbox/n1',
      lens: null,
    })
  })

  it('a target behind another lens opens the message instead of bouncing home', () => {
    const reminder = one({ child_name: 'Ayan' })
    expect(targetFor(reminder, 'guardian')).toBe('/child/seat1/fees')
    expect(targetFor(reminder, 'teacher')).toBe('/inbox/n1')
    expect(targetFor(one({ kind: 'notice' }), 'teacher')).toBe('/inbox/n1')
  })
})

describe('mapDetail', () => {
  const base: Schemas['NotificationDetailResponse'] = {
    notification_id: 'n1',
    kind: 'payment_partial',
    available: true,
    batch_name: 'Batch A',
    child_name: null,
    created_at: '2026-11-05T03:00:00Z',
    read: false,
    payment: {
      claim_id: 'c1',
      period: '2026-10',
      claimed: '1200.00',
      approved: '800.00',
      outcome: 'partial',
      reason: null,
    },
  }

  it('an unavailable item, or an unknown kind, is unavailable', () => {
    expect(mapDetail({ ...base, available: false })).toEqual({ state: 'unavailable' })
    expect(
      mapDetail({ ...base, kind: 'new_kind' as Schemas['NotificationDetailResponse']['kind'] }),
    ).toEqual({ state: 'unavailable' })
  })

  it('maps a payment block with its money as Money', () => {
    const d = mapDetail(base)
    expect(
      d.state === 'available' && d.content?.kind === 'payment' && d.content.approved?.format(),
    ).toBe('৳800')
  })

  it('maps a notice and an exam', () => {
    const notice = mapDetail({
      ...base,
      kind: 'notice',
      payment: null,
      notice: { body: 'Hello', posted_at: '2026-11-04T10:00:00Z', edited_at: null },
    })
    expect(notice).toMatchObject({ state: 'available', content: { kind: 'notice', body: 'Hello' } })
    const exam = mapDetail({
      ...base,
      kind: 'exam_scheduled',
      payment: null,
      exam: {
        exam_id: 'e1',
        title: 'Monthly',
        date: '2026-11-20',
        subject_name: 'Physics',
        total_marks: 50,
        topics: ['Heat', 'Light'],
        cancelled: false,
      },
    })
    expect(exam).toMatchObject({
      content: { kind: 'exam', totalMarks: 50, topics: ['Heat', 'Light'], cancelled: false },
    })
    const cancelled = mapDetail({
      ...base,
      kind: 'exam_cancelled',
      payment: null,
      exam: {
        exam_id: 'e1',
        title: 'Monthly',
        date: '2026-11-20',
        subject_name: 'Physics',
        total_marks: 50,
        topics: [],
        cancelled: true,
      },
    })
    expect(cancelled).toMatchObject({
      state: 'available',
      kind: 'exam_cancelled',
      content: { kind: 'exam', cancelled: true },
    })
  })
})

describe('profile', () => {
  const me: Schemas['MeResponse'] = {
    self_name: 'Rokeya',
    phone: '+8801911000003',
    address_house: '12',
    address_road: 'Road 5',
    address_city: 'Dhaka',
    address_postcode: '1205',
    lenses: [],
  }

  it('shows the four parts on one line, else the legacy address', () => {
    expect(shownAddress(me)).toBe('12, Road 5, Dhaka 1205')
    expect(
      shownAddress({
        ...me,
        address_house: null,
        address_road: null,
        address_city: null,
        address_postcode: null,
        address: 'Old one-line address',
      }),
    ).toBe('Old one-line address')
  })

  it('a complete address needs every part and a 4-digit postcode, Bangla digits allowed', () => {
    expect(isComplete({ house: '12', road: 'R', city: 'D', postcode: '১২০৫' })).toBe(true)
    expect(isComplete({ house: '12', road: 'R', city: 'D', postcode: '120' })).toBe(false)
    expect(isComplete({ house: ' ', road: 'R', city: 'D', postcode: '1205' })).toBe(false)
  })

  it('sends a blank name as null, and the address only when complete', () => {
    expect(profileUpdate('  ', { house: ' 12 ', road: 'R', city: 'D', postcode: '১২০৫' })).toEqual({
      self_name: null,
      address_house: '12',
      address_road: 'R',
      address_city: 'D',
      address_postcode: '1205',
    })
    expect(profileUpdate('Rokeya', { house: '12', road: '', city: 'D', postcode: '1205' })).toEqual(
      {
        self_name: 'Rokeya',
        address_house: null,
        address_road: null,
        address_city: null,
        address_postcode: null,
      },
    )
  })
})

describe('deletion', () => {
  it.each([
    ['01911000003', true],
    ['01911-000003', true],
    ['8801911000003', true],
    ['+880 1911 000003', true],
    ['০১৯১১০০০০০৩', true],
    ['000003', false],
    ['1911000003', false],
    ['01911000004', false],
    ['', false],
  ])('number %p matches the account: %p', (typed, expected) => {
    expect(numberMatches(typed, '+8801911000003')).toBe(expected)
  })

  it('nothing matches an account with no number', () => {
    expect(numberMatches('01911000003', null)).toBe(false)
  })

  it('a teacher footprint exists only for someone who owns batches', () => {
    expect(footprintOf({ batch_count: 0, student_count: 0, outstanding: '0.00' })).toBeNull()
    const f = footprintOf({ batch_count: 2, student_count: 7, outstanding: '37200.00' })
    expect(f?.batchCount).toBe(2)
    expect(f?.outstanding.format()).toBe('৳37,200')
  })
})

it('keeps the server’s grouping of children', () => {
  const rows = mapChildren({
    children: [
      {
        key: 'k1',
        display_name: 'Tasnim',
        batch_count: 2,
        batches: [
          {
            enrollment_id: 'e1',
            batch_name: 'A',
            teacher_display_name: 'Mahfuz',
            next_session: null,
          },
          { enrollment_id: 'e2', batch_name: 'B', teacher_display_name: null, next_session: null },
        ],
      },
    ],
  } as Schemas['GuardianHomeResponse'])
  expect(rows).toEqual([
    {
      key: 'k1',
      name: 'Tasnim',
      batchCount: 2,
      batches: [
        { enrollmentId: 'e1', batchName: 'A', teacherName: 'Mahfuz' },
        { enrollmentId: 'e2', batchName: 'B', teacherName: null },
      ],
    },
  ])
})
