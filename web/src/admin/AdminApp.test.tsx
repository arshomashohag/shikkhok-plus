/**
 * The admin app's gate: signed out it shows log-in, a 401 from any call
 * takes the administrator back there, and log-in returns them to the
 * screen they were on.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../i18n/i18n'
import { json } from '../test/render'
import { safeReturnPath } from './AdminApp'
import './strings'
import { peekAdminSession, resetAdminSessionForTests, SESSION_KEY } from './session'
import { renderAdmin, serveAdmin, type Handler } from './test/renderAdmin'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)

const expired = json(401, {
  error: { code: 'NOT_AUTHENTICATED', message_key: 'auth.token.not_valid', retryable: false },
})

const ticket = {
  ticket: {
    ticket_id: 't1',
    subject: 'Fee not showing',
    status: 'open',
    platform: 'android',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    message_count: 1,
    preview: 'p',
    requester: { ref: 'a1b2c3d4e5', roles: ['student'] },
  },
  messages: [
    {
      message_id: 'm1',
      author: 'requester',
      body: 'Where is my fee?',
      created_at: '2026-11-01T00:00:00Z',
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetAdminSessionForTests()
  sessionStorage.clear()
})

describe('the gate', () => {
  it('sends a signed-out visit to log-in, and makes no admin call', async () => {
    const calls = serveAdmin(() => undefined, false)
    renderAdmin('/help/tickets?status=open')
    expect(await screen.findByText(en('web_admin_signin_title'))).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/signin')
    expect(calls).toHaveLength(0)
  })

  it('a 401 ends the session and returns to log-in, then back to the same screen', async () => {
    const user = userEvent.setup()
    let signedInAgain = false
    const handler: Handler = (_m, url) => {
      if (url === '/v1/admin/help/tickets/t1') return signedInAgain ? json(200, ticket) : expired
      if (url === '/v1/admin/auth/otp') return json(200, {})
      if (url === '/v1/admin/auth/verify')
        return json(200, { challenge: 'CH', expires_in: 300, stage: 'verify', enrollment: null })
      if (url === '/v1/admin/auth/mfa') {
        signedInAgain = true
        return json(200, { access_token: 'FRESH', expires_in: 3600 })
      }
      return undefined
    }
    serveAdmin(handler)
    renderAdmin('/help/tickets/t1')

    expect(await screen.findByText(en('web_admin_session_ended'))).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/signin')
    expect(peekAdminSession()).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()

    await user.type(screen.getByLabelText(en('auth_phone_label')), '01711234567')
    await user.click(screen.getByRole('button', { name: en('auth_request_code') }))
    await user.type(await screen.findByLabelText(en('auth_code_label')), '123456')
    await user.type(await screen.findByLabelText(en('web_admin_verify_code_label')), '111222')

    expect(await screen.findByText('Where is my fee?')).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/help/tickets/t1')
  })

  it('a token that lapses while the tab is open goes back to log-in by itself', async () => {
    serveAdmin(() => json(200, {}), false)
    sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ access: 'OLD', expiresAt: Date.now() + 50 }),
    )
    renderAdmin('/teachers')
    expect(await screen.findByText(en('web_admin_session_ended'))).toBeInTheDocument()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  })

  it('shows until when the session lasts, and Log out ends it', async () => {
    const user = userEvent.setup()
    serveAdmin(() => json(200, { workspaces: [] }))
    renderAdmin('/teachers')
    expect(await screen.findByText(/^Signed in until \d\d:\d\d$/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: en('more_log_out') }))
    expect(await screen.findByText(en('web_admin_signed_out'))).toBeInTheDocument()
    expect(peekAdminSession()).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  })

  it('a signed-in visit to /signin goes on to the dashboard', async () => {
    serveAdmin((_m, url) => (url === '/v1/admin/overview' ? undefined : undefined))
    renderAdmin('/signin')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/))
  })
})

describe('safeReturnPath', () => {
  it('returns only to a path inside the app', () => {
    expect(safeReturnPath('/help/tickets?status=open')).toBe('/help/tickets?status=open')
    expect(safeReturnPath('//evil.example/x')).toBe('/')
    expect(safeReturnPath('https://evil.example/')).toBe('/')
    expect(safeReturnPath('/signin')).toBe('/')
    expect(safeReturnPath(undefined)).toBe('/')
  })
})
