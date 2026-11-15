/**
 * Nothing typed is persisted, put in route state, titled, put in the page
 * URL or logged [NFR3.2] [NFR3.3] [NFR3.4] [NFR3.6] [functional-spec § 7
 * Sensitive data].
 *
 * It drives the real `App` under `BrowserRouter`, as `src/main.tsx` does
 * [TSD-4] — the shared helpers' `MemoryRouter` never writes
 * `window.history`, so a `history.state` snapshot there would pass
 * whatever the code did. The flows: sign-in (and on to the code flow),
 * sign-up through a 409 and Replace, the choose-username gate, and
 * rename, each with one distinctive sentinel per value. After every step
 * it snapshots every `localStorage` and `sessionStorage` value,
 * `history.state`, `document.title`, `location.href` and every argument
 * to a spied `console` method, and fails if any sentinel appears; and it
 * fails if `indexedDB.open` was ever called.
 *
 * Non-vacuity, two controls: the sentinels are first shown to have
 * reached the request bodies, and after the first navigation
 * `history.state` holds the router's entry (a numeric `idx`).
 *
 * The one URL exception is U2's already-added lookup (`?phone=`,
 * `?email=`), a request URL, not the page's; this test checks the page.
 */
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import { I18nProvider, translate } from '../i18n/i18n'
import { PwaProvider } from '../pwa/pwa'
import { SessionProvider } from '../session/session'
import { json } from './render'

const en = (key: string) => translate('en', key)

const SENTINEL = {
  username: 'sentinel_user_7',
  login: 'sentinel_login_9',
  phone: '+8801999999999',
  email: 'sentinel@example.invalid',
  password: 'sentinel-pass',
  code: '918273',
} as const

/** Every form a sentinel could take once the app has handled it. */
const FORBIDDEN = [
  ...Object.values(SENTINEL),
  '01999999999', // the phone, normalised
  '01999-999999', // the phone, formatted
  encodeURIComponent(SENTINEL.email),
  encodeURIComponent(SENTINEL.phone),
]

const CONSOLE = ['log', 'info', 'warn', 'error', 'debug'] as const

let logged: unknown[][] = []
let bodies: string[] = []
let meAnswers: Record<string, unknown>[] = []
let verifyAnswers: (() => Response)[] = []
const indexedDbOpen = vi.fn()

const SETUP = {
  access_token: null,
  refresh_token: null,
  expires_in: null,
  mfa_required: false,
  password_setup_token: 'SETUP-1',
  password_setup_expires_in: 600,
}

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const path = new URL(url, 'http://x').pathname
      if (typeof init.body === 'string') bodies.push(init.body)
      const refuse = (status: number, key: string) =>
        json(status, { error: { code: 'REFUSED', message_key: key, retryable: false } })
      if (path === '/v1/auth/password') return refuse(400, 'auth.password.wrong')
      if (path === '/v1/auth/otp') return json(200, { status: 'requested' })
      if (path === '/v1/accounts') return json(201, { account_id: 'acc-1', code_sent_to: '' })
      if (path.endsWith('/username-availability')) return json(200, { status: 'available' })
      if (path === '/v1/accounts/already-added') return json(200, { already_added: false })
      if (path === '/v1/auth/verify') return (verifyAnswers.shift() ?? (() => json(200, SETUP)))()
      if (path === '/v1/auth/password/setup')
        return json(200, { access_token: 'ACCESS', refresh_token: 'REFRESH', expires_in: 900 })
      if (path === '/v1/me/username' && method === 'PUT')
        return json(200, { username: 'server-side-name', next_change_at: null })
      if (path === '/v1/me' && method === 'GET') {
        const next = meAnswers.length > 1 ? meAnswers.shift()! : meAnswers[0]!
        return json(200, next)
      }
      if (path === '/v1/auth/logout') return new Response(null, { status: 204 })
      return refuse(404, 'error.unexpected')
    }),
  )
}

/** Every place a typed value must never reach, joined for a substring search. */
function snapshot(): Record<string, string> {
  const storage = (s: Storage) =>
    Array.from({ length: s.length }, (_, i) => s.getItem(s.key(i) ?? '') ?? '').join('\n')
  return {
    localStorage: storage(window.localStorage),
    sessionStorage: storage(window.sessionStorage),
    historyState: JSON.stringify(window.history.state),
    title: document.title,
    href: window.location.href,
    console: logged.map((args) => args.map((a) => String(a)).join(' ')).join('\n'),
  }
}

function assertNoLeak(step: string) {
  const places = snapshot()
  for (const [place, text] of Object.entries(places))
    for (const sentinel of FORBIDDEN)
      expect(text.includes(sentinel), `${step}: "${sentinel}" in ${place}`).toBe(false)
  expect(indexedDbOpen, `${step}: indexedDB.open`).not.toHaveBeenCalled()
}

beforeEach(() => {
  logged = []
  bodies = []
  meAnswers = []
  verifyAnswers = []
  indexedDbOpen.mockClear()
  for (const method of CONSOLE)
    vi.spyOn(console, method).mockImplementation((...args: unknown[]) => {
      logged.push(args)
    })
  vi.stubGlobal('indexedDB', { open: indexedDbOpen })
  window.history.replaceState(null, '', '/signin')
  serve()
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.removeItem('sp.session')
  window.localStorage.removeItem('sp.lens')
  window.localStorage.removeItem('sp.workspace')
  window.history.replaceState(null, '', '/')
})

function renderApp() {
  render(
    <I18nProvider lang="en">
      <PwaProvider>
        <SessionProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </SessionProvider>
      </PwaProvider>
    </I18nProvider>,
  )
}

describe('no identifier leaks [NFR3.2–3.4] [NFR3.6]', () => {
  it('sign-in, the code flow, sign-up with Replace, the gate and rename leave no typed value behind', async () => {
    const user = userEvent.setup()
    meAnswers = [
      {
        self_name: 'Server Name',
        phone: null,
        email: null,
        has_password: true,
        username: null,
        username_required: true,
        lenses: [{ kind: 'student', count: 1 }],
      },
      {
        self_name: 'Server Name',
        phone: null,
        email: null,
        has_password: true,
        username: 'server-side-name',
        username_required: false,
        lenses: [{ kind: 'student', count: 1 }],
      },
    ]
    verifyAnswers = [
      () =>
        json(409, {
          error: {
            code: 'CONFLICT',
            message_key: 'account.username.unavailable',
            retryable: false,
          },
        }),
    ]
    renderApp()

    // ------------------------------------------------ sign-in
    await user.type(await screen.findByLabelText(en('auth_login_label')), SENTINEL.login)
    await user.type(screen.getByLabelText('Password'), SENTINEL.password)
    assertNoLeak('sign-in typed')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('alert')
    assertNoLeak('sign-in refused')

    // ------------------------------------------------ on to the code flow
    await user.click(screen.getByRole('link', { name: 'Forgot password?' }))
    await screen.findByRole('heading', { name: 'Get a code' })
    // The router writes its entry to the real history: the snapshot above
    // is of the place route state would be kept, not of nothing.
    expect(typeof (window.history.state as { idx?: unknown } | null)?.idx).toBe('number')
    assertNoLeak('code flow opened')
    await user.click(screen.getByRole('button', { name: 'Email' }))
    await user.type(screen.getByLabelText('Email address'), SENTINEL.email)
    await user.click(screen.getByRole('button', { name: 'Send code' }))
    await screen.findByLabelText('Enter the code')
    assertNoLeak('code flow sent')

    // ------------------------------------------------ sign-up, 409, Replace
    await user.click(screen.getByRole('button', { name: 'Change' }))
    await user.click(await screen.findByRole('link', { name: 'Back to log in' }))
    await user.click(await screen.findByRole('link', { name: 'Create account' }))
    await user.type(await screen.findByLabelText('Full name'), 'Rina Akter')
    await user.type(screen.getByLabelText('Mobile number'), SENTINEL.phone)
    await user.tab()
    await user.type(screen.getByLabelText('House or flat'), '12')
    await user.type(screen.getByLabelText('Road and area'), 'Road 4')
    await user.type(screen.getByLabelText('City or district'), 'Dhaka')
    await user.type(screen.getByLabelText('Postcode'), '1205')
    await user.type(screen.getByLabelText(en('signup_username_label')), SENTINEL.username)
    await user.type(screen.getByLabelText('Password'), SENTINEL.password)
    await user.type(screen.getByLabelText('Type the password again'), SENTINEL.password)
    assertNoLeak('sign-up typed')
    await user.click(screen.getByRole('button', { name: 'Send code' }))
    await user.type(await screen.findByLabelText('Enter the code'), SENTINEL.code)
    await screen.findByTestId('replace-username')
    assertNoLeak('Replace opened, code held')
    await user.type(screen.getByLabelText(en('signup_username_label')), `${SENTINEL.username}b`)
    await user.click(screen.getByRole('button', { name: en('auth_replace_username_continue') }))

    // ------------------------------------------------ the gate
    await screen.findByTestId('choose-username-gate', {}, { timeout: 3000 })
    assertNoLeak('signed in, gate shown')
    await user.type(screen.getByLabelText(en('signup_username_label')), SENTINEL.username)
    assertNoLeak('gate typed')
    await user.click(screen.getByRole('button', { name: en('choose_username_continue') }))
    await waitFor(() => expect(screen.queryByTestId('choose-username-gate')).toBeNull())
    assertNoLeak('gate lifted')

    // ------------------------------------------------ rename
    act(() => {
      window.history.pushState(null, '', '/settings/username')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await user.click(await screen.findByRole('button', { name: en('username_change') }))
    await user.type(screen.getByLabelText(en('username_new_label')), `${SENTINEL.username}c`)
    await user.type(screen.getByLabelText(en('web_password_current')), SENTINEL.password)
    assertNoLeak('rename typed')
    await user.click(screen.getByRole('button', { name: en('username_save') }))
    await screen.findByText(en('username_changed'))
    assertNoLeak('renamed')

    // Non-vacuity: every sentinel did reach a request body, so none of
    // the absences above is an absence of input.
    const sent = bodies.join('\n')
    for (const value of [
      SENTINEL.login,
      SENTINEL.password,
      SENTINEL.email,
      SENTINEL.username,
      SENTINEL.code,
      '01999999999',
    ])
      expect(sent, `${value} was never sent`).toContain(value)
  }, 30_000)
})
