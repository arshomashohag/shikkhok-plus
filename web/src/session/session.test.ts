import { describe, expect, it, vi } from 'vitest'
import type { Me } from '../api/endpoints'
import { readLenses, resolveLens, sessionFromMe } from './session'

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

// Written before the code [FR5.2] [NFR3.14]: which of the gate or the app
// a read publishes. A wrong answer shows a screen the server's flag
// withholds, so these were run red first.
describe('sessionFromMe — the gate or the app', () => {
  const me = (patch: Partial<Me>): Me => ({
    self_name: 'Karim Uddin',
    phone: '+8801711111111',
    has_password: true,
    username_required: false,
    lenses: [
      { kind: 'teacher', count: 1 },
      { kind: 'guardian', count: 2 },
    ],
    workspaces: [{ owner_id: 'ws-1', kind: 'solo' }],
    ...patch,
  })

  it('a read saying username_required true publishes the gate, holding the account', () => {
    const account = me({ username_required: true })
    const workspaceOf = vi.fn(() => 'ws-1')
    expect(sessionFromMe(account, 'guardian', workspaceOf)).toEqual({
      state: 'username-required',
      me: account,
    })
    // Nothing about the app is decided behind the gate: no workspace is reconciled.
    expect(workspaceOf).not.toHaveBeenCalled()
  })

  it('false publishes ready, exactly as resolveLens and the workspace decide today', () => {
    const account = me({ username_required: false })
    const workspaceOf = vi.fn(() => 'ws-1')
    expect(sessionFromMe(account, 'guardian', workspaceOf)).toEqual({
      state: 'ready',
      me: account,
      options: [
        { lens: 'teacher', count: 1 },
        { lens: 'guardian', count: 2 },
      ],
      lens: 'guardian',
      choosing: false,
      workspace: 'ws-1',
    })
    expect(workspaceOf).toHaveBeenCalledWith(account.workspaces)
  })

  it('several lenses and nothing remembered still asks, behind no gate', () => {
    const result = sessionFromMe(me({}), null, () => null)
    expect(result).toMatchObject({ state: 'ready', lens: null, choosing: true, workspace: null })
  })

  it('an absent flag (an older server) reads as false and publishes ready', () => {
    const account = { ...me({}) } as Partial<Me>
    delete account.username_required
    expect(sessionFromMe(account as Me, null, () => null)).toMatchObject({ state: 'ready' })
  })
})
