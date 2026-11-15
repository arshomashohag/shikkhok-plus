/** The hint's states, from the server's four answers [NFR1.3] [NFR6.3]. */
import { describe, expect, it } from 'vitest'
import { translate, translateMessage } from '../../../i18n/i18n'
import { availabilityText, mapAvailability, type Availability } from './availability'

const t = (key: string) => translate('en', key)
const message = (key: string) => translateMessage('en', key)

describe('mapAvailability', () => {
  it.each(['available', 'unavailable', 'invalid', 'reserved'] as const)(
    '%s maps to one answered state carrying that status',
    (status) => {
      expect(mapAvailability({ status })).toEqual({ kind: 'answered', status, messageKey: null })
    },
  )

  it('keeps the message key an invalid answer carries', () => {
    expect(
      mapAvailability({ status: 'invalid', message_key: 'account.username.too_short' }),
    ).toEqual({ kind: 'answered', status: 'invalid', messageKey: 'account.username.too_short' })
  })

  it('an unknown status renders as could-not-check, never as a crash or a guess', () => {
    expect(mapAvailability({ status: 'held' })).toEqual({ kind: 'could-not-check' })
    expect(mapAvailability({ status: '' })).toEqual({ kind: 'could-not-check' })
  })

  it('tolerates a field it does not know [NFR6.1]', () => {
    const response = { status: 'available', message_key: null, held_until: '2026-12-01' }
    expect(mapAvailability(response)).toMatchObject({ kind: 'answered', status: 'available' })
  })
})

describe('availabilityText', () => {
  const answered = (status: 'available' | 'unavailable' | 'reserved' | 'invalid', key = null) =>
    ({ kind: 'answered', status, messageKey: key }) as Availability

  it('says nothing of its own while idle or waiting, so the help line stays', () => {
    expect(availabilityText({ kind: 'idle' }, t, message)).toBeNull()
    expect(availabilityText({ kind: 'waiting' }, t, message)).toBeNull()
  })

  it('names each answer with its own string', () => {
    expect(availabilityText({ kind: 'checking' }, t, message)).toBe(t('username_checking'))
    expect(availabilityText(answered('available'), t, message)).toBe(t('username_available'))
    expect(availabilityText(answered('reserved'), t, message)).toBe(t('account_username_reserved'))
  })

  it('has one text for unavailable: held and taken read alike [ADR-007]', () => {
    expect(availabilityText(answered('unavailable'), t, message)).toBe(
      t('account_username_unavailable'),
    )
  })

  it('shows an invalid answer through the key the server sent', () => {
    const state = {
      kind: 'answered',
      status: 'invalid',
      messageKey: 'account.username.bad_dot',
    } as const
    expect(availabilityText(state, t, message)).toBe(message('account.username.bad_dot'))
  })

  it('reads a failure and a stop after 429 alike: could not check, you can still continue', () => {
    expect(availabilityText({ kind: 'could-not-check' }, t, message)).toBe(
      t('username_could_not_check'),
    )
    expect(availabilityText({ kind: 'stopped' }, t, message)).toBe(t('username_could_not_check'))
  })
})
