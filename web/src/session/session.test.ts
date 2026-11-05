import { describe, expect, it } from 'vitest'
import { readLenses, resolveLens } from './session'

describe('readLenses', () => {
  it('keeps known lenses in the server order and drops unknown kinds', () => {
    expect(
      readLenses([
        { kind: 'teacher', count: 7 },
        { kind: 'admin', count: 1 },
        { kind: 'GUARDIAN', count: 2 },
      ]),
    ).toEqual([
      { lens: 'teacher', count: 7 },
      { lens: 'guardian', count: 2 },
    ])
  })
})

describe('resolveLens — the session state machine', () => {
  const teacher = { lens: 'teacher' as const, count: 1 }
  const guardian = { lens: 'guardian' as const, count: 2 }

  it('no lens: nothing opens but invitations', () => {
    expect(resolveLens([], 'teacher')).toEqual({ lens: null, choosing: false })
  })

  it('one lens: open it, whatever was remembered', () => {
    expect(resolveLens([guardian], 'teacher')).toEqual({ lens: 'guardian', choosing: false })
  })

  it('several: reopen the remembered one', () => {
    expect(resolveLens([teacher, guardian], 'guardian')).toEqual({
      lens: 'guardian',
      choosing: false,
    })
  })

  it('several, nothing remembered or a lens since lost: ask', () => {
    expect(resolveLens([teacher, guardian], null)).toEqual({ lens: null, choosing: true })
    expect(resolveLens([teacher, guardian], 'student')).toEqual({ lens: null, choosing: true })
  })
})
