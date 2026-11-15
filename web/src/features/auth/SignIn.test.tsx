import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { I18nProvider, translate, translateMessage } from '../../i18n/i18n'
import { SessionProvider } from '../../session/session'
import { json, renderScreen } from '../../test/render'
import { SignIn } from './SignIn'

const en = (key: string) => translate('en', key)

/** What the code flow would receive as route state. */
function StateProbe() {
  return <p data-testid="route-state">{JSON.stringify(useLocation().state)}</p>
}

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

const loginField = () => screen.getByLabelText(en('auth_login_label'))

async function typeAndSubmit(login: string, password: string) {
  await userEvent.type(loginField(), login)
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

it('marks the fields up for a password manager', () => {
  renderScreen(<SignIn />)
  const login = loginField()
  expect(login).toHaveAttribute('type', 'text')
  expect(login).toHaveAttribute('autocomplete', 'username')
  expect(login).toHaveAttribute('autocapitalize', 'none')
  expect(login).toHaveAttribute('spellcheck', 'false')
  const password = screen.getByLabelText('Password')
  expect(password).toHaveAttribute('type', 'password')
  expect(password).toHaveAttribute('autocomplete', 'current-password')
})

it('has one login field and no Phone | Email toggle [FR4.1]', () => {
  renderScreen(<SignIn />)
  expect(screen.queryByRole('group', { name: en('web_auth_kind_label') })).toBeNull()
  expect(screen.queryByLabelText('Mobile number')).toBeNull()
  expect(screen.queryByLabelText('Email address')).toBeNull()
})

// Rewritten from W3 steps 2–3 (was "refuses a malformed number without
// calling the server"): the client no longer judges the shape; the server does.
it('sends a login of any shape, as typed and trimmed: no client shape check', async () => {
  servePassword(() => refusal(400, 'auth.password.wrong', 'PASSWORD_NOT_VALID'))
  renderScreen(<SignIn />)
  await typeAndSubmit('12345', 'a long password')
  await waitFor(() => expect(called('/v1/auth/password')).toHaveLength(1))
  expect(bodyOf('/v1/auth/password')).toEqual({ login: '12345', password: 'a long password' })
})

// Rewritten from W3 step 3 (was "signs in with a number and a password",
// which asserted client normalisation to `phone`).
it.each([
  ['a username', 'Rahim.Uddin', 'Rahim.Uddin'],
  ['a phone, Bangla digits and all', '  ০১৭১১-২৩৪৫৬৭ ', '০১৭১১-২৩৪৫৬৭'],
  ['an email, casing kept', '  Rina@Example.com ', 'Rina@Example.com'],
])('signs in with %s sent as login, trimmed and otherwise as typed', async (_kind, typed, sent) => {
  servePassword(() => json(200, TOKENS))
  renderScreen(<SignIn />)
  await typeAndSubmit(typed, 'correct horse')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  const body = bodyOf('/v1/auth/password')
  expect(body).toEqual({ login: sent, password: 'correct horse' })
  expect(body).not.toHaveProperty('phone')
  expect(body).not.toHaveProperty('email')
  // No code is sent on the way in any more.
  expect(called('/v1/auth/otp')).toHaveLength(0)
  expect(called('/v1/auth/mfa')).toHaveLength(0)
})

it('a blank login sends nothing: Sign in stays disabled', async () => {
  renderScreen(<SignIn />)
  const submit = screen.getByRole('button', { name: 'Sign in' })
  expect(submit).toBeDisabled()
  await userEvent.type(loginField(), '   ')
  await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
  expect(submit).toBeDisabled()
  expect(fetchMock).not.toHaveBeenCalled()
})

// Rewritten from W3 step 5 (was "refuses a malformed email address
// without calling the server"): the server's `email.invalid` is shown
// under the field.
it('the server’s email.invalid shows under the login field, not in the banner', async () => {
  servePassword(() => refusal(400, 'email.invalid', 'VALIDATION'))
  renderScreen(<SignIn />)
  await typeAndSubmit('rina@example', 'correct horse')
  const error = await screen.findByText(translateMessage('en', 'email.invalid'))
  expect(error).toHaveAttribute('id', 'login-error')
  expect(loginField()).toHaveAttribute('aria-invalid', 'true')
  expect(document.querySelector('.banner.error')).toBeNull()
  expect(loginField()).toHaveValue('rina@example')
})

it.each(['Rahim.Uddin', '01711234567', 'rina@example.com'])(
  'a wrong password reads the same for the login %s [NFR1.1]',
  async (login) => {
    servePassword(() => refusal(400, 'auth.password.wrong', 'PASSWORD_NOT_VALID'))
    renderScreen(<SignIn />)
    await typeAndSubmit(login, 'wrong one')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(translateMessage('en', 'auth.password.wrong'))
    expect(alert).toHaveTextContent(en('web_auth_password_wrong_hint'))
  },
)

it('passes nothing typed to the code flow: its links carry no route state', async () => {
  servePassword(() => refusal(400, 'auth.password.wrong', 'PASSWORD_NOT_VALID'))
  render(
    <I18nProvider lang="en">
      <SessionProvider>
        <MemoryRouter initialEntries={['/signin']}>
          <Routes>
            <Route path="/signin" element={<SignIn />} />
            <Route path="/signin/code" element={<StateProbe />} />
          </Routes>
        </MemoryRouter>
      </SessionProvider>
    </I18nProvider>,
  )
  await typeAndSubmit('Rahim.Uddin', 'wrong one')
  await screen.findByRole('alert')
  const links = screen.getAllByRole('link', { name: /Get a code|Forgot password/ })
  expect(links).toHaveLength(3)
  await userEvent.click(links[0]!)
  expect(screen.getByTestId('route-state')).toHaveTextContent('null')
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
