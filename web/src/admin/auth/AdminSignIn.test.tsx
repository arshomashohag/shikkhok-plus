/**
 * Admin log-in through the whole app: phone, SMS code, then setting up
 * the authenticator (first time) or entering its code, against a mocked
 * API. What these hold the screens to: the QR and key are shown, the
 * recovery codes are shown once and never stored, the dashboard opens
 * only after "I've saved them", and each refusal reads as it should.
 */
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../i18n/i18n'
import { json } from '../../test/render'
import '../strings'
import { peekAdminSession, resetAdminSessionForTests, SESSION_KEY } from '../session'
import { renderAdmin, serveAdmin, type Call, type Handler } from '../test/renderAdmin'
import { groupSecret } from './AdminSignIn'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)

const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
const URI = `otpauth://totp/ShikkhokPlus%20Admin%3A%2B8801711234567?secret=${SECRET}&issuer=ShikkhokPlus%20Admin`
const CODES = Array.from({ length: 10 }, (_, i) => `ABCD${i}-EFGH${i}`)

const overview = {
  generated_at: new Date().toISOString(),
  accounts: 1234,
  new_7_days: 1,
  new_30_days: 2,
  active_7_days: 3,
  active_30_days: 4,
  teachers: 5,
  centres: 6,
  centre_members: 7,
  students: 8,
  guardians: 9,
  batches: 10,
  seats: 11,
  platforms: [],
  both_platforms: 0,
  no_platform: 0,
  versions: [],
  help_open: 0,
  help_answered: 0,
  help_closed: 0,
}

const error = (status: number, code: string, key: string, details?: Record<string, string>) =>
  json(status, { error: { code, message_key: key, retryable: false, details } })

let calls: Call[] = []

/** The sign-in routes, with the MFA answer chosen per test. */
function serve(
  stage: 'enroll' | 'verify',
  mfa: (body: Record<string, unknown>) => Response,
  extra?: Handler,
  expiresIn = 300,
) {
  calls = serveAdmin((method, url, body) => {
    const fromExtra = extra?.(method, url, body)
    if (fromExtra) return fromExtra
    if (url === '/v1/admin/auth/otp') return json(200, {})
    if (url === '/v1/admin/auth/verify')
      return json(200, {
        challenge: 'CH',
        expires_in: expiresIn,
        stage,
        enrollment: stage === 'enroll' ? { secret: SECRET, otpauth_uri: URI } : null,
      })
    if (url === '/v1/admin/auth/mfa') return mfa(body as Record<string, unknown>)
    if (url === '/v1/admin/overview') return json(200, overview)
    return undefined
  }, false)
}

/** Phone and SMS code, as a person types them. */
async function throughSms(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText(en('auth_phone_label')), '01711234567')
  await user.click(screen.getByRole('button', { name: en('auth_request_code') }))
  await user.type(await screen.findByLabelText(en('auth_code_label')), '123456')
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetAdminSessionForTests()
  sessionStorage.clear()
})

describe('first log-in: setting up the authenticator', () => {
  it('shows the QR code and the key, then the recovery codes once, then the dashboard', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn(async () => undefined)
    serve('enroll', () =>
      json(200, { access_token: 'ADMIN', expires_in: 3600, recovery_codes: CODES }),
    )
    renderAdmin('/teachers')
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    await throughSms(user)
    expect(calls.find((c) => c.url === '/v1/admin/auth/otp')!.body).toEqual({
      phone: '01711234567',
    })
    expect(calls.find((c) => c.url === '/v1/admin/auth/verify')!.body).toEqual({
      phone: '01711234567',
      code: '123456',
    })

    // The setup: a QR of the otpauth URI, the key in fours, a link for phones.
    expect(await screen.findByText(en('web_admin_enroll_title'))).toBeInTheDocument()
    const qr = screen.getByRole('img', { name: en('web_admin_enroll_qr_label') })
    expect(qr.tagName.toLowerCase()).toBe('svg')
    expect(screen.getByTestId('admin-secret')).toHaveTextContent(
      'JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP',
    )
    expect(screen.getByRole('link', { name: en('web_admin_enroll_open_app') })).toHaveAttribute(
      'href',
      URI,
    )
    // No recovery-code option before there are recovery codes.
    expect(screen.queryByRole('button', { name: en('web_admin_use_recovery') })).toBeNull()

    await user.click(screen.getByRole('button', { name: en('web_admin_copy') }))
    expect(writeText).toHaveBeenCalledWith(SECRET)
    expect(screen.getAllByText(en('web_admin_copied')).length).toBeGreaterThan(0)

    await user.type(screen.getByLabelText(en('web_admin_enroll_code_label')), '654321')
    expect(calls.find((c) => c.url === '/v1/admin/auth/mfa')!.body).toEqual({
      challenge: 'CH',
      code: '654321',
    })

    // The codes, once, with the warning; not yet signed in, nothing stored.
    expect(await screen.findByText(en('web_admin_codes_title'))).toBeInTheDocument()
    expect(screen.getByText(en('web_admin_codes_warning'))).toBeInTheDocument()
    const list = screen.getByRole('list', { name: en('web_admin_codes_label') })
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(CODES)
    expect(peekAdminSession()).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()

    await user.click(screen.getByRole('button', { name: en('web_admin_copy_all') }))
    expect(writeText).toHaveBeenLastCalledWith(CODES.join('\n'))

    await user.click(screen.getByRole('button', { name: en('web_admin_codes_saved') }))
    // Into the app, where they were going; only the token is stored.
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/teachers'))
    expect(peekAdminSession()?.access).toBe('ADMIN')
    const stored = sessionStorage.getItem(SESSION_KEY)!
    expect(stored).toContain('ADMIN')
    for (const code of CODES) expect(stored).not.toContain(code)
    expect(localStorage.getItem(SESSION_KEY)).toBeNull()
    expect(screen.queryByText(CODES[0]!)).toBeNull()
  })

  it('says so when the clipboard refuses', async () => {
    const user = userEvent.setup()
    serve('enroll', () => json(200, {}))
    renderAdmin('/signin')
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(async () => Promise.reject(new Error('denied'))) },
      configurable: true,
    })
    await throughSms(user)
    await user.click(await screen.findByRole('button', { name: en('web_admin_copy') }))
    expect(await screen.findByText(en('web_admin_copy_failed'))).toBeInTheDocument()
  })

  it('groups a key in fours', () => {
    expect(groupSecret('ABCDEFGHIJ')).toBe('ABCD EFGH IJ')
    expect(groupSecret('AB CD')).toBe('ABCD')
  })
})

describe('every later log-in: the authenticator code', () => {
  it('signs in with a code from the app, straight to the dashboard', async () => {
    const user = userEvent.setup()
    serve('verify', () => json(200, { access_token: 'ADMIN', expires_in: 3600 }))
    renderAdmin('/')
    await throughSms(user)
    expect(await screen.findByText(en('web_admin_verify_title'))).toBeInTheDocument()
    // No QR or key at a normal log-in.
    expect(screen.queryByRole('img')).toBeNull()
    const field = screen.getByLabelText(en('web_admin_verify_code_label'))
    expect(field).toHaveAttribute('inputmode', 'numeric')
    expect(field).toHaveAttribute('autocomplete', 'one-time-code')
    await user.type(field, '111222')
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(peekAdminSession()?.access).toBe('ADMIN')
    expect(screen.getByText(/Signed in until \d\d:\d\d/)).toBeInTheDocument()
  })

  it('signs in with a recovery code instead', async () => {
    const user = userEvent.setup()
    serve('verify', () => json(200, { access_token: 'ADMIN', expires_in: 3600 }))
    renderAdmin('/')
    await throughSms(user)
    await user.click(await screen.findByRole('button', { name: en('web_admin_use_recovery') }))
    await user.type(screen.getByLabelText(en('web_admin_recovery_label')), ' abcde-fghjk ')
    await user.click(screen.getByRole('button', { name: en('web_admin_recovery_submit') }))
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(calls.find((c) => c.url === '/v1/admin/auth/mfa')!.body).toEqual({
      challenge: 'CH',
      recovery_code: 'ABCDE-FGHJK',
    })
  })

  it('a wrong code: says so inline, clears the field and keeps the cursor in it', async () => {
    const user = userEvent.setup()
    let tries = 0
    serve('verify', () =>
      ++tries === 1
        ? error(400, 'ADMIN_MFA_WRONG', 'auth.otp.wrong')
        : json(200, { access_token: 'ADMIN', expires_in: 3600 }),
    )
    renderAdmin('/')
    await throughSms(user)
    const field = await screen.findByLabelText(en('web_admin_verify_code_label'))
    await user.type(field, '000000')
    expect(await screen.findByText(en('web_admin_wrong_code'))).toBeInTheDocument()
    await waitFor(() => expect(field).toHaveFocus())
    expect(field).toHaveValue('')
    await user.type(field, '111222')
    expect(await screen.findByText('1,234')).toBeInTheDocument()
  })

  it('a wrong recovery code keeps what was typed', async () => {
    const user = userEvent.setup()
    serve('verify', () => error(400, 'ADMIN_MFA_WRONG', 'auth.otp.wrong'))
    renderAdmin('/')
    await throughSms(user)
    await user.click(await screen.findByRole('button', { name: en('web_admin_use_recovery') }))
    const field = screen.getByLabelText(en('web_admin_recovery_label'))
    await user.type(field, 'ABCDE-XXXXX')
    await user.click(screen.getByRole('button', { name: en('web_admin_recovery_submit') }))
    expect(await screen.findByText(en('web_admin_wrong_recovery'))).toBeInTheDocument()
    expect(field).toHaveValue('ABCDE-XXXXX')
    await waitFor(() => expect(field).toHaveFocus())
  })

  it('locked after too many wrong codes: says to wait 15 minutes', async () => {
    const user = userEvent.setup()
    serve('verify', () => error(409, 'ADMIN_MFA_LOCKED', 'auth.otp.no_tries_left'))
    renderAdmin('/')
    await throughSms(user)
    await user.type(await screen.findByLabelText(en('web_admin_verify_code_label')), '000000')
    expect(await screen.findByText(en('web_admin_locked'))).toBeInTheDocument()
    expect(en('web_admin_locked')).toBe('Too many wrong codes. Try again in 15 minutes.')
    expect(screen.queryByLabelText(en('web_admin_verify_code_label'))).toBeNull()
    await user.click(screen.getByRole('button', { name: en('web_admin_start_again') }))
    expect(await screen.findByLabelText(en('auth_phone_label'))).toBeInTheDocument()
  })

  it('a challenge the server no longer accepts starts again from the phone', async () => {
    const user = userEvent.setup()
    serve('verify', () => error(401, 'ADMIN_CHALLENGE_INVALID', 'auth.otp.expired'))
    renderAdmin('/')
    await throughSms(user)
    await user.type(await screen.findByLabelText(en('web_admin_verify_code_label')), '000000')
    expect(await screen.findByText(en('web_admin_challenge_expired'))).toBeInTheDocument()
    expect(screen.getByLabelText(en('auth_phone_label'))).toBeInTheDocument()
  })

  it('a challenge that lapses on screen starts again by itself', async () => {
    const user = userEvent.setup()
    serve('verify', () => json(200, {}), undefined, 0)
    renderAdmin('/')
    await throughSms(user)
    expect(await screen.findByText(en('web_admin_challenge_expired'))).toBeInTheDocument()
    expect(screen.getByLabelText(en('auth_phone_label'))).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/v1/admin/auth/mfa')).toBe(false)
  })
})

describe('the SMS step', () => {
  it('fills in the tries left on a wrong SMS code', async () => {
    const user = userEvent.setup()
    serve(
      'verify',
      () => json(200, {}),
      (_m, url) =>
        url === '/v1/admin/auth/verify'
          ? error(400, 'VALIDATION', 'auth.otp.wrong', { attempts_left: '2' })
          : undefined,
    )
    renderAdmin('/')
    await throughSms(user)
    expect(await screen.findByText(en('auth_otp_wrong', '2'))).toBeInTheDocument()
  })

  it('a number that is not an administrator’s is told it cannot log in here', async () => {
    const user = userEvent.setup()
    serve(
      'verify',
      () => json(200, {}),
      (_m, url) =>
        url === '/v1/admin/auth/verify'
          ? error(403, 'FORBIDDEN', 'authz.lens.not_available')
          : undefined,
    )
    renderAdmin('/')
    await throughSms(user)
    expect(await screen.findByText(en('web_admin_signin_not_admin'))).toBeInTheDocument()
  })

  it('off the admin edge, says admin is not available here', async () => {
    const user = userEvent.setup()
    serve(
      'verify',
      () => json(200, {}),
      (_m, url) =>
        url === '/v1/admin/auth/otp'
          ? error(404, 'NOT_AVAILABLE', 'authz.lens.not_available')
          : undefined,
    )
    renderAdmin('/')
    await user.type(await screen.findByLabelText(en('auth_phone_label')), '01711234567')
    await user.click(screen.getByRole('button', { name: en('auth_request_code') }))
    expect(await screen.findByText(en('web_admin_unavailable'))).toBeInTheDocument()
  })

  it('checks the number’s format before sending anything', async () => {
    const user = userEvent.setup()
    serve('verify', () => json(200, {}))
    renderAdmin('/')
    await user.type(await screen.findByLabelText(en('auth_phone_label')), '12345')
    await act(() => user.click(screen.getByRole('button', { name: en('auth_request_code') })))
    expect(screen.getByText(en('phone_invalid'))).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })
})
