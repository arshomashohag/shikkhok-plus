import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'
import { changes, splitSubjects, valuesOf } from './EditBatchScreen'
import {
  classTarget,
  draftFromSlots,
  lastTopic,
  mapMonth,
  mapSeats,
  monthGrid,
  parseConflictState,
  shiftMonth,
  slotsFromDraft,
} from './mappers'

const cls = (
  patch: Partial<Schemas['CalendarClassResponse']> = {},
): Schemas['CalendarClassResponse'] => ({
  session_id: 's1',
  date: '2026-11-05',
  start_time: '16:00:00',
  end_time: '17:30:00',
  subject_name: null,
  state: 'today',
  topic: null,
  notes: null,
  plannable: true,
  recordable: false,
  topic_version: 0,
  attendance_version: 0,
  mark: null,
  ...patch,
})

describe('mapMonth', () => {
  it('keeps the server’s states and range, and drops states it does not know', () => {
    const model = mapMonth({
      year: 2026,
      month: 11,
      first_month: '2026-11',
      last_month: '2026-12',
      served_at: '2026-11-05T10:00:00+06:00',
      today: '2026-11-05',
      days: [
        { date: '2026-11-05', state: 'today', classes: [cls()] },
        { date: '2026-11-06', state: 'something_new' as 'today', classes: [] },
        {
          date: '2026-11-07',
          state: 'upcoming',
          classes: [cls({ state: 'odd' as 'today' }), cls({ session_id: 's2', state: 'upcoming' })],
        },
      ],
    })
    expect(model.first).toEqual({ year: 2026, month: 11 })
    expect(model.last).toEqual({ year: 2026, month: 12 })
    expect([...model.days.keys()]).toEqual(['2026-11-05', '2026-11-07'])
    expect(model.days.get('2026-11-07')?.classes.map((c) => c.sessionId)).toEqual(['s2'])
  })
})

describe('classTarget — ClassTapRouter.forClass', () => {
  it.each([
    [{ recordable: true, plannable: true }, 'record'],
    [{ recordable: false, plannable: true }, 'plan'],
    [{ recordable: false, plannable: false }, 'read'],
  ] as const)('%o opens %s', (flags, target) => {
    expect(classTarget(flags)).toBe(target)
  })
})

describe('calendar layout', () => {
  it('lays out a month Sunday first', () => {
    // 1 November 2026 is a Sunday; 1 October 2026 a Thursday.
    expect(monthGrid({ year: 2026, month: 11 })[0]).toEqual([1, 2, 3, 4, 5, 6, 7])
    const oct = monthGrid({ year: 2026, month: 10 })
    expect(oct[0]).toEqual([null, null, null, null, 1, 2, 3])
    expect(oct.at(-1)).toEqual([25, 26, 27, 28, 29, 30, 31])
  })

  it('handles February in a leap year and pads the last week', () => {
    const feb = monthGrid({ year: 2028, month: 2 })
    expect(feb.flat().filter((n) => n !== null)).toHaveLength(29)
    expect(feb.every((w) => w.length === 7)).toBe(true)
  })

  it('moves across year ends', () => {
    expect(shiftMonth({ year: 2026, month: 12 }, 1)).toEqual({ year: 2027, month: 1 })
    expect(shiftMonth({ year: 2026, month: 1 }, -1)).toEqual({ year: 2025, month: 12 })
  })
})

describe('lastTopic — the "Continue" suggestion', () => {
  const s = (patch: Partial<Schemas['SessionResponse']>): Schemas['SessionResponse'] => ({
    session_id: 'x',
    date: '2026-11-01',
    start_time: '16:00:00',
    status: 'held',
    origin: 'recurrence',
    topic: 'Newton',
    topic_logged: true,
    topic_version: 1,
    attendance_version: 0,
    ...patch,
  })

  it('takes the latest logged topic of another class', () => {
    expect(
      lastTopic(
        [
          s({ session_id: 'a', date: '2026-11-01', topic: 'old' }),
          s({ session_id: 'b', date: '2026-11-03', topic: 'newest' }),
          s({ session_id: 'c', date: '2026-11-04', topic: 'unlogged', topic_logged: false }),
          s({ session_id: 'me', date: '2026-11-05', topic: 'this one' }),
          s({ session_id: 'd', date: '2026-11-04', topic: '   ' }),
        ],
        'me',
      ),
    ).toBe('newest')
  })

  it('offers nothing for a first class', () => {
    expect(lastTopic([], 'me')).toBeNull()
  })
})

describe('attendance', () => {
  it('starts an unmarked seat present, as Android does', () => {
    expect(
      mapSeats({
        attendance_version: 0,
        writable: true,
        seats: [
          { enrollment_id: 'e1', display_name: 'A', present: null },
          { enrollment_id: 'e2', display_name: 'B', present: false },
        ],
      }).map((x) => x.present),
    ).toEqual([true, false])
  })

  it('reads the record a conflict reports', () => {
    const state = parseConflictState('e1:present,e2:absent,bad,e3:maybe')
    expect([...state.entries()]).toEqual([
      ['e1', true],
      ['e2', false],
    ])
    expect(parseConflictState(undefined).size).toBe(0)
  })
})

describe('schedule', () => {
  it('reads one range for every day from the first slot, and writes it back', () => {
    const draft = draftFromSlots([
      { weekday: 5, start_time: '16:00:00', end_time: '17:30:00' },
      { weekday: 0, start_time: '16:00:00', end_time: '17:30:00' },
    ])
    expect(draft).toEqual({ days: [5, 0], start: '16:00', end: '17:30' })
    expect(slotsFromDraft(draft)).toEqual([
      { weekday: 0, start_time: '16:00', end_time: '17:30' },
      { weekday: 5, start_time: '16:00', end_time: '17:30' },
    ])
    expect(draftFromSlots([]).days).toEqual([])
  })
})

describe('edit batch', () => {
  const batch = {
    id: 'b1',
    name: 'Physics · Batch A',
    subjects: ['Physics'],
    default_fee: '1200.00',
    fee_due_day: 10,
  } as Schemas['BatchResponse']

  it('prefills from the batch without a float', () => {
    expect(valuesOf(batch)).toEqual({
      name: 'Physics · Batch A',
      subjects: 'Physics',
      fee: '1,200',
      dueDay: '10',
    })
  })

  it('sends only what changed', () => {
    expect(
      changes(batch, {
        name: 'Physics · Batch A',
        subjects: ['Physics'],
        fee: Money.fromTyped('1,200'),
        dueDay: 10,
      }),
    ).toBeNull()
    expect(
      changes(batch, {
        name: 'Physics · A',
        subjects: ['Physics', 'Maths'],
        fee: Money.fromTyped('1500'),
        dueDay: null,
      }),
    ).toEqual({
      name: 'Physics · A',
      subjects: ['Physics', 'Maths'],
      default_fee: '1500.00',
      fee_due_day: null,
    })
  })

  it('splits subjects on Latin and Bangla commas', () => {
    expect(splitSubjects('গণিত، Physics , ,Chemistry')).toEqual(['গণিত', 'Physics', 'Chemistry'])
  })
})
