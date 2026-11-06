/** The timetable's helpers: weeks, grouping, pickable people and rooms, clashes. */
import { describe, expect, it } from 'vitest'
import { ApiError } from '../../../api/errors'
import {
  assignable,
  byDay,
  clashOf,
  liveRooms,
  shiftWeek,
  swapCandidates,
  weekFrom,
  type TimetableClass,
} from './timetable'

const cls = (patch: Partial<TimetableClass>): TimetableClass => ({
  session_id: 's1',
  batch_id: 'b1',
  batch_name: 'Class 9',
  date: '2026-11-09',
  start_time: '16:00',
  status: 'scheduled',
  overridden: false,
  ...patch,
})

describe('weeks', () => {
  it('lists seven days across a month and moves by whole weeks', () => {
    expect(weekFrom('2026-11-28')).toEqual([
      '2026-11-28',
      '2026-11-29',
      '2026-11-30',
      '2026-12-01',
      '2026-12-02',
      '2026-12-03',
      '2026-12-04',
    ])
    expect(shiftWeek('2026-12-29', 1)).toBe('2027-01-05')
    expect(shiftWeek('2026-11-03', -1)).toBe('2026-10-27')
  })
})

describe('byDay', () => {
  it('keeps every day, empty ones included, in order', () => {
    const grouped = byDay(['2026-11-09', '2026-11-10'], [cls({})])
    expect(grouped.map(([day, list]) => [day, list.length])).toEqual([
      ['2026-11-09', 1],
      ['2026-11-10', 0],
    ])
  })
})

describe('pickers', () => {
  it('offers live, undeclined members and rooms still in use', () => {
    const member = (patch: object) =>
      ({
        member_id: 'm',
        display_name: 'X',
        phone: '+8801711111111',
        role: 'teacher',
        decision: 'accepted',
        invited_at: '',
        revoked: false,
        is_you: false,
        ...patch,
      }) as never
    expect(
      assignable([
        member({ member_id: 'a' }),
        member({ member_id: 'p', decision: 'pending' }),
        member({ member_id: 'd', decision: 'declined' }),
        member({ member_id: 'r', revoked: true }),
      ]).map((m) => m.member_id),
    ).toEqual(['a', 'p'])
    expect(
      liveRooms([
        { room_id: '1', name: 'A', archived: false },
        { room_id: '2', name: 'B', archived: true },
      ]).map((r) => r.room_id),
    ).toEqual(['1'])
  })

  it('offers same-day, uncancelled classes to swap with, never the class itself', () => {
    const target = cls({ session_id: 'a' })
    const all = [
      target,
      cls({ session_id: 'b' }),
      cls({ session_id: 'c', status: 'cancelled' }),
      cls({ session_id: 'd', date: '2026-11-10' }),
    ]
    expect(swapCandidates(target, all).map((c) => c.session_id)).toEqual(['b'])
  })
})

describe('clashOf', () => {
  it('reads the named class from a clash, and nothing from other errors', () => {
    const clash = new ApiError(409, 'CLASS_CLASH', 'schedule.clash', false, {
      batch: 'Class 10',
      start_time: '16:30',
      with: 'teacher',
    })
    expect(clashOf(clash)).toEqual({ batch: 'Class 10', time: '16:30' })
    expect(clashOf(new ApiError(409, 'CLASS_CLASH', 'schedule.clash', false))).toBeNull()
    expect(clashOf(new Error('x'))).toBeNull()
  })
})
