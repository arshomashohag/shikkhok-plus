import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { json, renderScreen } from '../../test/render'
import { SignIn } from './SignIn'

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

const TOKENS = { access_token: 'A', refresh_token: 'R', expires_in: 900, mfa_required: false }

/** Serve `/v1/auth/password` with `answer`; `/v1/me` with an empty account. */
function servePassword(answer: (body: Record<string, unknown>) => Response) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    if (url.endsWith('/v1/auth/password')) return answer(JSON.parse(init.body as string))
    return json(200, { lenses: [] })
  })
}

async function typeAndSubmit(identifier: string, password: string) {
  await userEvent.type(screen.getByLabelText('Mobile number'), identifier)
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

it('marks the fields up for a password manager', () => {
  renderScreen(<SignIn />)
  expect(screen.getByLabelText('Mobile number')).toHaveAttribute('autocomplete', 'username')
  expect(screen.getByLabelText('Mobile number')).toHaveAttribute('inputmode', 'tel')
  const password = screen.getByLabelText('Password')
  expect(password).toHaveAttribute('type', 'password')
  expect(password).toHaveAttribute('autocomplete', 'current-password')
})

it('refuses a malformed number without calling the server', async () => {
  renderScreen(<SignIn />)
  await typeAndSubmit('12345', 'a long password')
  expect(screen.getByRole('alert')).toHaveTextContent('11 digits')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('signs in with a number and a password', async () => {
  servePassword(() => json(200, TOKENS))
  renderScreen(<SignIn />)
  await typeAndSubmit('০১৭১১-২৩৪৫৬৭', 'correct horse')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/password')).toEqual({ phone: '01711234567', password: 'correct horse' })
  // No code is sent on the way in any more.
  expect(called('/v1/auth/otp')).toHaveLength(0)
  expect(called('/v1/auth/mfa')).toHaveLength(0)
})

it('signs in with an email address, trimmed and lowercased', async () => {
  servePassword(() => json(200, TOKENS))
  renderScreen(<SignIn />)
  await userEvent.click(screen.getByRole('button', { name: 'Email' }))
  const email = screen.getByLabelText('Email address')
  expect(email).toHaveAttribute('type', 'email')
  expect(email).toHaveAttribute('autocomplete', 'username')
  await userEvent.type(email, '  Rina@Example.com ')
  await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/password')).toEqual({
    email: 'rina@example.com',
    password: 'correct horse',
  })
})

it('refuses a malformed email address without calling the server', async () => {
  renderScreen(<SignIn />)
  await userEvent.click(screen.getByRole('button', { name: 'Email' }))
  await userEvent.type(screen.getByLabelText('Email address'), 'rina-at-example')
  await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(screen.getByRole('alert')).toHaveTextContent('name@example.com')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('a wrong password shows the server’s words and a way to the code flow', async () => {
  servePassword(() => refusal(400, 'auth.password.wrong', 'PASSWORD_NOT_VALID'))
  renderScreen(<SignIn />)
  await typeAndSubmit('01711234567', 'wrong one')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent("That phone or email and password don't match.")
  expect(alert).toHaveTextContent('First time signing in with a password, or forgot it?')
  expect(screen.getAllByRole('link', { name: 'Get a code' })[0]).toHaveAttribute(
    'href',
    '/signin/code',
  )
  // The typed password does not linger on screen, and nothing is stored.
  expect(screen.getByLabelText('Password')).toHaveValue('')
  expect(readTokens()).toBeNull()
})

it('too many wrong passwords says so, with the same way to the code flow', async () => {
  servePassword(() => refusal(409, 'auth.password.too_many_attempts', 'CONFLICT'))
  renderScreen(<SignIn />)
  await typeAndSubmit('01711234567', 'wrong again')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Too many tries. Wait a while, or log in with a code instead.')
  expect(alert).toHaveTextContent('Get a code')
})

it('a network-wide ceiling shows its own words and no code-flow hint', async () => {
  servePassword(() => refusal(409, 'auth.verify.temporarily_unavailable', 'CONFLICT'))
  renderScreen(<SignIn />)
  await typeAndSubmit('01711234567', 'any password')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Too many attempts right now.')
  expect(alert).not.toHaveTextContent('forgot it?')
})

it('offers the code flow for a forgotten or first password', () => {
  renderScreen(<SignIn />)
  expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute(
    'href',
    '/signin/code',
  )
  expect(screen.getByText(/Signing in for the first time since passwords arrived/)).toBeVisible()
})

// ------------------------------------------------- two-step verification

const CHALLENGE = { mfa_required: true, mfa_challenge: 'CH-1', mfa_expires_in: 300 }

/** Serve the password step with a challenge, and `/v1/auth/mfa` with `mfa`. */
function serveMfa(mfa: (body: Record<string, unknown>) => Response, challenge = CHALLENGE) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    if (url.endsWith('/v1/auth/password')) return json(200, challenge)
    if (url.endsWith('/v1/auth/mfa')) return mfa(JSON.parse(init.body as string))
    return json(200, { lenses: [] })
  })
}

async function toMfaStep() {
  renderScreen(<SignIn />)
  await typeAndSubmit('01711234567', 'correct horse')
  return screen.findByLabelText('Authenticator code')
}

const mfaError = (status: number, key: string, code = 'MFA') =>
  json(status, { error: { code, message_key: key, retryable: false } })

it('asks for the authenticator code, and stores tokens only once it is right', async () => {
  serveMfa(() => json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 }))
  const field = await toMfaStep()
  // The password alone signed nobody in.
  expect(readTokens()).toBeNull()
  expect(field).toHaveAttribute('inputmode', 'numeric')
  expect(field).toHaveAttribute('autocomplete', 'one-time-code')

  await userEvent.type(field, '654321')
  await waitFor(() => expect(readTokens()?.access).toBe('A2'))
  expect(bodyOf('/v1/auth/mfa')).toEqual({ challenge: 'CH-1', code: '654321' })
})

it('takes a recovery code instead', async () => {
  serveMfa(() => json(200, { access_token: 'A3', refresh_token: 'R3', expires_in: 900 }))
  await toMfaStep()
  await userEvent.click(screen.getByRole('button', { name: 'Use a recovery code instead' }))
  await userEvent.type(screen.getByLabelText('Recovery code'), 'abcde-fghjk')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(readTokens()?.access).toBe('A3'))
  expect(bodyOf('/v1/auth/mfa')).toEqual({ challenge: 'CH-1', recovery_code: 'ABCDE-FGHJK' })
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

it('after too many wrong codes, says so and starts again from the form', async () => {
  serveMfa(() => mfaError(409, 'mfa.locked'))
  const field = await toMfaStep()
  await userEvent.type(field, '000000')
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Too many wrong codes. Try again in 15 minutes.',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Start again' }))
  expect(screen.getByLabelText('Password')).toBeInTheDocument()
  expect(readTokens()).toBeNull()
})

it('a lapsed challenge (401) starts again from the form, with no renewal or sign-out', async () => {
  serveMfa(() => mfaError(401, 'mfa.challenge_expired', 'UNAUTHENTICATED'))
  const field = await toMfaStep()
  await userEvent.type(field, '123123')
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Signing in took too long. Enter your password again.',
  )
  expect(screen.getByLabelText('Password')).toHaveValue('')
  // There is no session yet: the 401 must not reach token renewal.
  expect(called('/v1/auth/refresh')).toHaveLength(0)
  expect(called('/v1/me')).toHaveLength(0)
  expect(readTokens()).toBeNull()
})

it('starts again by itself when the five minutes run out on screen', async () => {
  serveMfa(() => mfaError(400, 'mfa.code_wrong'), { ...CHALLENGE, mfa_expires_in: 1 })
  await toMfaStep()
  expect(
    await screen.findByText(
      'Signing in took too long. Enter your password again.',
      {},
      { timeout: 2500 },
    ),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('Password')).toBeInTheDocument()
})
