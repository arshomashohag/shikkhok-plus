/** Seat links: no child's name in a URL; names only from navigation state. */
import { describe, expect, it } from 'vitest'
import { paths, readSeatNames, seatState } from './paths'

describe('seat links', () => {
  it('carry only the seat id in the URL', () => {
    expect(paths.seatFees('e 1')).toBe('/seats/e%201/fees')
    expect(paths.seatProgress('e1')).toBe('/seats/e1/progress')
  })

  it('round-trip the names through navigation state', () => {
    expect(readSeatNames(seatState('Tasnim', 'Math'))).toEqual({ name: 'Tasnim', batch: 'Math' })
    expect(readSeatNames(seatState('', undefined))).toEqual({})
  })

  it('read nothing from absent or malformed state', () => {
    expect(readSeatNames(null)).toEqual({})
    expect(readSeatNames(undefined)).toEqual({})
    expect(readSeatNames({ seatNames: 'Tasnim' })).toEqual({})
    expect(readSeatNames({ seatNames: { name: 42, batch: ['x'] } })).toEqual({})
  })
})
