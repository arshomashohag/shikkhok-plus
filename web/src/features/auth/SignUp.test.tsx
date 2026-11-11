/**
 * Creating an account against a mocked API: the form with a password,
 * the code, then the password set with the token the code bought.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { json, renderScreen } from '../../test/render'
import { alreadyAddedFrom, SignUp } from './SignUp'

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
  password_setup_token: 'SETUP-1',
  password_setup_expires_in: 600,
}
const TOKENS = { access_token: 'A', refresh_token: 'R', expires_in: 900 }
const PASSWORD = 'my first password'

function serve(setup: (body: Record<string, unknown>) => Response = () => json(200, TOKENS)) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const body = init.body ? JSON.parse(init.body as string) : {}
    if (url.endsWith('/v1/accounts'))
      return json(201, { account_id: 'acc-1', code_sent_to: body.phone ?? body.email })
    if (url.endsWith('/v1/auth/otp')) return json(200, { status: 'requested' })
    if (url.endsWith('/v1/auth/verify')) return json(200, SETUP)
    if (url.endsWith('/v1/auth/password/setup')) return setup(body)
    return json(200, { lenses: [] })
  })
}

async function fillForm({
  email,
  password = PASSWORD,
  confirm = password,
}: { email?: string; password?: string; confirm?: string } = {}) {
  await userEvent.type(screen.getByLabelText('Full name'), 'Rina Akter')
  if (email) {
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    await userEvent.type(screen.getByLabelText('Email address'), email)
  } else {
    await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  }
  await userEvent.type(screen.getByLabelText('House or flat'), '12')
  await userEvent.type(screen.getByLabelText('Road and area'), 'Road 4, Dhanmondi')
  await userEvent.type(screen.getByLabelText('City or district'), 'Dhaka')
  await userEvent.type(screen.getByLabelText('Postcode'), '1205')
  await userEvent.type(screen.getByLabelText('Password'), password)
  await userEvent.type(screen.getByLabelText('Type the password again'), confirm)
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
}

it('creates the account, spends the code and sets the password in one go', async () => {
  serve()
  renderScreen(<SignUp />)
  const password = screen.getByLabelText('Password')
  expect(password).toHaveAttribute('type', 'password')
  expect(password).toHaveAttribute('autocomplete', 'new-password')
  expect(screen.getByLabelText('Mobile number')).toHaveAttribute('autocomplete', 'username')

  await fillForm()
  const sent = await screen.findByText(/We sent a 6-digit code by SMS to/)
  expect(sent).toHaveTextContent('01711-234567')
  // The password is not sent with the account, and not kept anywhere.
  expect(bodyOf('/v1/accounts')).toEqual({
    role: 'teacher',
    self_name: 'Rina Akter',
    phone: '01711234567',
    address_house: '12',
    address_road: 'Road 4, Dhanmondi',
    address_city: 'Dhaka',
    address_postcode: '1205',
  })
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(PASSWORD)

  await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/verify')).toEqual({ phone: '01711234567', code: '123456' })
  expect(bodyOf('/v1/auth/password/setup')).toEqual({ token: 'SETUP-1', password: PASSWORD })
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(PASSWORD)
})

it('signs up with an email address instead of a phone', async () => {
  serve()
  renderScreen(<SignUp />)
  await fillForm({ email: 'Rina@Example.com' })
  expect(await screen.findByText(/We sent a 6-digit code by email to/)).toHaveTextContent(
    'rina@example.com',
  )
  const created = bodyOf('/v1/accounts')
  expect(created.email).toBe('rina@example.com')
  expect(created).not.toHaveProperty('phone')
  await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/verify')).toEqual({ email: 'rina@example.com', code: '123456' })
})

it('refuses a short or mismatched password before creating anything', async () => {
  serve()
  renderScreen(<SignUp />)
  await fillForm({ password: 'short' })
  expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
  await userEvent.clear(screen.getByLabelText('Password'))
  await userEvent.clear(screen.getByLabelText('Type the password again'))
  await userEvent.type(screen.getByLabelText('Password'), PASSWORD)
  await userEvent.type(screen.getByLabelText('Type the password again'), 'something else')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  expect(screen.getByText('The two passwords are not the same.')).toBeInTheDocument()
  expect(called('/v1/accounts')).toHaveLength(0)
})

it('a password the server refuses is chosen again on the password step', async () => {
  serve((body) =>
    body.password === PASSWORD
      ? refusal(400, 'auth.password.too_common', 'VALIDATION')
      : json(200, TOKENS),
  )
  renderScreen(<SignUp />)
  await fillForm()
  await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
  expect(await screen.findByRole('alert')).toHaveTextContent('That password is too common')
  expect(readTokens()).toBeNull()

  await userEvent.type(screen.getByLabelText('New password'), 'a better passphrase')
  await userEvent.type(screen.getByLabelText('Type the password again'), 'a better passphrase')
  await userEvent.click(screen.getByRole('button', { name: 'Save password and log in' }))
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  expect(bodyOf('/v1/auth/password/setup', 1)).toEqual({
    token: 'SETUP-1',
    password: 'a better passphrase',
  })
})

it('an expired setup token asks for a new code, and stores nothing', async () => {
  serve(() => refusal(401, 'auth.password.setup_expired', 'UNAUTHENTICATED'))
  renderScreen(<SignUp />)
  await fillForm()
  await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
  expect(await screen.findByRole('status')).toHaveTextContent(
    'That took too long. Send a new code to finish creating your account.',
  )
  expect(screen.getByLabelText('Enter the code')).toHaveValue('')
  expect(called('/v1/auth/refresh')).toHaveLength(0)
  expect(readTokens()).toBeNull()
})

it('shows the server’s refusal of the account itself', async () => {
  fetchMock.mockImplementation(async () =>
    refusal(409, 'auth.otp.temporarily_unavailable', 'CONFLICT'),
  )
  renderScreen(<SignUp />)
  await fillForm()
  expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable')
  expect(screen.queryByLabelText('Enter the code')).toBeNull()
})

// ------------------------------------------------ already added [PO-6]

const lookups = () =>
  fetchMock.mock.calls
    .map(([u]) => new URL(u as string, 'http://x'))
    .filter((u) => u.pathname === '/v1/accounts/already-added')
    .map((u) => u.searchParams.get('phone'))

/** Serve the lookup with `answer`, and everything else as `serve()` does. */
function serveLookup(answer: () => Response | Promise<Response>) {
  serve()
  const rest = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    new URL(url, 'http://x').pathname === '/v1/accounts/already-added' ? answer() : rest(url, init),
  )
}

const ADDED = { already_added: true, display_name: '', role: 'student' }
const NOT_ADDED = { already_added: false, display_name: null, role: null }

async function typeNumberAndLeave(number: string) {
  const phone = screen.getByLabelText('Mobile number')
  await userEvent.clear(phone)
  await userEvent.type(phone, number)
  await userEvent.tab()
}

describe('already-added notice', () => {
  it('shows the notice, naming no one, and locks the role to the seat’s', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await typeNumberAndLeave('০১৭১১-২৩৪৫৬৭')

    const status = screen.getByRole('status')
    await waitFor(() => expect(status).toHaveTextContent("You've been added already"))
    expect(status).toHaveTextContent('A teacher has already added this number.')
    expect(lookups()).toEqual(['01711234567'])
    // Nothing is pre-filled: the response carries no name [C-06].
    expect(screen.getByLabelText('Full name')).toHaveValue('')

    expect(screen.getByRole('button', { name: 'Student' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Teacher' })).toBeDisabled()
    expect(screen.getByText('Your role was set when you were added.')).toBeInTheDocument()
  })

  it('shows nothing for a number nobody added', async () => {
    serveLookup(() => json(200, NOT_ADDED))
    renderScreen(<SignUp />)
    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(lookups()).toHaveLength(1))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(screen.getByRole('button', { name: 'Teacher' })).toBeEnabled()
  })

  it('shows nothing when the lookup is refused, and sign-up still goes through', async () => {
    serveLookup(() =>
      json(429, { error: { code: 'CEILING', message_key: 'error.unexpected', retryable: true } }),
    )
    renderScreen(<SignUp />)
    await fillForm()
    expect(await screen.findByText(/We sent a 6-digit code by SMS to/)).toBeInTheDocument()
    expect(lookups()).toEqual(['01711234567'])
    expect(called('/v1/accounts')).toHaveLength(1)
  })

  it('shows nothing when the server is unreachable', async () => {
    serveLookup(() => Promise.reject(new TypeError('Failed to fetch')))
    renderScreen(<SignUp />)
    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(lookups()).toHaveLength(1))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('lookup discipline', () => {
  it('never asks while the number is being typed, or about a malformed number', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
    expect(lookups()).toHaveLength(0)
    await typeNumberAndLeave('0171123')
    expect(lookups()).toHaveLength(0)
  })

  it('asks once per number, and again only for a different one', async () => {
    serveLookup(() => json(200, NOT_ADDED))
    renderScreen(<SignUp />)
    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(lookups()).toHaveLength(1))
    await userEvent.click(screen.getByLabelText('Mobile number'))
    await userEvent.tab()
    await typeNumberAndLeave('+8801711234567')
    await typeNumberAndLeave('01811234567')
    await waitFor(() => expect(lookups()).toEqual(['01711234567', '01811234567']))
  })

  it('never looks up an email address', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    await userEvent.type(screen.getByLabelText('Email address'), 'rina@example.com')
    await userEvent.tab()
    expect(lookups()).toHaveLength(0)
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it('drops the notice when the number is edited or email is chosen', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(screen.getByRole('status')).not.toBeEmptyDOMElement())
    await userEvent.type(screen.getByLabelText('Mobile number'), '8')
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(screen.getByRole('button', { name: 'Teacher' })).toBeEnabled()

    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(screen.getByRole('status')).not.toBeEmptyDOMElement())
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })
})

it('alreadyAddedFrom locks only on a yes that carries a role', () => {
  expect(alreadyAddedFrom({ already_added: true, display_name: '', role: 'guardian' })).toBe(
    'guardian',
  )
  expect(alreadyAddedFrom({ already_added: false })).toBeNull()
  expect(alreadyAddedFrom({ already_added: true, display_name: '', role: null })).toBeNull()
})
