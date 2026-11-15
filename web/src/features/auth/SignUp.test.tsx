/**
 * Creating an account against a mocked API: the form with a password,
 * the code, then the password set with the token the code bought.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { translate, translateMessage } from '../../i18n/i18n'
import { json, renderScreen } from '../../test/render'
import { alreadyAddedFrom, isUsernameKey, SignUp } from './SignUp'

const en = (key: string, ...args: string[]) => translate('en', key, ...args)

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

const USERNAME = 'Rahim.Uddin'

async function fillForm({
  email,
  username = USERNAME,
  password = PASSWORD,
  confirm = password,
}: { email?: string; username?: string; password?: string; confirm?: string } = {}) {
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
  if (username) await userEvent.type(screen.getByLabelText(en('signup_username_label')), username)
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

  await fillForm()
  const sent = await screen.findByText(/We sent a 6-digit code by SMS to/)
  expect(sent).toHaveTextContent('01711-234567')
  // The password is not sent with the account, and not kept anywhere.
  expect(bodyOf('/v1/accounts')).toEqual({
    role: 'teacher',
    self_name: 'Rina Akter',
    username: USERNAME,
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

it('files the password under the chosen username on the password step [W9, § 7]', async () => {
  serve(() => refusal(400, 'auth.password.too_common', 'VALIDATION'))
  renderScreen(<SignUp />)
  await fillForm()
  await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
  await screen.findByLabelText('New password')
  const hidden = document.querySelector<HTMLInputElement>('input[name="username"][hidden]')
  expect(hidden?.value).toBe(USERNAME)
  expect(hidden).toHaveAttribute('autocomplete', 'username')
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
const emailLookups = () =>
  fetchMock.mock.calls
    .map(([u]) => new URL(u as string, 'http://x'))
    .filter((u) => u.pathname === '/v1/accounts/already-added' && u.searchParams.has('email'))
    .map((u) => u.searchParams.get('email'))

/** Serve the lookup with `answer`, and everything else as `serve()` does. */
function serveLookup(answer: () => Response | Promise<Response>) {
  serve()
  const rest = fetchMock.getMockImplementation()!
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    new URL(url, 'http://x').pathname === '/v1/accounts/already-added' ? answer() : rest(url, init),
  )
}

/** The already-added notice's live region (the username hint is another). */
const notice = () => screen.getByTestId('signup-already-added')

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

    const status = notice()
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
    expect(notice()).toBeEmptyDOMElement()
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
    expect(notice()).toBeEmptyDOMElement()
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

  // Rewritten from W9 (was "never looks up an email address"): teachers
  // now record students by email, so an address is looked up as a number is.
  it('looks up a well-formed email once per value, and locks the role on a seat [FR6.7]', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    const email = screen.getByLabelText('Email address')
    await userEvent.type(email, 'Rina@Example.com')
    await userEvent.tab()
    await waitFor(() => expect(notice()).toHaveTextContent("You've been added already"))
    expect(emailLookups()).toEqual(['rina@example.com'])
    expect(lookups()).toEqual([null])
    expect(screen.getByRole('button', { name: 'Student' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Teacher' })).toBeDisabled()
    // Leaving the same value again asks nothing more.
    await userEvent.click(email)
    await userEvent.tab()
    expect(emailLookups()).toHaveLength(1)
  })

  it('never looks up a malformed email address', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    await userEvent.type(screen.getByLabelText('Email address'), 'rina@example')
    await userEvent.tab()
    expect(emailLookups()).toHaveLength(0)
    expect(notice()).toBeEmptyDOMElement()
  })

  it('an email lookup that fails shows nothing and never blocks Send code', async () => {
    serveLookup(() => Promise.reject(new TypeError('Failed to fetch')))
    renderScreen(<SignUp />)
    await fillForm({ email: 'rina@example.com' })
    expect(await screen.findByText(/We sent a 6-digit code by email to/)).toBeInTheDocument()
    expect(emailLookups()).toEqual(['rina@example.com'])
    expect(screen.queryByText("You've been added already")).toBeNull()
  })

  it('drops a late answer about an address the person has since changed', async () => {
    let release: (r: Response) => void = () => undefined
    serveLookup(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    renderScreen(<SignUp />)
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    const email = screen.getByLabelText('Email address')
    await userEvent.type(email, 'rina@example.com')
    await userEvent.tab()
    await userEvent.type(email, 'x')
    release(json(200, ADDED))
    await waitFor(() => expect(emailLookups()).toHaveLength(1))
    expect(notice()).toBeEmptyDOMElement()
    expect(screen.getByRole('button', { name: 'Teacher' })).toBeEnabled()
  })

  it('restores the person’s own pick when the lock no longer applies', async () => {
    // The first number was added as a student; the second was not.
    let asked = 0
    serveLookup(() => json(200, asked++ === 0 ? ADDED : NOT_ADDED))
    renderScreen(<SignUp />)
    await userEvent.click(screen.getByRole('button', { name: 'Teacher' }))
    await typeNumberAndLeave('01711234567')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Student' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    )

    await typeNumberAndLeave('01811234567')
    await waitFor(() => expect(lookups()).toHaveLength(2))
    expect(screen.getByRole('button', { name: 'Teacher' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Student' })).toHaveAttribute('aria-pressed', 'false')

    await userEvent.type(screen.getByLabelText('Full name'), 'Rina Akter')
    await userEvent.type(screen.getByLabelText('House or flat'), '12')
    await userEvent.type(screen.getByLabelText('Road and area'), 'Road 4, Dhanmondi')
    await userEvent.type(screen.getByLabelText('City or district'), 'Dhaka')
    await userEvent.type(screen.getByLabelText('Postcode'), '1205')
    await userEvent.type(screen.getByLabelText(en('signup_username_label')), USERNAME)
    await userEvent.type(screen.getByLabelText('Password'), PASSWORD)
    await userEvent.type(screen.getByLabelText('Type the password again'), PASSWORD)
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    await waitFor(() => expect(called('/v1/accounts')).toHaveLength(1))
    expect(bodyOf('/v1/accounts')).toMatchObject({ role: 'teacher', phone: '01811234567' })
  })

  it('drops the notice when the number is edited or email is chosen', async () => {
    serveLookup(() => json(200, ADDED))
    renderScreen(<SignUp />)
    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(notice()).not.toBeEmptyDOMElement())
    await userEvent.type(screen.getByLabelText('Mobile number'), '8')
    expect(notice()).toBeEmptyDOMElement()
    expect(screen.getByRole('button', { name: 'Teacher' })).toBeEnabled()

    await typeNumberAndLeave('01711234567')
    await waitFor(() => expect(notice()).not.toBeEmptyDOMElement())
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    expect(notice()).toBeEmptyDOMElement()
  })
})

// ------------------------------------------------ username [FR2.1] W1

describe('the username field', () => {
  it('sends the username trimmed, as typed, casing kept', async () => {
    serve()
    renderScreen(<SignUp />)
    await fillForm({ username: '  Rahim.Uddin  ' })
    await waitFor(() => expect(called('/v1/accounts')).toHaveLength(1))
    expect(bodyOf('/v1/accounts').username).toBe('Rahim.Uddin')
  })

  it('a blank username blocks the submit with its own message under the field', async () => {
    serve()
    renderScreen(<SignUp />)
    await fillForm({ username: '' })
    const field = screen.getByLabelText(en('signup_username_label'))
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(en('signup_username_required'))).toHaveAttribute('role', 'alert')
    expect(called('/v1/accounts')).toHaveLength(0)
  })

  it('whitespace alone is blank', async () => {
    serve()
    renderScreen(<SignUp />)
    await fillForm({ username: '   ' })
    expect(screen.getByText(en('signup_username_required'))).toBeInTheDocument()
    expect(called('/v1/accounts')).toHaveLength(0)
  })

  it.each([
    [400, 'account.username.too_short'],
    [400, 'account.username.must_start_with_letter'],
    [400, 'account.username.reserved'],
    [409, 'account.username.unavailable'],
  ])('a %i %s lands under Username, and the rest of the form is kept', async (status, key) => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/v1/accounts') ? refusal(status, key, 'VALIDATION') : json(200, {}),
    )
    renderScreen(<SignUp />)
    await fillForm()
    const field = screen.getByLabelText(en('signup_username_label'))
    await waitFor(() => expect(field).toHaveAttribute('aria-invalid', 'true'))
    const alert = document.getElementById('su-username-error')
    expect(alert).toHaveAttribute('role', 'alert')
    expect(alert?.textContent).toBe(translateMessage('en', key))
    // Not in the banner, and every other field keeps its value.
    expect(document.querySelector('.banner.error')).toBeNull()
    expect(field).toHaveValue(USERNAME)
    expect(screen.getByLabelText('Full name')).toHaveValue('Rina Akter')
    expect(screen.getByLabelText('Mobile number')).toHaveValue('01711234567')
    expect(screen.getByLabelText('Postcode')).toHaveValue('1205')
  })

  it('any other refusal stays in the banner', async () => {
    fetchMock.mockImplementation(async () =>
      refusal(409, 'auth.otp.temporarily_unavailable', 'CONFLICT'),
    )
    renderScreen(<SignUp />)
    await fillForm()
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable')
    expect(screen.getByLabelText(en('signup_username_label'))).not.toHaveAttribute('aria-invalid')
  })

  it('puts the password manager on the username field, not on the contact', async () => {
    renderScreen(<SignUp />)
    const username = screen.getByLabelText(en('signup_username_label'))
    expect(username).toHaveAttribute('autocomplete', 'username')
    expect(username).toHaveAttribute('name', 'username')
    expect(username).toHaveAttribute('autocapitalize', 'none')
    expect(username).toHaveAttribute('spellcheck', 'false')
    const phone = screen.getByLabelText('Mobile number')
    expect(phone).toHaveAttribute('autocomplete', 'tel-national')
    expect(phone).not.toHaveAttribute('name', 'username')
    await userEvent.click(screen.getByRole('button', { name: 'Email' }))
    const email = screen.getByLabelText('Email address')
    expect(email).toHaveAttribute('autocomplete', 'email')
    expect(email).not.toHaveAttribute('name', 'username')
  })

  it.each([
    ['unavailable', () => json(200, { status: 'unavailable' }), 'account_username_unavailable'],
    ['could not check', () => Promise.reject(new TypeError('offline')), 'username_could_not_check'],
  ])(
    'submission is never gated on the hint: it goes through while the hint says %s [FR3.2]',
    async (_name, lookup, hintKey) => {
      serve()
      const rest = fetchMock.getMockImplementation()!
      fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
        url.endsWith('/v1/accounts/username-availability') ? lookup() : rest(url, init),
      )
      renderScreen(<SignUp />)
      await userEvent.type(screen.getByLabelText(en('signup_username_label')), USERNAME)
      expect(await screen.findByText(en(hintKey), {}, { timeout: 2000 })).toHaveAttribute(
        'role',
        'status',
      )
      await fillForm({ username: '' })
      await waitFor(() => expect(called('/v1/accounts')).toHaveLength(1))
      expect(bodyOf('/v1/accounts').username).toBe(USERNAME)
      // The name goes in the lookup's body, never its URL [NFR3.1].
      const [url, init] = called('/v1/accounts/username-availability')[0]!
      expect(new URL(url as string, 'http://x').search).toBe('')
      expect(JSON.parse((init as RequestInit).body as string)).toEqual({ username: USERNAME })
    },
  )

  it('isUsernameKey takes every account.username key and nothing else', () => {
    expect(isUsernameKey('account.username.unavailable')).toBe(true)
    expect(isUsernameKey('account.username.bad_dot')).toBe(true)
    expect(isUsernameKey('account.contact.taken')).toBe(false)
    expect(isUsernameKey('auth.lookup.too_many')).toBe(false)
  })
})

// ------------------------------------------- Replace [FR2.2] W2, § 3.2

describe('the Replace step', () => {
  type VerifyAnswer = (body: Record<string, unknown>) => Response
  let verifies: VerifyAnswer[] = []
  const verifyBodies = () => called('/v1/auth/verify').map((c) => JSON.parse(c[1].body as string))

  /** `/v1/auth/verify` answers in order; the last one repeats. */
  function serveVerify(...answers: VerifyAnswer[]) {
    verifies = answers
    serve()
    const rest = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/auth/verify')) {
        const body = JSON.parse(init.body as string) as Record<string, unknown>
        const answer = verifies.length > 1 ? verifies.shift()! : verifies[0]!
        return answer(body)
      }
      return rest(url, init)
    })
  }

  const taken: VerifyAnswer = () =>
    json(409, {
      error: {
        code: 'CONFLICT',
        message_key: 'account.username.unavailable',
        retryable: false,
        // Nothing from the response beyond its key is ever shown [NFR1.4].
        details: { holder: 'someone_else_entirely' },
      },
    })
  const setup: VerifyAnswer = () => json(200, SETUP)
  const otp =
    (key: string): VerifyAnswer =>
    () =>
      refusal(400, key, 'OTP_NOT_VALID')

  async function toReplace(code = '123456') {
    renderScreen(<SignUp />)
    await fillForm()
    await userEvent.type(await screen.findByLabelText('Enter the code'), code)
    return screen.findByTestId('replace-username')
  }

  const replaceField = () => screen.getByLabelText(en('signup_username_label'))
  const continueReplace = () =>
    screen.getByRole('button', { name: en('auth_replace_username_continue') })

  async function replaceWith(name: string) {
    await userEvent.type(replaceField(), name)
    await userEvent.click(continueReplace())
  }

  afterEach(() => {
    vi.useRealTimers()
  })

  it('a 409 opens Replace, and the code step never shows it', async () => {
    serveVerify(taken, setup)
    const step = await toReplace()
    expect(step).toBeInTheDocument()
    expect(screen.queryByLabelText('Enter the code')).toBeNull()
    expect(screen.queryByText(translateMessage('en', 'account.username.unavailable'))).toBeNull()
    expect(document.activeElement).toBe(replaceField())
  })

  it('the body names the W1 username and nothing from the response', async () => {
    serveVerify(taken, setup)
    await toReplace()
    const body = screen.getByTestId('replace-username-body')
    expect(body).toHaveTextContent(en('auth_replace_username_body', USERNAME))
    expect(document.body.textContent).not.toContain('someone_else_entirely')
  })

  it('the retry sends the same code with the replacement, and signs in', async () => {
    serveVerify(taken, setup)
    await toReplace('123456')
    await replaceWith('  rahim_math ')
    await waitFor(() => expect(readTokens()?.access).toBe('A'))
    expect(verifyBodies()).toEqual([
      { phone: '01711234567', code: '123456' },
      { phone: '01711234567', code: '123456', username: 'rahim_math' },
    ])
    expect(bodyOf('/v1/auth/password/setup')).toEqual({ token: 'SETUP-1', password: PASSWORD })
  })

  it('a refused replacement stays on Replace, under the field', async () => {
    serveVerify(taken, () => refusal(400, 'account.username.too_short', 'VALIDATION'))
    await toReplace()
    await replaceWith('ab')
    const error = await screen.findByText(translateMessage('en', 'account.username.too_short'))
    expect(error).toHaveAttribute('id', 'replace-username-error')
    expect(screen.getByTestId('replace-username')).toBeInTheDocument()
  })

  it('a 429 stays on Replace, in the banner, with Continue still offered', async () => {
    serveVerify(taken, () => refusal(429, 'auth.lookup.too_many', 'CEILING'))
    await toReplace()
    await replaceWith('rahim_math')
    expect(await screen.findByText(translateMessage('en', 'auth.lookup.too_many'))).toBeVisible()
    expect(continueReplace()).toBeEnabled()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
  })

  it('no connection stays on Replace, and Retry resends the same request', async () => {
    let first = true
    serveVerify(taken, (body) => {
      if (first) {
        first = false
        throw new TypeError('Failed to fetch')
      }
      return json(200, { ...SETUP, echoed: body.username })
    })
    await toReplace()
    await replaceWith('rahim_math')
    await userEvent.click(await screen.findByRole('button', { name: en('auth_retry') }))
    await waitFor(() => expect(readTokens()?.access).toBe('A'))
    const bodies = verifyBodies()
    expect(bodies).toHaveLength(3)
    expect(bodies[2]).toEqual(bodies[1])
  })

  it.each([
    [90, true, ''],
    [20, false, '0:40'],
  ])(
    'an expired code on the retry, sent %i s earlier, shows why with the field empty (Resend open: %s)',
    async (secondsAgo, open, countdown) => {
      vi.useFakeTimers({ toFake: ['Date'] })
      const sentAt = new Date('2026-11-15T10:00:00Z').getTime()
      vi.setSystemTime(sentAt)
      serveVerify(taken, otp('auth.otp.expired'))
      await toReplace()
      vi.setSystemTime(sentAt + secondsAgo * 1000)
      await replaceWith('rahim_math')
      const code = await screen.findByLabelText('Enter the code')
      expect(screen.getByRole('alert')).toHaveTextContent(
        translateMessage('en', 'auth.otp.expired'),
      )
      expect(code).toHaveValue('')
      expect(screen.queryByTestId('replace-username')).toBeNull()
      if (open) {
        expect(screen.getByRole('button', { name: en('auth_resend') })).toBeEnabled()
      } else {
        const resend = screen.getByRole('button', { name: en('auth_resend_in', countdown) })
        expect(resend).toBeDisabled()
      }
    },
  )

  it.each(['auth.otp.no_tries_left', 'auth.otp.not_valid'])(
    'after %s on the retry, the next verify sends only newly typed digits',
    async (key) => {
      serveVerify(taken, otp(key), setup)
      await toReplace('123456')
      await replaceWith('rahim_math')
      await userEvent.type(await screen.findByLabelText('Enter the code'), '654321')
      await waitFor(() => expect(readTokens()?.access).toBe('A'))
      const bodies = verifyBodies()
      expect(bodies[2]).toEqual({ phone: '01711234567', code: '654321' })
      expect(bodies[2]).not.toHaveProperty('username')
    },
  )

  it('after Back and a fresh 409, the retry sends the new digits, never the old ones', async () => {
    serveVerify(taken, taken, setup)
    await toReplace('111111')
    await userEvent.click(screen.getByRole('button', { name: en('web_auth_signup_back') }))
    // Back to the form: the held code and the held password are forgotten.
    await userEvent.type(screen.getByLabelText('Password'), PASSWORD)
    await userEvent.type(screen.getByLabelText('Type the password again'), PASSWORD)
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    await userEvent.type(await screen.findByLabelText('Enter the code'), '222222')
    await screen.findByTestId('replace-username')
    await replaceWith('rahim_math')
    await waitFor(() => expect(verifyBodies()).toHaveLength(3))
    expect(verifyBodies()[2]).toEqual({
      phone: '01711234567',
      code: '222222',
      username: 'rahim_math',
    })
  })
})

it('alreadyAddedFrom locks only on a yes that carries a role', () => {
  expect(alreadyAddedFrom({ already_added: true, display_name: '', role: 'guardian' })).toBe(
    'guardian',
  )
  expect(alreadyAddedFrom({ already_added: false })).toBeNull()
  expect(alreadyAddedFrom({ already_added: true, display_name: '', role: null })).toBeNull()
})
