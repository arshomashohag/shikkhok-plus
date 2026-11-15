/**
 * Settings → Username, signed in against a mocked API, test-after from
 * functional-spec W5 [FR7.1] [FR7.2] [FR7.5] [NFR3.13].
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens } from '../../../api/tokens'
import { formatDateTime } from '../../../core/format'
import { translate, translateMessage } from '../../../i18n/i18n'
import { json } from '../../../test/render'
import { mockSignedIn, renderRoutes, type Call } from '../../../test/signedIn'
import { securityRoutes } from '../security'

const en = (key: string, ...args: string[]) => translate('en', key, ...args)

let me: Record<string, unknown>
let calls: Call[]
let put: (body: Record<string, unknown>) => Response | Promise<Response>

const puts = () => calls.filter((c) => c.method === 'PUT' && c.url.endsWith('/v1/me/username'))
const meReads = () => calls.filter((c) => c.method === 'GET' && c.url.endsWith('/v1/me'))
const refusal = (status: number, key: string, retryable = false, details?: unknown) =>
  json(status, { error: { code: 'REFUSED', message_key: key, retryable, details } })

beforeEach(() => {
  me = { username: 'nadia_k', phone: '+8801711234567', email: null, has_password: true }
  put = () => json(200, { username: 'Nadia_K2', next_change_at: null })
  calls = mockSignedIn(
    (method, url, body) => {
      const path = new URL(url, 'http://x').pathname
      if (method === 'PUT' && path === '/v1/me/username')
        return put(body as Record<string, unknown>) as Response
      if (path === '/v1/me/username-availability') return json(200, { status: 'available' })
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

const open = () => renderRoutes(securityRoutes, '/settings/username')

async function change(username = 'Nadia_K2', password = 'correct horse') {
  await userEvent.click(await screen.findByRole('button', { name: en('username_change') }))
  await userEvent.type(screen.getByLabelText(en('username_new_label')), username)
  await userEvent.type(screen.getByLabelText(en('web_password_current')), password)
  await userEvent.click(screen.getByRole('button', { name: en('username_save') }))
}

describe('viewing', () => {
  it('shows the current username as stored, casing kept, and Change always', async () => {
    me = { ...me, username: 'Rahim.Uddin' }
    open()
    expect(await screen.findByTestId('username-current')).toHaveTextContent('Rahim.Uddin')
    // MeResponse carries no next_change_at: the client never decides [NFR3.13].
    expect(screen.getByRole('button', { name: en('username_change') })).toBeEnabled()
  })
})

describe('changing [W5 step 5]', () => {
  it('sends the name and the password in the body, then shows Changed and re-reads', async () => {
    open()
    const before = await waitFor(() => {
      expect(meReads().length).toBeGreaterThan(0)
      return meReads().length
    })
    await change()
    expect(await screen.findByText(en('username_changed'))).toBeInTheDocument()
    expect(puts()[0]!.body).toEqual({ username: 'Nadia_K2', password: 'correct horse' })
    expect(new URL(puts()[0]!.url, 'http://x').search).toBe('')
    await waitFor(() => expect(meReads().length).toBeGreaterThan(before))
  })

  it('says when it can change again, from next_change_at, formatted on the screen', async () => {
    const at = '2026-12-15T04:30:00Z'
    put = () => json(200, { username: 'Nadia_K2', next_change_at: at })
    open()
    await change()
    expect(
      await screen.findByText(en('username_changed_on', formatDateTime(at, 'en', true))),
    ).toBeInTheDocument()
    expect(document.body.textContent).not.toContain(at)
  })

  it('a change too soon shows the date from details.next_change_at', async () => {
    const at = '2026-12-01T00:00:00Z'
    put = () => refusal(409, 'account.username.change_too_soon', false, { next_change_at: at })
    open()
    await change()
    expect(
      await screen.findByText(
        en('account_username_change_too_soon_on', formatDateTime(at, 'en', true)),
      ),
    ).toBeInTheDocument()
  })

  it('a change too soon with no detail shows the plain string', async () => {
    put = () => refusal(409, 'account.username.change_too_soon')
    open()
    await change()
    expect(
      await screen.findByText(translateMessage('en', 'account.username.change_too_soon')),
    ).toBeInTheDocument()
  })

  it('password_required goes in the banner with a link to set a password', async () => {
    put = () => refusal(409, 'account.username.password_required')
    open()
    await change()
    const banner = await screen.findByRole('alert')
    expect(banner).toHaveTextContent(translateMessage('en', 'account.username.password_required'))
    expect(screen.getByRole('link', { name: en('contacts_set_password') })).toHaveAttribute(
      'href',
      '/settings/password',
    )
  })

  it('a wrong current password lands under the password, which is cleared', async () => {
    put = () => refusal(400, 'auth.password.current_wrong')
    open()
    await change()
    const error = await screen.findByText(translateMessage('en', 'auth.password.current_wrong'))
    expect(error).toHaveAttribute('id', 'rename-password-error')
    expect(screen.getByLabelText(en('web_password_current'))).toHaveValue('')
    expect(screen.getByLabelText(en('username_new_label'))).toHaveValue('Nadia_K2')
  })

  it('too many wrong passwords goes in the banner, with no Retry', async () => {
    put = () => refusal(429, 'auth.password.too_many_attempts')
    open()
    await change()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      translateMessage('en', 'auth.password.too_many_attempts'),
    )
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
  })

  it.each(['account.username.bad_dot', 'account.username.unavailable'])(
    '%s lands under the new username',
    async (key) => {
      put = () => refusal(key.endsWith('unavailable') ? 409 : 400, key)
      open()
      await change('nadia..k')
      const error = await screen.findByText(translateMessage('en', key))
      expect(error).toHaveAttribute('id', 'new-username-error')
    },
  )

  it('a 429 goes in the banner, and Save stays available', async () => {
    put = () => refusal(429, 'auth.lookup.too_many')
    open()
    await change()
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: en('username_save') })).toBeEnabled()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
  })

  it.each([
    ['a 503', () => refusal(503, 'error.temporarily_unavailable', true)],
    [
      'no connection',
      (): Response => {
        throw new TypeError('Failed to fetch')
      },
    ],
  ])('%s offers Retry, which resends the same request', async (_name, failOnce) => {
    let first = true
    put = () => {
      if (first) {
        first = false
        return failOnce()
      }
      return json(200, { username: 'Nadia_K2', next_change_at: null })
    }
    open()
    await change()
    await userEvent.click(await screen.findByRole('button', { name: en('auth_retry') }))
    expect(await screen.findByText(en('username_changed'))).toBeInTheDocument()
    expect(puts()).toHaveLength(2)
    expect(puts()[1]!.body).toEqual(puts()[0]!.body)
  })

  it('a second press while the change is in flight sends nothing more', async () => {
    let release: (r: Response) => void = () => undefined
    put = () =>
      new Promise<Response>((resolve) => {
        release = resolve
      })
    open()
    await change()
    expect(screen.getByRole('button', { name: en('username_save') })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: en('username_save') }))
    expect(puts()).toHaveLength(1)
    release(json(200, { username: 'Nadia_K2', next_change_at: null }))
    expect(await screen.findByText(en('username_changed'))).toBeInTheDocument()
  })

  it('the hint asks as the signed-in account, in the body', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: en('username_change') }))
    await userEvent.type(screen.getByLabelText(en('username_new_label')), 'Nadia_K2')
    expect(await screen.findByText(en('username_available'), {}, { timeout: 2000 })).toBeVisible()
    const lookup = calls.find((c) => c.url.endsWith('/v1/me/username-availability'))!
    expect(lookup.body).toEqual({ username: 'Nadia_K2' })
    expect(lookup.headers.Authorization).toMatch(/^Bearer /)
  })

  it('Cancel drops the typed password', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: en('username_change') }))
    await userEvent.type(screen.getByLabelText(en('web_password_current')), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: en('action_cancel') }))
    await userEvent.click(screen.getByRole('button', { name: en('username_change') }))
    expect(screen.getByLabelText(en('web_password_current'))).toHaveValue('')
    expect(puts()).toHaveLength(0)
  })
})
