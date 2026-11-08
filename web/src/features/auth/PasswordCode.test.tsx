/**
 * The code flow — forgot password, or an account's first password —
 * against a mocked API: identifier, code, choose a password, signed in.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { json, renderScreen } from '../../test/render'
import { PasswordCode } from './PasswordCode'

const fetchMock = vi.fn()
beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
  clearTokens()
})

const called = (path: string) => fetchMock.mock.calls.filter(([u]) => (u as string).endsWith(path))
const bodyOf = (path: string, i = 0) =>
  JSON.parse(called(path)[i]![1].body as string) as Record<string, unknown>

const refusal = (status: number, key: string, code = 'REFUSED') =>
  json(status, { error: { code, message_key: key, retryable: false } })

const SETUP = {
  access_token: null,
  refresh_token: null,
  expires_in: null,
  mfa_required: false,
  mfa_challenge: null,
  mfa_expires_in: null,
  password_setup_token: 'SETUP-1',
  password_setup_expires_in: 600,
}
const TOKENS = { access_token: 'A', refresh_token: 'R', expires_in: 900 }

function serve(
  setup: (body: Record<string, unknown>) => Response,
  verify: () => Response = () => json(200, SETUP),
) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    if (url.endsWith('/v1/auth/otp')) return json(200, { status: 'requested' })
    if (url.endsWith('/v1/auth/verify')) return verify()
    if (url.endsWith('/v1/auth/password/setup')) return setup(JSON.parse(init.body as string))
    return json(200, { lenses: [] })
  })
}

async function toChooseStep() {
  renderScreen(<PasswordCode />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  // The same words whether or not the number has an account [D-33].
  expect(await screen.findByText(/If this number has an account/)).toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
  return screen.findByLabelText('New password')
}

async function choose(password: string, confirm = password) {
  await userEvent.type(screen.getByLabelText('New password'), password)
  await userEvent.type(screen.getByLabelText('Type the password again'), confirm)
  await userEvent.click(screen.getByRole('button', { name: 'Save password and log in' }))
}

it('sends a code, spends it, sets the password and signs in', async () => {
  serve(() => json(200, TOKENS))
  const field = await toChooseStep()
  expect(field).toHaveAttribute('type', 'password')
  expect(field).toHaveAttribute('autocomplete', 'new-password')
  // The code bought no session by itself.
  expect(readTokens()).toBeNull()
  expect(bodyOf('/v1/auth/otp')).toEqual({ phone: '01711234567' })
  expect(bodyOf('/v1/auth/verify')).toEqual({ phone: '01711234567', code: '123456' })

  await choose('a new long password')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/password/setup')).toEqual({
    token: 'SETUP-1',
    password: 'a new long password',
  })
  // The password went to the server and nowhere else.
  expect(JSON.stringify({ ...localStorage })).not.toContain('a new long password')
  expect(JSON.stringify({ ...sessionStorage })).not.toContain('a new long password')
})

it('works the same with an email address', async () => {
  serve(() => json(200, TOKENS))
  renderScreen(<PasswordCode />)
  await userEvent.click(screen.getByRole('button', { name: 'Email' }))
  await userEvent.type(screen.getByLabelText('Email address'), 'Rina@Example.com')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  expect(await screen.findByText(/If this address has an account/)).toBeInTheDocument()
  expect(screen.getByText('rina@example.com')).toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
  await screen.findByLabelText('New password')
  await choose('a new long password')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/verify')).toEqual({ email: 'rina@example.com', code: '123456' })
})

it('checks length and the match on the device, and nothing else', async () => {
  serve(() => json(200, TOKENS))
  await toChooseStep()
  await choose('short')
  expect(await screen.findByRole('alert')).toHaveTextContent('Use at least 8 characters.')
  await userEvent.clear(screen.getByLabelText('New password'))
  await userEvent.clear(screen.getByLabelText('Type the password again'))
  await choose('a new long password', 'a different one')
  expect(await screen.findByRole('alert')).toHaveTextContent('The two passwords are not the same.')
  expect(called('/v1/auth/password/setup')).toHaveLength(0)
})

it('shows the server’s refusal of a common password under the field', async () => {
  serve(() => refusal(400, 'auth.password.too_common', 'VALIDATION'))
  await toChooseStep()
  await choose('password123')
  expect(await screen.findByRole('alert')).toHaveTextContent('That password is too common')
  // Still on the password step, to choose another with the same token.
  expect(screen.getByLabelText('New password')).toBeInTheDocument()
  expect(readTokens()).toBeNull()
})

it('an expired setup token starts the code flow again, with no renewal or sign-out', async () => {
  serve(() => refusal(401, 'auth.password.setup_expired', 'UNAUTHENTICATED'))
  await toChooseStep()
  await choose('a new long password')
  expect(await screen.findByRole('status')).toHaveTextContent(
    'That took too long. Ask for a new code to choose your password.',
  )
  expect(screen.getByLabelText('Mobile number')).toBeInTheDocument()
  expect(called('/v1/auth/refresh')).toHaveLength(0)
  expect(readTokens()).toBeNull()
})

it('asks for the authenticator code too when verify says two-step is on', async () => {
  serve(
    (body) =>
      body.code === '654321'
        ? json(200, TOKENS)
        : refusal(400, body.code ? 'mfa.code_wrong' : 'mfa.code_required', 'MFA'),
    () => json(200, { ...SETUP, mfa_required: true }),
  )
  await toChooseStep()
  const totp = screen.getByLabelText('Authenticator code')
  expect(totp).toHaveAttribute('autocomplete', 'one-time-code')

  await userEvent.type(totp, '000000')
  await choose('a new long password')
  expect(await screen.findByRole('alert')).toHaveTextContent("That code isn't right.")
  expect(readTokens()).toBeNull()

  await userEvent.type(screen.getByLabelText('Authenticator code'), '654321')
  await userEvent.click(screen.getByRole('button', { name: 'Save password and log in' }))
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/password/setup', 1)).toEqual({
    token: 'SETUP-1',
    password: 'a new long password',
    code: '654321',
  })
})

it('takes a recovery code instead of the authenticator code', async () => {
  serve(
    () => json(200, TOKENS),
    () => json(200, { ...SETUP, mfa_required: true }),
  )
  await toChooseStep()
  await userEvent.click(screen.getByRole('button', { name: 'Use a recovery code instead' }))
  await userEvent.type(screen.getByLabelText('Recovery code'), 'abcde-fghjk')
  await choose('a new long password')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/password/setup')).toEqual({
    token: 'SETUP-1',
    password: 'a new long password',
    recovery_code: 'ABCDE-FGHJK',
  })
})

it('a wrong code says so and stays on the code step', async () => {
  serve(
    () => json(200, TOKENS),
    () => refusal(400, 'auth.otp.expired', 'OTP_NOT_VALID'),
  )
  renderScreen(<PasswordCode />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  await userEvent.type(await screen.findByLabelText('Enter the code'), '000000')
  expect(await screen.findByRole('alert')).toHaveTextContent('This code has expired')
  expect(screen.getByLabelText('Enter the code')).toHaveValue('')
  expect(called('/v1/auth/password/setup')).toHaveLength(0)
})
