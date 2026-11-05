import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { MoneyFormatError } from '../../../core/money'
import {
  bangladeshToday,
  mapNotices,
  mapSeats,
  phoneProblem,
  removalRemedy,
  RosterShapeError,
  sameNameMatch,
  seatLine,
} from './mappers'

function row(patch: Partial<Schemas['RosterRowResponse']> = {}): Schemas['RosterRowResponse'] {
  return {
    enrollment_id: 'e1',
    display_name: 'তাসনিম জাহান',
    fee_amount: null,
    guardian_phone: '+8801911000003',
    guardian_state: 'accepted',
    inactive_from: null,
    is_removable: false,
    status: 'active',
    student_state: 'accepted',
    student_id: 's1',
    ...patch,
  }
}

const phone = (raw: string) => `P(${raw})`

describe('mapSeats', () => {
  it('maps a seat and joins its fee chip by enrollment id', () => {
    const [seat] = mapSeats([row()], {
      charged: '0.00',
      collected: '0.00',
      counts: { checking: 0, owed: 1, paid: 0 },
      period: '2026-11',
      seats: [
        {
          enrollment_id: 'e1',
          display_name: 'x',
          outstanding: '1200.00',
          current_status: 'unpaid',
          days_overdue: 5,
        },
      ],
    } as Schemas['BatchFeesResponse'])
    expect(seat).toMatchObject({ enrollmentId: 'e1', declined: false, isRemovable: false })
    expect(seat?.chip).toMatchObject({ kind: 'overdue', days: 5 })
  })

  it('shows no chip when fees did not load', () => {
    expect(mapSeats([row()], null)[0]?.chip).toBeNull()
  })

  it('marks a seat declined when either link declined', () => {
    expect(mapSeats([row({ guardian_state: 'declined' })], null)[0]?.declined).toBe(true)
    expect(mapSeats([row({ student_state: 'declined' })], null)[0]?.declined).toBe(true)
  })

  it.each([
    [{ status: 'archived' }],
    [{ student_state: 'maybe' }],
    [{ guardian_state: 'gone' }],
    [{ student_state: 'absent' }],
  ])('refuses a shape it cannot explain: %o', (patch) => {
    expect(() => mapSeats([row(patch)], null)).toThrow(RosterShapeError)
  })

  it('refuses a custom fee sent as a number', () => {
    expect(() => mapSeats([row({ fee_amount: 1000 as unknown as string })], null)).toThrow(
      MoneyFormatError,
    )
  })
})

describe('seatLine — StudentsTab.kt subline', () => {
  const [base] = mapSeats([row()], null)
  it('names the guardian', () => {
    expect(seatLine(base!, phone)).toEqual([['batch_guardian', 'P(+8801911000003)']])
  })
  it('leads with a custom fee and says who has not answered', () => {
    const [seat] = mapSeats([row({ fee_amount: '1000.00', student_state: 'pending' })], null)
    expect(seatLine(seat!, phone)).toEqual([
      ['batch_custom_fee', '৳1,000'],
      ['batch_guardian', 'P(+8801911000003)'],
      ['batch_not_answered'],
    ])
  })
  it('says when there is no guardian, or the guardian declined', () => {
    const [none] = mapSeats([row({ guardian_phone: null, guardian_state: 'absent' })], null)
    expect(seatLine(none!, phone)).toEqual([['batch_no_guardian']])
  })
  it('a declined seat says only that', () => {
    const [seat] = mapSeats([row({ student_state: 'declined' })], null)
    expect(seatLine(seat!, phone)).toEqual([['batch_declined_by_number']])
  })
  it('marks an inactive seat', () => {
    const [seat] = mapSeats([row({ status: 'inactive' })], null)
    expect(seatLine(seat!, phone).at(-1)).toEqual(['roster_status_inactive'])
  })
})

describe('removal refusals name their remedy', () => {
  it.each([
    ['ENROLLMENT_CLAIMED', 'mark-inactive'],
    ['ENROLLMENT_ERASED', 'none'],
    ['CONFLICT', null],
  ])('%s → %s', (code, remedy) => {
    expect(removalRemedy(code)).toBe(remedy)
  })
})

it('today is Bangladesh’s date, not the browser’s', () => {
  // 20:30 UTC on 4 Nov is 02:30 on 5 Nov in Dhaka.
  expect(bangladeshToday(new Date('2026-11-04T20:30:00Z'))).toBe('2026-11-05')
})

it('keeps the server’s notice order', () => {
  expect(
    mapNotices([
      { announcement_id: 'b', body: 'two', created_at: '2026-11-05T00:00:00Z', edited: true },
      { announcement_id: 'a', body: 'one', created_at: '2026-11-04T00:00:00Z', edited: false },
    ]).map((n) => [n.id, n.edited]),
  ).toEqual([
    ['b', true],
    ['a', false],
  ])
})

describe('form hints', () => {
  it('matches a name already in the batch, ignoring case and spaces', () => {
    expect(sameNameMatch('  rafsan ahmed ', ['Rafsan Ahmed', 'Tasnim'])).toBe('Rafsan Ahmed')
    expect(sameNameMatch('Rafsan', ['Rafsan Ahmed'])).toBeNull()
    expect(sameNameMatch('', ['x'])).toBeNull()
  })

  it.each([
    ['', true, null],
    ['01711234567', true, null],
    ['0181920773', false, ['phone_digit_count', 10]],
    ['০১৮১৯২০৭৭৩', false, ['phone_digit_count', 10]],
    ['12345', false, ['phone_invalid']],
  ])('phone %p → %p', (raw, valid, problem) => {
    expect(phoneProblem(raw, valid)).toEqual(problem)
  })
})
