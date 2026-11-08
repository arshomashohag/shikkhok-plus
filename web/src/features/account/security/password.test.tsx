/**
 * Signed in, against a mocked API: the prompt to set a first password,
 * setting and changing it from Settings, and adding the phone number or
 * email address the account lacks.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../../api/tokens'
import { json } from '../../../test/render'
import { mockSignedIn, renderRoutes, type Call } from '../../../test/signedIn'
import { AccountEntries } from './AccountEntries'
import { PasswordPrompt } from './PasswordPrompt'
import { securityRoutes } from './index'

const NEW_PAIR = { access_token: 'A-NEW', refresh_token: 'R-NEW', expires_in: 900 }

let me: Record<string, unknown>
let calls: Call[]
const posts = (path: string) => calls.filter((c) => c.method === 'POST' && c.url.endsWith(path))
const meReads = () => calls.filter((c) => c.method === 'GET' && c.url.endsWith('/v1/me'))

const refusal = (status: number, key: string, code = 'REFUSED') =>
  json(status, { error: { code, message_key: key, retryable: false } })

function serve(handler: (path: string, body: Record<string, unknown>) => Response | undefined) {
  calls = mockSignedIn(
    (method, url, body) =>
      method === 'POST'
        ? handler(new URL(url, 'http://x').pathname, (body ?? {}) as Record<string, unknown>)
        : undefined,
    'student',
    () => me,
  )
}

const HOME = { path: '/home', element: <PasswordPrompt /> }
const ENTRIES = {
  path: '/entries',
  element: (
    <ul>
      <AccountEntries />
    </ul>
  ),
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  me = { phone: '+8801711234567', email: null, has_password: false }
})
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

describe('the prompt to set a password', () => {
  it('shows, with no way to dismiss it, while the account has no password', async () => {
    serve(() => undefined)
    renderRoutes([HOME], '/home')
    expect(await screen.findByRole('heading', { name: 'Set a password' })).toBeInTheDocument()
    expect(screen.getByText('Set a password so you can log in without a code.')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Set a password' })).toHaveAttribute(
      'href',
      '/settings/password',
    )
    expect(screen.queryByRole('button', { name: 'Not now' })).toBeNull()
  })

  it('is absent once the account has one, and when an older server does not say', async () => {
    me = { phone: '+8801711234567', has_password: true }
    serve(() => undefined)
    const { unmount } = renderRoutes([HOME], '/home')
    await waitFor(() => expect(meReads().length).toBeGreaterThan(0))
    expect(screen.queryByRole('heading', { name: 'Set a password' })).toBeNull()
    unmount()

    me = { phone: '+8801711234567' }
    serve(() => undefined)
    renderRoutes([HOME], '/home')
    await waitFor(() => expect(meReads().length).toBeGreaterThan(0))
    expect(screen.queryByRole('heading', { name: 'Set a password' })).toBeNull()
  })
})

describe('setting and changing the password', () => {
  it('sets a first password and keeps the new token pair', async () => {
    serve((path, body) => {
      if (path !== '/v1/me/password') return undefined
      me = { ...me, has_password: true }
      expect(body).toEqual({ new_password: 'a new long password' })
      return json(200, NEW_PAIR)
    })
    renderRoutes(securityRoutes, '/settings/password')
    expect(await screen.findByRole('heading', { name: 'Set a password' })).toBeInTheDocument()
    // No current password for an account that has none.
    expect(screen.queryByLabelText('Current password')).toBeNull()
    const field = screen.getByLabelText('New password')
    expect(field).toHaveAttribute('autocomplete', 'new-password')

    await userEvent.type(field, 'a new long password')
    await userEvent.type(screen.getByLabelText('Type the password again'), 'a new long password')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/settings')
    // Every session ended on the server: this one carries on with the new pair.
    expect(readTokens()?.access).toBe('A-NEW')
    expect(readTokens()?.refresh).toBe('R-NEW')
    expect(posts('/v1/me/password')).toHaveLength(1)
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(
      'a new long password',
    )
  })

  it('changes it with the current one, and says a wrong current one is wrong', async () => {
    me = { ...me, has_password: true }
    serve((path, body) => {
      if (path !== '/v1/me/password') return undefined
      if (body.current_password !== 'old password')
        return refusal(400, 'auth.password.current_wrong', 'PASSWORD_NOT_VALID')
      return json(200, NEW_PAIR)
    })
    renderRoutes(securityRoutes, '/settings/password')
    const current = await screen.findByLabelText('Current password')
    expect(current).toHaveAttribute('autocomplete', 'current-password')
    expect(current).toHaveAttribute('type', 'password')

    await userEvent.type(current, 'not it at all')
    await userEvent.type(screen.getByLabelText('New password'), 'a new long password')
    await userEvent.type(screen.getByLabelText('Type the password again'), 'a new long password')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("That isn't your current password.")
    expect(readTokens()?.access).toBe('A')

    await userEvent.type(screen.getByLabelText('Current password'), 'old password')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/settings')
    expect(readTokens()?.access).toBe('A-NEW')
    expect(posts('/v1/me/password').at(-1)!.body).toEqual({
      current_password: 'old password',
      new_password: 'a new long password',
    })
  })

  it('shows a refused new password under its field, and checks length first', async () => {
    serve((path) =>
      path === '/v1/me/password'
        ? refusal(400, 'auth.password.too_common', 'VALIDATION')
        : undefined,
    )
    renderRoutes(securityRoutes, '/settings/password')
    const field = await screen.findByLabelText('New password')
    await userEvent.type(field, 'short')
    await userEvent.type(screen.getByLabelText('Type the password again'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Use at least 8 characters.')
    expect(posts('/v1/me/password')).toHaveLength(0)

    await userEvent.type(field, 'word123')
    await userEvent.type(screen.getByLabelText('Type the password again'), 'word123')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That password is too common')
    expect(readTokens()?.access).toBe('A')
  })
})

describe('the settings rows', () => {
  it('offer setting a password and adding a phone to an email-only account', async () => {
    me = { phone: null, email: 'rina@example.com', has_password: false }
    serve(() => undefined)
    renderRoutes([ENTRIES], '/entries')
    expect(await screen.findByRole('link', { name: /Set a password/ })).toHaveAttribute(
      'href',
      '/settings/password',
    )
    const phone = screen.getByRole('link', { name: /Add phone number/ })
    expect(phone).toHaveAttribute('href', '/settings/contact/phone')
    expect(phone).toHaveTextContent('Teachers find students and guardians by their mobile number.')
    expect(screen.queryByRole('link', { name: /Add email/ })).toBeNull()
  })

  it('offer changing the password and adding an email to a phone account', async () => {
    me = { phone: '+8801711234567', email: null, has_password: true }
    serve(() => undefined)
    renderRoutes([ENTRIES], '/entries')
    expect(await screen.findByRole('link', { name: /Change password/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Add email/ })).toHaveAttribute(
      'href',
      '/settings/contact/email',
    )
    expect(screen.queryByRole('link', { name: /Add phone number/ })).toBeNull()
  })
})

describe('adding a phone number or email address', () => {
  it('adds a phone with a code, then reads the account again', async () => {
    me = { phone: null, email: 'rina@example.com', has_password: true }
    serve((path) => {
      if (path === '/v1/me/contact') return json(200, { status: 'requested' })
      if (path === '/v1/me/contact/verify') {
        me = { ...me, phone: '+8801711234567' }
        return json(200, { ...me, lenses: [{ kind: 'student', count: 2 }] })
      }
      return undefined
    })
    renderRoutes(securityRoutes, '/settings/contact/phone')
    const field = await screen.findByLabelText('Mobile number')
    expect(field).toHaveAttribute('type', 'tel')
    expect(field).toHaveAttribute('inputmode', 'tel')
    expect(
      screen.getByText(/Teachers find students and guardians by their mobile number/),
    ).toBeVisible()

    await userEvent.type(field, '01711-234567')
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    expect(await screen.findByText(/We sent a 6-digit code by SMS to/)).toBeInTheDocument()
    expect(posts('/v1/me/contact')[0]!.body).toEqual({ phone: '01711234567' })
    const readsBefore = meReads().length

    await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
    expect(await screen.findByTestId('where')).toHaveTextContent('/settings')
    expect(posts('/v1/me/contact/verify')[0]!.body).toEqual({
      phone: '01711234567',
      code: '123456',
    })
    // Seats a teacher recorded for that number may now be this account's.
    await waitFor(() => expect(meReads().length).toBeGreaterThan(readsBefore))
  })

  it('adds an email address', async () => {
    serve((path) => {
      if (path === '/v1/me/contact') return json(200, { status: 'requested' })
      if (path === '/v1/me/contact/verify') return json(200, { ...me, email: 'rina@example.com' })
      return undefined
    })
    renderRoutes(securityRoutes, '/settings/contact/email')
    const field = await screen.findByLabelText('Email address')
    expect(field).toHaveAttribute('type', 'email')
    expect(field).toHaveAttribute('autocomplete', 'email')
    await userEvent.type(field, 'Rina@Example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
    expect(await screen.findByTestId('where')).toHaveTextContent('/settings')
    expect(posts('/v1/me/contact/verify')[0]!.body).toEqual({
      email: 'rina@example.com',
      code: '123456',
    })
  })

  it('says when another account already uses the number', async () => {
    serve((path) =>
      path === '/v1/me/contact' ? refusal(409, 'account.contact.taken', 'CONFLICT') : undefined,
    )
    renderRoutes(securityRoutes, '/settings/contact/phone')
    await userEvent.type(await screen.findByLabelText('Mobile number'), '01711234567')
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Another account already uses this.')
    expect(screen.queryByLabelText('Enter the code')).toBeNull()
  })

  it('says when the account already has one', async () => {
    serve((path) => {
      if (path === '/v1/me/contact') return json(200, { status: 'requested' })
      if (path === '/v1/me/contact/verify')
        return refusal(409, 'account.contact.already_set', 'CONFLICT')
      return undefined
    })
    renderRoutes(securityRoutes, '/settings/contact/email')
    await userEvent.type(await screen.findByLabelText('Email address'), 'rina@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This account already has one. It cannot be added twice.',
    )
    expect(screen.queryByTestId('where')).toBeNull()
  })

  it('refuses a malformed email address without calling the server', async () => {
    serve(() => undefined)
    renderRoutes(securityRoutes, '/settings/contact/email')
    await userEvent.type(await screen.findByLabelText('Email address'), 'not-an-address')
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('name@example.com')
    expect(posts('/v1/me/contact')).toHaveLength(0)
  })
})
