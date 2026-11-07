/** The examiner screen's own two decisions: the state line and a sendable mark. */
import { describe, expect, it } from 'vitest'
import { markBody, resultKey } from './MyExams'

describe('resultKey', () => {
  it('names the derived and absent states, and nothing for a mark', () => {
    const row = { enrollment_id: 'e', display_name: 'R' }
    expect(resultKey({ ...row, result_state: 'absent' })).toBe('my_exam_absent')
    expect(resultKey({ ...row, result_state: 'joined_after' })).toBe('my_exam_joined_after')
    expect(resultKey({ ...row, result_state: 'not_entered' })).toBe('my_exam_not_entered')
    expect(resultKey({ ...row, result_state: 'marked', marks: 72 })).toBeNull()
  })
})

describe('markBody', () => {
  it('sends a number typed, and nothing for blank, negative or not a number', () => {
    expect(markBody('e', ' 72.5 ')).toEqual({
      enrollment_id: 'e',
      result_state: 'marked',
      marks: 72.5,
    })
    expect(markBody('e', '')).toBeNull()
    expect(markBody('e', '-1')).toBeNull()
    expect(markBody('e', 'abc')).toBeNull()
  })

  it('reads Bangla digits, and refuses what Number() would quietly accept', () => {
    expect(markBody('e', '৭২.৫')).toMatchObject({ marks: 72.5 })
    expect(markBody('e', '0x10')).toBeNull()
    expect(markBody('e', '1e2')).toBeNull()
    expect(markBody('e', 'Infinity')).toBeNull()
    expect(markBody('e', '1.2.3')).toBeNull()
    expect(markBody('e', '.5')).toMatchObject({ marks: 0.5 })
    expect(markBody('e', '7.')).toMatchObject({ marks: 7 })
  })
})
