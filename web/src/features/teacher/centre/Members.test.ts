/** The members screen's two decisions it may make itself: wording and sendability. */
import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { contactLine, inviteBody, memberState } from './Members'

const member = (patch: Partial<Schemas['MemberResponse']>): Schemas['MemberResponse'] => ({
  member_id: 'm1',
  display_name: 'Sumi',
  phone: '+8801711111111',
  invited_email: null,
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

// An email-only invitation has no phone [C2]; the card must never format
// a null [functional-spec § 1 defect 2, W8 step 5].
describe('contactLine', () => {
  it('formats the phone when there is one', () => {
    expect(contactLine(member({ phone: '+8801711111111' }))).toBe('01711-111111')
  })

  it('shows the invited email when the phone is null', () => {
    expect(contactLine(member({ phone: null, invited_email: 'rina@example.com' }))).toBe(
      'rina@example.com',
    )
  })

  it('prefers the phone when both are present', () => {
    expect(
      contactLine(member({ phone: '+8801711111111', invited_email: 'rina@example.com' })),
    ).toBe('01711-111111')
  })

  it('is null when there is neither', () => {
    expect(contactLine(member({ phone: null, invited_email: null }))).toBeNull()
  })
})

// Existing cases updated for the email parameter (plan correction 1);
// the new ones are from functional-spec W8 steps 2–3.
describe('inviteBody', () => {
  it('sends a trimmed name and the number in local form; the server canonicalises it', () => {
    expect(inviteBody('  Sumi ', '+880 1711-111111', '', 'manager')).toEqual({
      display_name: 'Sumi',
      phone: '01711111111',
      role: 'manager',
    })
  })

  it('sends nothing for a blank name or a number that is not one', () => {
    expect(inviteBody(' ', '01711111111', '', 'teacher')).toBeNull()
    expect(inviteBody('Sumi', '123', '', 'teacher')).toBeNull()
  })

  it('email only: sends the address, trimmed, and no phone key', () => {
    expect(inviteBody('Rina', '', '  Rina@Example.com ', 'teacher')).toEqual({
      display_name: 'Rina',
      email: 'rina@example.com',
      role: 'teacher',
    })
  })

  it('both: sends both', () => {
    expect(inviteBody('Rina', '01711111111', 'rina@example.com', 'teacher')).toEqual({
      display_name: 'Rina',
      phone: '01711111111',
      email: 'rina@example.com',
      role: 'teacher',
    })
  })

  it('neither: nothing to send', () => {
    expect(inviteBody('Rina', ' ', '  ', 'teacher')).toBeNull()
  })

  it('a malformed email sends nothing, even beside a good phone', () => {
    expect(inviteBody('Rina', '', 'rina@example', 'teacher')).toBeNull()
    expect(inviteBody('Rina', '01711111111', 'rina-at-example', 'teacher')).toBeNull()
  })
})
