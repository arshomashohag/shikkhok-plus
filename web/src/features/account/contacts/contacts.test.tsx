/**
 * Settings → Phone and email, signed in against a mocked API, test-after
 * from functional-spec W6 [FR8.1] [FR8.2] [FR8.3] [FR8.4] [NFR3.13].
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Me } from '../../../api/endpoints'
import { clearTokens } from '../../../api/tokens'
import { translate, translateMessage } from '../../../i18n/i18n'
import { json } from '../../../test/render'
import { mockSignedIn, renderRoutes, type Call } from '../../../test/signedIn'
import { securityRoutes } from '../security'
import { contactCards, contactsSummary } from './mappers'

const en = (key: string, ...args: string[]) => translate('en', key, ...args)

let me: Record<string, unknown>
let calls: Call[]
type Post = (body: Record<string, unknown>) => Response | Promise<Response>
let onContact: Post
let onVerify: Post
let onRemove: Post

const posts = (path: string) => calls.filter((c) => c.method === 'POST' && c.url.endsWith(path))
const meReads = () => calls.filter((c) => c.method === 'GET' && c.url.endsWith('/v1/me'))
const refusal = (status: number, key: string, retryable = false) =>
  json(status, { error: { code: 'REFUSED', message_key: key, retryable } })

beforeEach(() => {
  me = {
    username: 'nadia_k',
    phone: '+8801711234567',
    email: 'rina@example.com',
    has_password: true,
  }
  onContact = () => json(200, { status: 'requested' })
  onVerify = () => json(200, me)
  onRemove = () => json(200, me)
  calls = mockSignedIn(
    (method, url, body) => {
      if (method !== 'POST') return undefined
      const path = new URL(url, 'http://x').pathname
      const b = (body ?? {}) as Record<string, unknown>
      if (path === '/v1/me/contact') return onContact(b) as Response
      if (path === '/v1/me/contact/verify') return onVerify(b) as Response
      if (path === '/v1/me/contact/remove') return onRemove(b) as Response
      return undefined
    },
    'student',
    () => me,
  )
})
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

const card = (kind: 'phone' | 'email') => screen.getByTestId(`contact-card-${kind}`)

describe('contactCards', () => {
  const account = (patch: Partial<Me>): Me => ({
    has_password: true,
    username_required: false,
    phone: null,
    email: null,
    ...patch,
  })

  it('both present: phone first, formatted', () => {
    expect(contactCards(account({ phone: '+8801711234567', email: 'rina@example.com' }))).toEqual([
      { kind: 'phone', contact: '01711-234567' },
      { kind: 'email', contact: 'rina@example.com' },
    ])
  })

  it('phone only, and email only', () => {
    expect(contactCards(account({ phone: '+8801711234567' }))[1]).toEqual({
      kind: 'email',
      contact: null,
    })
    expect(contactCards(account({ email: 'rina@example.com' }))[0]).toEqual({
      kind: 'phone',
      contact: null,
    })
  })

  it('the Settings summary lists what is present, or is null for none', () => {
    expect(contactsSummary(account({ email: 'rina@example.com' }))).toBe('rina@example.com')
    expect(contactsSummary(account({}))).toBeNull()
  })
})

describe('the contacts screen', () => {
  it('both present: each card offers Replace and Remove', async () => {
    renderRoutes(securityRoutes, '/settings/contacts')
    expect(await screen.findByText('01711-234567')).toBeInTheDocument()
    expect(within(card('email')).getByText('rina@example.com')).toBeInTheDocument()
    for (const kind of ['phone', 'email'] as const) {
      expect(
        within(card(kind)).getByRole('link', { name: en('contacts_replace') }),
      ).toHaveAttribute('href', `/settings/contact/${kind}/replace`)
      expect(within(card(kind)).getByRole('button', { name: en('contacts_remove') })).toBeEnabled()
    }
  })

  it('one present contact still yields Remove: the client reads no count', async () => {
    me = { ...me, email: null }
    renderRoutes(securityRoutes, '/settings/contacts')
    await screen.findByText('01711-234567')
    expect(within(card('phone')).getByRole('button', { name: en('contacts_remove') })).toBeEnabled()
    expect(within(card('email')).getByText(en('contacts_no_email'))).toBeInTheDocument()
    expect(within(card('email')).getByRole('link', { name: 'Add email' })).toHaveAttribute(
      'href',
      '/settings/contact/email',
    )
  })

  it('email only: the phone card offers Add', async () => {
    me = { ...me, phone: null }
    renderRoutes(securityRoutes, '/settings/contacts')
    expect(await screen.findByText(en('contacts_no_phone'))).toBeInTheDocument()
    expect(within(card('phone')).getByRole('link', { name: 'Add phone number' })).toBeVisible()
  })

  it('has_password false shows the note, and every action stays enabled', async () => {
    me = { ...me, has_password: false }
    renderRoutes(securityRoutes, '/settings/contacts')
    const note = await screen.findByTestId('contacts-password-note')
    expect(note).toHaveTextContent(en('contacts_password_note'))
    expect(within(note).getByRole('link', { name: en('contacts_set_password') })).toHaveAttribute(
      'href',
      '/settings/password',
    )
    for (const b of screen.getAllByRole('button', { name: en('contacts_remove') }))
      expect(b).toBeEnabled()
  })
})

describe('replace', () => {
  async function request(value: string, password = 'correct horse') {
    await userEvent.type(await screen.findByLabelText(en('contacts_new_email_label')), value)
    await userEvent.type(screen.getByLabelText(en('web_password_current')), password)
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  }

  it('sends the new value with the password, then drops the password for the code step', async () => {
    renderRoutes(securityRoutes, '/settings/contact/email/replace')
    await request('New@Example.com')
    expect(await screen.findByText(en('contacts_code_sent_new_email'))).toBeInTheDocument()
    expect(posts('/v1/me/contact')[0]!.body).toEqual({
      email: 'new@example.com',
      password: 'correct horse',
    })
    // Change goes back with the value kept and the password gone.
    await userEvent.click(screen.getByRole('button', { name: 'Change' }))
    expect(screen.getByLabelText(en('contacts_new_email_label'))).toHaveValue('New@Example.com')
    expect(screen.getByLabelText(en('web_password_current'))).toHaveValue('')
  })

  it('verifies the code, re-reads, and returns to the contacts screen with the notice', async () => {
    renderRoutes(securityRoutes, '/settings/contact/email/replace')
    await request('new@example.com')
    const before = meReads().length
    await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
    expect(await screen.findByText(en('contacts_replaced_email'))).toBeInTheDocument()
    expect(posts('/v1/me/contact/verify')[0]!.body).toEqual({
      email: 'new@example.com',
      code: '123456',
    })
    await waitFor(() => expect(meReads().length).toBeGreaterThan(before))
  })

  it('a refusal of the code stays on the code step', async () => {
    onVerify = () => refusal(409, 'account.contact.taken')
    renderRoutes(securityRoutes, '/settings/contact/email/replace')
    await request('new@example.com')
    await userEvent.type(await screen.findByLabelText('Enter the code'), '123456')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      translateMessage('en', 'account.contact.taken'),
    )
    expect(screen.getByLabelText('Enter the code')).toBeInTheDocument()
  })

  it.each([
    ['account.contact.already_set', 'replace-contact-error'],
    ['auth.password.current_wrong', 'replace-password-error'],
  ])('%s from the request lands under its field', async (key, id) => {
    onContact = () => refusal(409, key)
    renderRoutes(securityRoutes, '/settings/contact/email/replace')
    await request('new@example.com')
    const error = await screen.findByText(translateMessage('en', key))
    expect(error).toHaveAttribute('id', id)
    expect(screen.getByLabelText(en('web_password_current'))).toHaveValue(
      key === 'auth.password.current_wrong' ? '' : 'correct horse',
    )
  })

  it.each(['account.contact.change_limit', 'account.contact.admin_locked'])(
    '%s from the request goes in the banner',
    async (key) => {
      onContact = () => refusal(409, key)
      renderRoutes(securityRoutes, '/settings/contact/email/replace')
      await request('new@example.com')
      expect(await screen.findByRole('alert')).toHaveTextContent(translateMessage('en', key))
    },
  )

  it('password_required goes in the banner with a link to set a password', async () => {
    onContact = () => refusal(409, 'account.contact.password_required')
    renderRoutes(securityRoutes, '/settings/contact/email/replace')
    await request('new@example.com')
    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: en('contacts_set_password') })).toHaveAttribute(
      'href',
      '/settings/password',
    )
  })

  it('no connection offers Retry, which resends the same request', async () => {
    let first = true
    onContact = () => {
      if (first) {
        first = false
        throw new TypeError('Failed to fetch')
      }
      return json(200, { status: 'requested' })
    }
    renderRoutes(securityRoutes, '/settings/contact/email/replace')
    await request('new@example.com')
    await userEvent.click(await screen.findByRole('button', { name: en('auth_retry') }))
    expect(await screen.findByText(en('contacts_code_sent_new_email'))).toBeInTheDocument()
    expect(posts('/v1/me/contact')[1]!.body).toEqual(posts('/v1/me/contact')[0]!.body)
  })
})

describe('remove', () => {
  async function openSheet(kind: 'phone' | 'email' = 'email') {
    renderRoutes(securityRoutes, '/settings/contacts')
    await screen.findByText('01711-234567')
    await userEvent.click(within(card(kind)).getByRole('button', { name: en('contacts_remove') }))
    return screen.findByTestId('remove-contact-sheet')
  }

  const sheetPassword = () => screen.getByLabelText(en('web_password_current'))
  const confirm = () =>
    within(screen.getByTestId('remove-contact-sheet')).getByRole('button', {
      name: en('contacts_remove_confirm'),
    })

  async function removeWith(password = 'correct horse') {
    await userEvent.type(sheetPassword(), password)
    await userEvent.click(confirm())
  }

  it('names the contact, focuses the password, and sends {kind, password}', async () => {
    const sheet = await openSheet()
    expect(sheet).toHaveTextContent(en('contacts_remove_body', 'rina@example.com'))
    expect(document.activeElement).toBe(sheetPassword())
    const before = meReads().length
    onRemove = () => {
      me = { ...me, email: null }
      return json(200, me)
    }
    await removeWith()
    await waitFor(() => expect(screen.queryByTestId('remove-contact-sheet')).toBeNull())
    expect(posts('/v1/me/contact/remove')[0]!.body).toEqual({
      kind: 'email',
      password: 'correct horse',
    })
    expect(new URL(posts('/v1/me/contact/remove')[0]!.url, 'http://x').search).toBe('')
    await waitFor(() => expect(meReads().length).toBeGreaterThan(before))
    expect(within(card('email')).getByText(en('contacts_removed'))).toBeInTheDocument()
    expect(await within(card('email')).findByText(en('contacts_no_email'))).toBeInTheDocument()
  })

  it('last_one shows in the sheet, with Add another for the other kind', async () => {
    onRemove = () => refusal(409, 'account.contact.last_one')
    await openSheet('email')
    await removeWith()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(translateMessage('en', 'account.contact.last_one'))
    expect(within(alert).getByRole('link', { name: en('contacts_add_other') })).toHaveAttribute(
      'href',
      '/settings/contact/phone',
    )
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
  })

  it('a wrong current password lands under the password, which is cleared', async () => {
    onRemove = () => refusal(400, 'auth.password.current_wrong')
    await openSheet()
    await removeWith()
    const error = await screen.findByText(translateMessage('en', 'auth.password.current_wrong'))
    expect(error).toHaveAttribute('id', 'remove-password-error')
    expect(sheetPassword()).toHaveValue('')
  })

  it('password_required goes in the sheet with a link to set a password', async () => {
    onRemove = () => refusal(409, 'account.contact.password_required')
    await openSheet()
    await removeWith()
    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: en('contacts_set_password') })).toBeVisible()
  })

  it('no connection offers Retry, which resends {kind, password}', async () => {
    let first = true
    onRemove = () => {
      if (first) {
        first = false
        throw new TypeError('Failed to fetch')
      }
      return json(200, me)
    }
    await openSheet('phone')
    await removeWith('correct horse')
    await userEvent.click(await screen.findByRole('button', { name: en('auth_retry') }))
    await waitFor(() => expect(posts('/v1/me/contact/remove')).toHaveLength(2))
    expect(posts('/v1/me/contact/remove')[1]!.body).toEqual({
      kind: 'phone',
      password: 'correct horse',
    })
  })

  it('reopening the sheet starts fresh', async () => {
    onRemove = () => refusal(400, 'auth.password.current_wrong')
    await openSheet()
    await removeWith()
    await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button', { name: en('action_cancel') }))
    await userEvent.click(
      within(card('email')).getByRole('button', { name: en('contacts_remove') }),
    )
    await screen.findByTestId('remove-contact-sheet')
    expect(screen.queryByRole('alert')).toBeNull()
    expect(sheetPassword()).toHaveValue('')
  })

  it('a typed password makes the sheet ask before closing', async () => {
    await openSheet()
    await userEvent.type(sheetPassword(), 'half typed')
    await userEvent.keyboard('{Escape}')
    expect(screen.getByTestId('remove-contact-sheet')).toBeInTheDocument()
  })
})
