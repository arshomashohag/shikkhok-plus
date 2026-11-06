/** A centre teacher's roster marks: unmarked means present, recorded absences carry. */
import { describe, expect, it } from 'vitest'
import { absentFrom, marksFrom, type Roster } from './model'

const roster: Roster = {
  seats: [
    { enrollment_id: 'a', display_name: 'Rahim', present: null },
    { enrollment_id: 'b', display_name: 'Karim', present: false },
    { enrollment_id: 'c', display_name: 'Sumi', present: true },
  ],
  attendance_version: 2,
  writable: true,
  topic: null,
  topic_version: 0,
}

describe('roster marks', () => {
  it('starts from the recorded absences', () => {
    expect([...absentFrom(roster)]).toEqual(['b'])
  })

  it('sends every seat, present unless marked absent', () => {
    expect(marksFrom(roster, new Set(['a']))).toEqual([
      { enrollment_id: 'a', present: false },
      { enrollment_id: 'b', present: true },
      { enrollment_id: 'c', present: true },
    ])
  })
})
