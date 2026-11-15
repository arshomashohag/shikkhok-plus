/**
 * The code step's seam [frontend-components § 2.2a]: a `CodeEntry` shown
 * again after a Replace round says why, and keeps the original send's
 * Resend pacing rather than a fresh minute.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider, translate } from '../../i18n/i18n'
import { CodeEntry, RESEND_AFTER_S, secondsUntil } from './parts'

const en = (key: string, ...args: string[]) => translate('en', key, ...args)

function renderEntry(props: Partial<Parameters<typeof CodeEntry>[0]> = {}) {
  const verify = vi.fn(async () => undefined)
  const resend = vi.fn(async () => undefined)
  render(
    <I18nProvider lang="en">
      <CodeEntry verify={verify} resend={resend} {...props} />
    </I18nProvider>,
  )
  return { verify, resend }
}

describe('secondsUntil', () => {
  it('rounds up, and never goes below zero', () => {
    expect(secondsUntil(10_500, 0)).toBe(11)
    expect(secondsUntil(40_000, 0)).toBe(40)
    expect(secondsUntil(0, 5_000)).toBe(0)
  })
})

describe('CodeEntry', () => {
  it('shows initialError on mount, as an alert', () => {
    renderEntry({ initialError: 'This code has expired.' })
    expect(screen.getByRole('alert')).toHaveTextContent('This code has expired.')
    expect(screen.getByLabelText(en('auth_code_label'))).toHaveAttribute('aria-invalid', 'true')
  })

  it('a resendAvailableAt in the past enables Resend at once', () => {
    renderEntry({ resendAvailableAt: Date.now() - 1000 })
    expect(screen.getByRole('button', { name: en('auth_resend') })).toBeEnabled()
  })

  it('a resendAvailableAt in 40 s counts down from 40', () => {
    renderEntry({ resendAvailableAt: Date.now() + 40_000 })
    expect(screen.getByRole('button', { name: en('auth_resend_in', '0:40') })).toBeDisabled()
  })

  it('by default behaves as before: no error, and a minute before Resend', () => {
    renderEntry()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(RESEND_AFTER_S).toBe(60)
    expect(screen.getByRole('button', { name: en('auth_resend_in', '0:60') })).toBeDisabled()
  })

  it('a new code after the step was shown again restarts the minute', async () => {
    const { resend } = renderEntry({ resendAvailableAt: Date.now() - 1 })
    await userEvent.click(screen.getByRole('button', { name: en('auth_resend') }))
    expect(resend).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: en('auth_resend_in', '0:60') })).toBeDisabled()
  })

  it('checks by itself after the sixth digit', async () => {
    const { verify } = renderEntry()
    await userEvent.type(screen.getByLabelText(en('auth_code_label')), '123456')
    expect(verify).toHaveBeenCalledWith('123456')
  })
})
