/**
 * The username field: the client cap only — 64 trimmed code points, not
 * while composing — and the hint's live region [NFR3.11] [functional-spec
 * § 7]. FR1's rules are the server's and are not applied here.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { I18nProvider, translate } from '../../../i18n/i18n'
import type { Availability } from './availability'
import { capUsername, UsernameField, USERNAME_MAX } from './UsernameField'

const en = (key: string) => translate('en', key)

function Harness({ availability = { kind: 'idle' } }: { availability?: Availability }) {
  const [value, setValue] = useState('')
  return (
    <I18nProvider lang="en">
      <UsernameField
        id="u"
        label="Username"
        help={en('signup_username_help')}
        value={value}
        onChange={setValue}
        availability={availability}
      />
    </I18nProvider>
  )
}

const input = () => screen.getByLabelText('Username') as HTMLInputElement

describe('capUsername', () => {
  it('accepts 64 trimmed code points and cuts the 65th', () => {
    const sixtyFour = 'a'.repeat(64)
    expect(capUsername(sixtyFour)).toBe(sixtyFour)
    expect(capUsername(`${sixtyFour}b`)).toBe(sixtyFour)
  })

  it('counts code points, not UTF-16 units', () => {
    const astral = '😀'.repeat(64)
    expect(astral.length).toBe(128)
    expect(capUsername(astral)).toBe(astral)
    expect([...capUsername(`${astral}😀`)]).toHaveLength(64)
  })

  it('accepts 64 with surrounding spaces: only the trimmed value is capped', () => {
    const padded = `  ${'a'.repeat(64)}  `
    expect(capUsername(padded)).toBe(padded)
  })

  it('accepts 21, beyond FR1’s 20: that limit is the server’s', () => {
    expect(capUsername('a'.repeat(21))).toBe('a'.repeat(21))
  })
})

describe('UsernameField', () => {
  it('refuses a 65th code point as it is typed, and keeps 64', async () => {
    render(<Harness />)
    await userEvent.type(input(), 'a'.repeat(USERNAME_MAX + 1))
    expect(input().value).toBe('a'.repeat(USERNAME_MAX))
  })

  it('takes 64 with surrounding spaces, and 21', async () => {
    render(<Harness />)
    fireEvent.change(input(), { target: { value: ` ${'b'.repeat(64)} ` } })
    expect(input().value).toBe(` ${'b'.repeat(64)} `)
    fireEvent.change(input(), { target: { value: 'c'.repeat(21) } })
    expect(input().value).toBe('c'.repeat(21))
  })

  it('has no HTML maxlength, which would count UTF-16 units of untrimmed text', () => {
    render(<Harness />)
    expect(input()).not.toHaveAttribute('maxlength')
  })

  it('does not cut an input while an IME composition is in progress, and caps when it ends', () => {
    render(<Harness />)
    const long = 'ক'.repeat(70)
    fireEvent.input(input(), { target: { value: long }, isComposing: true })
    expect(input().value).toBe(long)
    fireEvent.compositionEnd(input())
    expect([...input().value]).toHaveLength(64)
  })

  it('the hint is a status region present from Idle, showing the help line', () => {
    render(<Harness />)
    const hint = screen.getByRole('status')
    expect(hint).toHaveTextContent(en('signup_username_help'))
    expect(input()).toHaveAttribute('aria-describedby', 'u-help')
    expect(hint).toHaveAttribute('id', 'u-help')
  })

  it('its text becomes username_available after an available answer', () => {
    const { rerender } = render(<Harness />)
    const hint = screen.getByRole('status')
    rerender(<Harness availability={{ kind: 'answered', status: 'available', messageKey: null }} />)
    expect(screen.getByRole('status')).toBe(hint)
    expect(hint).toHaveTextContent(en('username_available'))
  })

  it('carries the password-manager and typing attributes of a username', () => {
    render(<Harness />)
    expect(input()).toHaveAttribute('autocomplete', 'username')
    expect(input()).toHaveAttribute('autocapitalize', 'none')
    expect(input()).toHaveAttribute('spellcheck', 'false')
    expect(input()).toHaveAttribute('type', 'text')
  })
})
