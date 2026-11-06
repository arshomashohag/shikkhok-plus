/** The members screen's two decisions it may make itself: wording and sendability. */
import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { inviteBody, memberState } from './Members'

const member = (patch: Partial<Schemas['MemberResponse']>): Schemas['MemberResponse'] => ({
  member_id: 'm1',
  display_name: 'Sumi',
  phone: '+8801711111111',
  role: 'teacher',
  decision: 'pending',
  invited_at: '2026-11-06T00:00:00Z',
  revoked: false,
  is_you: false,
  ...patch,
})

describe('memberState', () => {
  it('names removal before any decision', () => {
    expect(memberState(member({ decision: 'accepted', revoked: true }))).toBe(
      'centre_member_revoked',
    )
    expect(memberState(member({}))).toBe('centre_member_pending')
    expect(memberState(member({ decision: 'declined' }))).toBe('centre_member_declined')
    expect(memberState(member({ decision: 'accepted' }))).toBe('centre_member_accepted')
  })
})

describe('inviteBody', () => {
  it('sends a trimmed name and the number in local form; the server canonicalises it', () => {
    expect(inviteBody('  Sumi ', '+880 1711-111111', 'manager')).toEqual({
      display_name: 'Sumi',
      phone: '01711111111',
      role: 'manager',
    })
  })

  it('sends nothing for a blank name or a number that is not one', () => {
    expect(inviteBody(' ', '01711111111', 'teacher')).toBeNull()
    expect(inviteBody('Sumi', '123', 'teacher')).toBeNull()
  })
})
