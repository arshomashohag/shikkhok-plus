import { describe, expect, it } from 'vitest'
import {
  formatClock,
  formatMark,
  formatPhone,
  howSoon,
  initial,
  normalisePhone,
  whenLabel,
} from './format'

const t = (key: string, ...args: (string | number)[]) => `${key}(${args.join(',')})`

describe('phones', () => {
  it.each([
    ['01711234567', '01711-234567'],
    ['+8801711234567', '01711-234567'],
    ['8801711234567', '01711-234567'],
    ['০১৭১১২৩৪৫৬৭', '01711-234567'],
    ['12345', '12345'],
  ])('formats %s as %s', (raw, shown) => {
    expect(formatPhone(raw)).toBe(shown)
  })

  it.each([
    ['01711234567', '01711234567'],
    ['01711-234567', '01711234567'],
    ['+880 1711 234567', '01711234567'],
    ['০১৭১১২৩৪৫৬৭', '01711234567'],
    ['0171123456', null],
    ['02711234567', null],
    ['', null],
  ])('normalises %p to %p (format only)', (typed, expected) => {
    expect(normalisePhone(typed)).toBe(expected)
  })
})

describe('times', () => {
  it('splits a wall clock with Western digits in both languages', () => {
    expect(formatClock('16:00:00', 'en')).toBe('4:00 pm')
    expect(formatClock('00:30', 'en')).toBe('12:30 am')
    expect(formatClock('12:05', 'en')).toBe('12:05 pm')
    expect(formatClock('16:00', 'bn')).toBe('4:00 pm')
  })

  it('says "today" only when the server sent a countdown', () => {
    expect(
      whenLabel({ date: '2026-11-05', startTime: '16:00', startsInMinutes: 35 }, 'en', t),
    ).toBe('student_today_at(4:00 pm)')
    expect(
      whenLabel({ date: '2026-11-05', startTime: '16:00', startsInMinutes: null }, 'en', t),
    ).toMatch(/^student_day_at\(/)
  })

  it('words how soon', () => {
    expect(howSoon(null, t)).toBe('student_next_class()')
    expect(howSoon(35, t)).toBe('student_next_in_min(35)')
    expect(howSoon(125, t)).toBe('student_next_in_hours(2,5)')
  })
})

it('trims marks without a float round-trip surprise', () => {
  expect(formatMark(36.7)).toBe('36.7')
  expect(formatMark(44)).toBe('44')
  expect(formatMark(33.25)).toBe('33.25')
})

it('takes a whole Bangla grapheme for an initial', () => {
  expect(initial('ফারহান ইসলাম')).toBe('ফা')
  expect(initial('  tasnim')).toBe('t')
  expect(initial('')).toBe('?')
})
