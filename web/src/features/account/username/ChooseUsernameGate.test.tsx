/**
 * The gate's own outcomes, test-after from functional-spec W4 step 6
 * [FR5.4] [NFR2.2]. Routing around the gate (before routes, lifting on
 * a read) is `session/usernameGate.routing.test.tsx`.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Me } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { saveTokens } from '../../../api/tokens'
import { I18nProvider, translate, translateMessage } from '../../../i18n/i18n'
import { json } from '../../../test/render'
import { SessionProvider } from '../../../session/session'
import { ChooseUsernameGate, gateRefusal } from './ChooseUsernameGate'

const en = (key: string) => translate('en', key)

const ME: Me = {
  self_name: 'Karim Uddin',
  phone: null,
  email: 'karim@example.com',
  has_password: false,
  username: null,
  username_required: true,
  lenses: [],
}

type Answer = (body: unknown) => Response | Promise<Response>
let putAnswer: Answer = () => json(200, { username: 'nadia_k', next_change_at: null })
const puts: unknown[] = []

beforeEach(() => {
  puts.length = 0
  saveTokens({ access_token: 'A', refresh_token: 'R', expires_in: 900 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const body = init.body ? JSON.parse(init.body as string) : undefined
      if (url.endsWith('/v1/me/username') && init.method === 'PUT') {
        puts.push(body)
        return putAnswer(body)
      }
      if (url.endsWith('/v1/me')) return json(200, ME)
      return json(200, { status: 'available' })
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.removeItem('sp.session')
  putAnswer = () => json(200, { username: 'nadia_k', next_change_at: null })
})

const refusal =
  (status: number, key: string, retryable = false) =>
  () =>
    json(status, { error: { code: 'REFUSED', message_key: key, retryable } })

function renderGate() {
  return render(
    <I18nProvider lang="en">
      <SessionProvider>
        <MemoryRouter>
          <ChooseUsernameGate me={ME} />
        </MemoryRouter>
      </SessionProvider>
    </I18nProvider>,
  )
}

const field = () => screen.getByLabelText(en('signup_username_label'))
const continueButton = () => screen.getByRole('button', { name: en('choose_username_continue') })

async function choose(name = 'nadia_k') {
  await userEvent.type(field(), name)
  await userEvent.click(continueButton())
}

describe('ChooseUsernameGate', () => {
  it('puts focus on the username field when it mounts', () => {
    renderGate()
    expect(document.activeElement).toBe(field())
    expect(field()).toHaveAttribute('autocomplete', 'username')
  })

  it('sends the trimmed choice with no password key', async () => {
    renderGate()
    await choose('  Nadia_K ')
    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0]).toEqual({ username: 'Nadia_K' })
  })

  it('a blank choice sends nothing and says so under the field', async () => {
    renderGate()
    await userEvent.type(field(), '   ')
    await userEvent.click(continueButton())
    expect(screen.getByText(en('signup_username_required'))).toHaveAttribute('role', 'alert')
    expect(puts).toHaveLength(0)
  })

  it.each(['account.username.invalid_character', 'account.username.unavailable'])(
    '%s lands under the field, with the name kept',
    async (key) => {
      putAnswer = refusal(key.endsWith('unavailable') ? 409 : 400, key)
      renderGate()
      await choose('nadia k')
      const error = await screen.findByText(translateMessage('en', key))
      expect(error).toHaveAttribute('id', 'gate-username-error')
      expect(field()).toHaveAttribute('aria-invalid', 'true')
      expect(field()).toHaveValue('nadia k')
      expect(document.querySelector('.banner.error')).toBeNull()
    },
  )

  it('a 429 goes in the banner, with Continue available and no Retry', async () => {
    putAnswer = refusal(429, 'auth.lookup.too_many')
    renderGate()
    await choose()
    expect(await screen.findByText(translateMessage('en', 'auth.lookup.too_many'))).toBeVisible()
    expect(continueButton()).toBeEnabled()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
  })

  it.each([
    ['a 503', () => refusal(503, 'error.temporarily_unavailable', true)()],
    ['no connection', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('%s offers Retry, which resends the same choice', async (_name, failOnce) => {
    let first = true
    putAnswer = () => {
      if (first) {
        first = false
        return failOnce()
      }
      return json(200, { username: 'nadia_k', next_change_at: null })
    }
    renderGate()
    await choose('nadia_k')
    const retry = await screen.findByRole('button', { name: en('auth_retry') })
    await userEvent.clear(field())
    await userEvent.type(field(), 'something_else')
    await userEvent.click(retry)
    await waitFor(() => expect(puts).toHaveLength(2))
    expect(puts[1]).toEqual(puts[0])
    expect(puts[1]).toEqual({ username: 'nadia_k' })
  })

  it('a second press while the choice is in flight sends nothing more', async () => {
    let release: (r: Response) => void = () => undefined
    putAnswer = () =>
      new Promise<Response>((resolve) => {
        release = resolve
      })
    renderGate()
    await choose()
    expect(continueButton()).toBeDisabled()
    await userEvent.click(continueButton())
    await userEvent.type(field(), '{Enter}')
    expect(puts).toHaveLength(1)
    release(json(200, { username: 'nadia_k', next_change_at: null }))
  })

  it('Sign out is a real button', () => {
    renderGate()
    const signOut = screen.getByRole('button', { name: en('choose_username_sign_out') })
    expect(signOut.tagName).toBe('BUTTON')
    expect(signOut).toHaveAttribute('type', 'button')
  })
})

describe('gateRefusal', () => {
  const err = (key: string, retryable = false, status = 400) =>
    new ApiError(status, 'X', key, retryable)

  it('re-reads on password_required: another tab or device chose first', () => {
    expect(gateRefusal(err('account.username.password_required'), 't')).toEqual({ next: 'reread' })
  })

  it('offers Retry for a retryable or offline refusal only', () => {
    expect(gateRefusal(err('error.temporarily_unavailable', true, 503), 't')).toMatchObject({
      state: { retry: 'save', field: null },
    })
    expect(
      gateRefusal(new ApiError(0, 'NETWORK', 'error.network.unreachable', true), 't'),
    ).toMatchObject({ state: { retry: 'save' } })
    expect(gateRefusal(err('auth.lookup.too_many', false, 429), 't')).toMatchObject({
      state: { retry: null, field: null },
    })
  })
})
