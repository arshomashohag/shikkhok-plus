import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { json, renderScreen } from '../../test/render'
import { SignIn } from './SignIn'

const fetchMock = vi.fn()
beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
  clearTokens()
})

it('refuses a malformed number without calling the server', async () => {
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '12345')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  expect(screen.getByRole('alert')).toHaveTextContent('11 digits')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('sends the code, then signs in by itself after the sixth digit', async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/v1/auth/otp')) return json(200, { status: 'requested' })
    if (url.endsWith('/v1/auth/verify'))
      return json(200, {
        access_token: 'A',
        refresh_token: 'R',
        expires_in: 900,
        mfa_required: false,
      })
    return json(200, { lenses: [] })
  })
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '০১৭১১-২৩৪৫৬৭')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))

  // The same words whether or not the number has an account [D-33].
  expect(await screen.findByText(/If this number has an account/)).toBeInTheDocument()
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual({ phone: '01711234567' })

  await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  const verify = fetchMock.mock.calls.find(([u]) => (u as string).endsWith('/verify'))
  expect(JSON.parse(verify![1].body as string)).toEqual({ phone: '01711234567', code: '123456' })
  // No second step for an account without two-step verification.
  expect(screen.queryByLabelText('Authenticator code')).toBeNull()
  expect(called('/v1/auth/mfa')).toHaveLength(0)
})

it('shows the string the server named for a wrong code', async () => {
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/v1/auth/otp')
      ? json(200, { status: 'requested' })
      : json(400, {
          error: { code: 'VALIDATION', message_key: 'auth.otp.expired', retryable: false },
        }),
  )
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  await userEvent.type(await screen.findByLabelText('Enter the code'), '000000')
  expect(await screen.findByRole('alert')).toHaveTextContent('This code has expired')
  expect(readTokens()).toBeNull()
})

it('says how many tries are left after a wrong code', async () => {
  // The server's real shape for a wrong code: the count arrives in
  // `details`, and the string has a placeholder for it. This read
  // "That code isn't right. {1} tries left." until the count was passed.
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/v1/auth/otp')
      ? json(200, { status: 'requested' })
      : json(400, {
          error: {
            code: 'OTP_WRONG',
            message_key: 'auth.otp.wrong',
            retryable: false,
            details: { attempts_left: '2' },
          },
        }),
  )
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  await userEvent.type(await screen.findByLabelText('Enter the code'), '000000')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent("That code isn't right. 2 tries left.")
  expect(alert.textContent).not.toMatch(/\{\d\}/)
})

// ------------------------------------------------- two-step verification

const CHALLENGE = { mfa_required: true, mfa_challenge: 'CH-1', mfa_expires_in: 300 }

/** Serve the SMS steps with `verify`, and `/v1/auth/mfa` with `mfa`. */
function serveMfa(mfa: (body: Record<string, unknown>) => Response) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    if (url.endsWith('/v1/auth/otp')) return json(200, { status: 'requested' })
    if (url.endsWith('/v1/auth/verify')) return json(200, CHALLENGE)
    if (url.endsWith('/v1/auth/mfa')) return mfa(JSON.parse(init.body as string))
    return json(200, { lenses: [] })
  })
}

async function toMfaStep() {
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
  return screen.findByLabelText('Authenticator code')
}

const called = (path: string) => fetchMock.mock.calls.filter(([u]) => (u as string).endsWith(path))

const mfaError = (status: number, key: string, code = 'MFA') =>
  json(status, { error: { code, message_key: key, retryable: false } })

it('asks for the authenticator code, and stores tokens only once it is right', async () => {
  serveMfa(() => json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 }))
  const field = await toMfaStep()
  // The SMS code alone signed nobody in.
  expect(readTokens()).toBeNull()
  expect(field).toHaveAttribute('inputmode', 'numeric')
  expect(field).toHaveAttribute('autocomplete', 'one-time-code')

  await userEvent.type(field, '654321')
  await waitFor(() => expect(readTokens()?.access).toBe('A2'))
  expect(JSON.parse(called('/v1/auth/mfa')[0]![1].body as string)).toEqual({
    challenge: 'CH-1',
    code: '654321',
  })
})

it('takes a recovery code instead', async () => {
  serveMfa(() => json(200, { access_token: 'A3', refresh_token: 'R3', expires_in: 900 }))
  await toMfaStep()
  await userEvent.click(screen.getByRole('button', { name: 'Use a recovery code instead' }))
  await userEvent.type(screen.getByLabelText('Recovery code'), 'abcde-fghjk')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(readTokens()?.access).toBe('A3'))
  expect(JSON.parse(called('/v1/auth/mfa')[0]![1].body as string)).toEqual({
    challenge: 'CH-1',
    recovery_code: 'ABCDE-FGHJK',
  })
})

it('says a wrong code is wrong, clears it and stores nothing', async () => {
  serveMfa(() => mfaError(400, 'mfa.code_wrong'))
  const field = await toMfaStep()
  await userEvent.type(field, '000000')
  expect(await screen.findByRole('alert')).toHaveTextContent(
    "That code isn't right. Check your authenticator app and try again.",
  )
  expect(field).toHaveValue('')
  expect(readTokens()).toBeNull()
})

it('says a wrong recovery code is wrong in its own words', async () => {
  serveMfa(() => mfaError(400, 'mfa.code_wrong'))
  await toMfaStep()
  await userEvent.click(screen.getByRole('button', { name: 'Use a recovery code instead' }))
  await userEvent.type(screen.getByLabelText('Recovery code'), 'ZZZZZ-ZZZZZ')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    "That recovery code isn't right, or it has already been used.",
  )
})

it('after too many wrong codes, says so and starts again from the number', async () => {
  serveMfa(() => mfaError(409, 'mfa.locked'))
  const field = await toMfaStep()
  await userEvent.type(field, '000000')
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Too many wrong codes. Try again in 15 minutes.',
  )
  expect(screen.queryByLabelText('Authenticator code')).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Start again' }))
  expect(screen.getByLabelText('Mobile number')).toBeInTheDocument()
  expect(readTokens()).toBeNull()
})

it('a lapsed challenge (401) starts again from the number, with no renewal or sign-out', async () => {
  serveMfa(() => mfaError(401, 'mfa.challenge_expired', 'UNAUTHENTICATED'))
  const field = await toMfaStep()
  await userEvent.type(field, '123123')
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Signing in took too long. Start again with a new SMS code.',
  )
  expect(screen.getByLabelText('Mobile number')).toBeInTheDocument()
  // There is no session yet: the 401 must not reach token renewal.
  expect(called('/v1/auth/refresh')).toHaveLength(0)
  expect(called('/v1/me')).toHaveLength(0)
  expect(readTokens()).toBeNull()
})

it('starts again by itself when the five minutes run out on screen', async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/v1/auth/otp')) return json(200, { status: 'requested' })
    return json(200, { ...CHALLENGE, mfa_expires_in: 1 })
  })
  await toMfaStep()
  expect(
    await screen.findByText(
      'Signing in took too long. Start again with a new SMS code.',
      {},
      { timeout: 2500 },
    ),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('Mobile number')).toBeInTheDocument()
})
