/**
 * The choose-username gate as the app routes it, written before the code
 * [FR5.2] [FR5.3] [NFR3.14] [NFR3.15] [NFR3.16] [NFR8.5] [NFR8.6].
 *
 * A wrong answer here shows a screen the server's flag withholds, or
 * strands a person with no way out, so these ran red first (plan Step 8).
 * `App` is rendered signed in under `BrowserRouter`, as `src/main.tsx`
 * does, so typed URLs and browser history are the real ones. StrictMode
 * is left out on purpose: it runs effects twice in development, and case
 * 1 counts the `/v1/me` reads exactly.
 */
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { BrowserRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import { readTokens, saveTokens } from '../api/tokens'
import { I18nProvider, translate } from '../i18n/i18n'
import { PwaProvider } from '../pwa/pwa'
import { json } from '../test/render'
import { SessionProvider, useSession } from './session'

const en = (key: string, ...args: string[]) => translate('en', key, ...args)

type Answer = () => Response | Promise<Response>
interface Call {
  method: string
  path: string
  body: unknown
}

let calls: Call[] = []
/** Queued answers per `METHOD path`; the last one repeats. */
let queues: Record<string, Answer[]> = {}

function answerFor(key: string): Answer | undefined {
  const queue = queues[key]
  if (!queue || queue.length === 0) return undefined
  return queue.length > 1 ? queue.shift() : queue[0]
}

function serve(key: string, ...answers: Answer[]) {
  queues[key] = [...(queues[key] ?? []), ...answers]
}

/** A response the test releases when it chooses. */
function held() {
  let release: (r: Response) => void = () => undefined
  const promise = new Promise<Response>((resolve) => {
    release = resolve
  })
  return { answer: () => promise, release }
}

const ME = (required: boolean, lenses = [{ kind: 'teacher', count: 1 }]) => ({
  self_name: 'Karim Uddin',
  phone: null,
  email: 'karim@example.com',
  has_password: true,
  username: required ? null : 'nadia_k',
  username_required: required,
  lenses,
  workspaces: [],
})
const me = (required: boolean, lenses?: { kind: string; count: number }[]) => () =>
  json(200, ME(required, lenses))
const refusal =
  (status: number, key: string, retryable = false) =>
  () =>
    json(status, { error: { code: 'REFUSED', message_key: key, retryable } })
const ok = (body: unknown) => () => json(200, body)

const meReads = () => calls.filter((c) => c.method === 'GET' && c.path === '/v1/me')
const puts = () => calls.filter((c) => c.method === 'PUT' && c.path === '/v1/me/username')

beforeEach(() => {
  calls = []
  queues = {}
  window.history.replaceState(null, '', '/')
  saveTokens({ access_token: 'A', refresh_token: 'R', expires_in: 900 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const path = new URL(url, 'http://x').pathname
      calls.push({ method, path, body: init.body ? JSON.parse(init.body as string) : undefined })
      const answer = answerFor(`${method} ${path}`)
      if (answer) return answer()
      return json(404, {
        error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
      })
    }),
  )
  serve('POST /v1/auth/logout', () => new Response(null, { status: 204 }))
  serve('POST /v1/me/username-availability', ok({ status: 'available' }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.removeItem('sp.session')
  localStorage.removeItem('sp.lens')
  localStorage.removeItem('sp.workspace')
  window.history.replaceState(null, '', '/')
})

/**
 * Records whether anything but the gate was ever added to the page —
 * the shell (`nav`, `#main`), the lens picker or the resolving loader —
 * from the mutation records, so a flash added and removed within one
 * task is still seen.
 */
function watch() {
  const seen = { shell: false, picker: false, loader: false }
  const inspect = (node: Node) => {
    if (!(node instanceof Element)) return
    if (node.matches('#main, nav') || node.querySelector('#main, nav')) seen.shell = true
    const text = node.textContent ?? ''
    if (text.includes(en('lens_picker_title'))) seen.picker = true
    if (text.includes(en('auth_restoring'))) seen.loader = true
  }
  const observer = new MutationObserver((records) => {
    for (const r of records) r.addedNodes.forEach(inspect)
  })
  observer.observe(document.body, { subtree: true, childList: true })
  inspect(document.body)
  return {
    seen,
    reset() {
      seen.shell = false
      seen.picker = false
      seen.loader = false
    },
    stop: () => observer.disconnect(),
  }
}

function renderApp() {
  return render(
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

const gate = () => screen.queryByTestId('choose-username-gate')
const shell = () => document.querySelector('#main')
const field = () => screen.getByLabelText(en('signup_username_label'))
const continueButton = () => screen.getByRole('button', { name: en('choose_username_continue') })

async function choose(username = 'nadia_k') {
  await userEvent.type(field(), username)
  await userEvent.click(continueButton())
}

/**
 * The gate, once its mount effects have run. `findByTestId` resolves as
 * soon as the form is in the DOM, but React can run the gate's passive
 * effects -- the visibilitychange listener among them -- a task later.
 * On a loaded runner a `becomeVisible()` in that gap reached no listener,
 * and the read the test waited for never came. React runs a commit's
 * mount effects in one pass, so the field holding focus (the gate's
 * first effect) means the listener is attached too.
 */
async function findListeningGate() {
  await screen.findByTestId('choose-username-gate')
  await waitFor(() => expect(field()).toHaveFocus())
}

function becomeVisible() {
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'))
  })
}

async function navigateHistory(go: () => void) {
  const popped = new Promise((resolve) =>
    window.addEventListener('popstate', resolve, { once: true }),
  )
  go()
  await act(async () => {
    await popped
  })
}

describe('the gate comes before every route [FR5.2] [NFR3.14] [NFR8.5]', () => {
  it('the first render after resolving is the gate when the read says true', async () => {
    serve(
      'GET /v1/me',
      me(true, [
        { kind: 'teacher', count: 1 },
        { kind: 'guardian', count: 1 },
      ]),
    )
    const watcher = watch()
    renderApp()
    expect(await screen.findByTestId('choose-username-gate')).toBeInTheDocument()
    // One read, and the flag rode on it: no extra request to reach the gate.
    expect(meReads()).toHaveLength(1)
    expect(watcher.seen.shell).toBe(false)
    expect(watcher.seen.picker).toBe(false)
    watcher.stop()
  })

  it('a typed URL renders the gate', async () => {
    window.history.replaceState(null, '', '/settings')
    serve('GET /v1/me', me(true))
    const watcher = watch()
    renderApp()
    expect(await screen.findByTestId('choose-username-gate')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: en('settings_title') })).toBeNull()
    expect(watcher.seen.shell).toBe(false)
    // The URL is left as it was, so the person lands there once it lifts.
    expect(window.location.pathname).toBe('/settings')
    watcher.stop()
  })

  it('history back and forward render the gate', async () => {
    serve('GET /v1/me', me(true))
    renderApp()
    await screen.findByTestId('choose-username-gate')
    const watcher = watch()
    window.history.pushState({}, '', '/settings')
    await navigateHistory(() => window.history.back())
    expect(gate()).toBeInTheDocument()
    await navigateHistory(() => window.history.forward())
    expect(window.location.pathname).toBe('/settings')
    expect(gate()).toBeInTheDocument()
    expect(watcher.seen.shell).toBe(false)
    watcher.stop()
  })
})

describe('the gate lifts only on a fresh read [FR5.4] [NFR3.14]', () => {
  it('a 200 from PUT /v1/me/username lifts the gate only when the next read says false', async () => {
    const reread = held()
    serve('GET /v1/me', me(true), reread.answer)
    serve('PUT /v1/me/username', ok({ username: 'nadia_k', next_change_at: null }))
    renderApp()
    await screen.findByTestId('choose-username-gate')
    await choose('nadia_k')
    await waitFor(() => expect(meReads()).toHaveLength(2))
    // The 200 alone lifted nothing: the read is still out.
    expect(gate()).toBeInTheDocument()
    expect(shell()).toBeNull()
    expect(puts()[0]!.body).toEqual({ username: 'nadia_k' })
    act(() => reread.release(json(200, ME(false))))
    await waitFor(() => expect(gate()).toBeNull())
    expect(shell()).not.toBeNull()
  })

  it('a 200 followed by a read still saying true returns to editing with a re-read retry', async () => {
    serve('GET /v1/me', me(true), me(true), me(false))
    serve('PUT /v1/me/username', ok({ username: 'nadia_k', next_change_at: null }))
    renderApp()
    await screen.findByTestId('choose-username-gate')
    await choose('nadia_k')
    expect(await screen.findByText(en('error_unexpected'))).toBeInTheDocument()
    expect(gate()).toBeInTheDocument()
    expect(meReads()).toHaveLength(2)
    // Retry re-reads; it does not send the choice again.
    await userEvent.click(screen.getByRole('button', { name: en('auth_retry') }))
    await waitFor(() => expect(gate()).toBeNull())
    expect(meReads()).toHaveLength(3)
    expect(puts()).toHaveLength(1)
  })

  it('password_required re-reads with no password asked, and lifts on false', async () => {
    serve('GET /v1/me', me(true), me(false))
    serve('PUT /v1/me/username', refusal(409, 'account.username.password_required'))
    renderApp()
    await screen.findByTestId('choose-username-gate')
    expect(screen.queryByLabelText(/password/i)).toBeNull()
    await choose('nadia_k')
    await waitFor(() => expect(gate()).toBeNull())
    expect(meReads()).toHaveLength(2)
    expect(puts()).toHaveLength(1)
    expect(puts()[0]!.body).not.toHaveProperty('password')
  })
})

describe('a read that lands while Saving [W4 step 9]', () => {
  it('a visibility read landing during Saving is ignored: it says true, and the PUT answer then leads to Rereading', async () => {
    const visibilityRead = held()
    const put = held()
    serve('GET /v1/me', me(true), visibilityRead.answer, me(false))
    serve('PUT /v1/me/username', put.answer)
    renderApp()
    await findListeningGate()
    becomeVisible()
    await waitFor(() => expect(meReads()).toHaveLength(2))
    await choose('nadia_k')
    await waitFor(() => expect(puts()).toHaveLength(1))
    act(() => visibilityRead.release(json(200, ME(true))))
    // Still saving: the read changed nothing, and nothing new was read.
    await waitFor(() => expect(continueButton()).toBeDisabled())
    expect(gate()).toBeInTheDocument()
    expect(meReads()).toHaveLength(2)
    act(() => put.release(json(200, { username: 'nadia_k', next_change_at: null })))
    await waitFor(() => expect(gate()).toBeNull())
    expect(meReads()).toHaveLength(3)
  })

  it('a visibility read landing during Saving is ignored: it says false, ready renders, and the late PUT answer renders and throws nothing', async () => {
    const visibilityRead = held()
    const put = held()
    serve('GET /v1/me', me(true), visibilityRead.answer)
    serve('PUT /v1/me/username', put.answer)
    const errors = vi.spyOn(console, 'error')
    renderApp()
    await findListeningGate()
    becomeVisible()
    await waitFor(() => expect(meReads()).toHaveLength(2))
    await choose('nadia_k')
    await waitFor(() => expect(puts()).toHaveLength(1))
    act(() => visibilityRead.release(json(200, ME(false))))
    await waitFor(() => expect(gate()).toBeNull())
    expect(shell()).not.toBeNull()
    await act(async () => {
      put.release(
        json(409, {
          error: {
            code: 'CONFLICT',
            message_key: 'account.username.password_required',
            retryable: false,
          },
        }),
      )
      await Promise.resolve()
    })
    expect(gate()).toBeNull()
    expect(shell()).not.toBeNull()
    expect(meReads()).toHaveLength(2)
    expect(errors).not.toHaveBeenCalled()
  })
})

describe('the visibility re-read [NFR8.6]', () => {
  it('visibilitychange sends one read in Editing and none in Saving or Rereading', async () => {
    const put = held()
    const reread = held()
    serve('GET /v1/me', me(true), me(true), reread.answer)
    serve('PUT /v1/me/username', put.answer)
    renderApp()
    await screen.findByTestId('choose-username-gate')

    // Hidden is not a return to the tab.
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(meReads()).toHaveLength(1)

    becomeVisible() // Editing: one read.
    await waitFor(() => expect(meReads()).toHaveLength(2))

    await choose('nadia_k')
    await waitFor(() => expect(puts()).toHaveLength(1))
    becomeVisible() // Saving: none.
    expect(meReads()).toHaveLength(2)

    act(() => put.release(json(200, { username: 'nadia_k', next_change_at: null })))
    await waitFor(() => expect(meReads()).toHaveLength(3)) // the gate's own re-read
    becomeVisible() // Rereading: none.
    expect(meReads()).toHaveLength(3)
    act(() => reread.release(json(200, ME(false))))
    await waitFor(() => expect(gate()).toBeNull())
  })

  it('a re-read while the gate shows never renders the resolving loader', async () => {
    const visibilityRead = held()
    const reread = held()
    serve('GET /v1/me', me(true), visibilityRead.answer, reread.answer)
    serve('PUT /v1/me/username', ok({ username: 'nadia_k', next_change_at: null }))
    renderApp()
    await findListeningGate()
    const watcher = watch()
    becomeVisible()
    await waitFor(() => expect(meReads()).toHaveLength(2))
    expect(screen.queryByText(en('auth_restoring'))).toBeNull()
    act(() => visibilityRead.release(json(200, ME(true))))
    await choose('nadia_k')
    await waitFor(() => expect(meReads()).toHaveLength(3))
    expect(screen.queryByText(en('auth_restoring'))).toBeNull()
    expect(gate()).toBeInTheDocument()
    act(() => reread.release(json(200, ME(false))))
    await waitFor(() => expect(gate()).toBeNull())
    expect(watcher.seen.loader).toBe(false)
    watcher.stop()
  })
})

describe('fail closed, with a way out [NFR3.15] [NFR3.16]', () => {
  it('a failed re-read shows the error card, not the app, and its Sign out clears the tokens', async () => {
    serve('GET /v1/me', me(true), refusal(503, 'error.temporarily_unavailable', true))
    serve('PUT /v1/me/username', ok({ username: 'nadia_k', next_change_at: null }))
    const watcher = watch()
    renderApp()
    await screen.findByTestId('choose-username-gate')
    await choose('nadia_k')
    const card = await screen.findByRole('alert')
    expect(card).toHaveClass('card', 'error')
    expect(gate()).toBeNull()
    expect(watcher.seen.shell).toBe(false)
    expect(screen.getByRole('button', { name: en('auth_retry') })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: en('more_log_out') }))
    await waitFor(() => expect(readTokens()).toBeNull())
    expect(calls.some((c) => c.method === 'POST' && c.path === '/v1/auth/logout')).toBe(true)
    watcher.stop()
  })

  it('a failed re-read that is not retryable shows no Retry, and Sign out still works', async () => {
    serve('GET /v1/me', me(true), refusal(403, 'error.unexpected', false))
    serve('PUT /v1/me/username', ok({ username: 'nadia_k', next_change_at: null }))
    renderApp()
    await screen.findByTestId('choose-username-gate')
    await choose('nadia_k')
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: en('more_log_out') }))
    await waitFor(() => expect(readTokens()).toBeNull())
  })

  it('Sign out from the gate clears sp.session and calls POST /v1/auth/logout', async () => {
    serve('GET /v1/me', me(true))
    renderApp()
    await screen.findByTestId('choose-username-gate')
    await userEvent.click(screen.getByRole('button', { name: en('choose_username_sign_out') }))
    await waitFor(() => expect(localStorage.getItem('sp.session')).toBeNull())
    const logout = calls.find((c) => c.method === 'POST' && c.path === '/v1/auth/logout')
    expect(logout?.body).toEqual({ refresh_token: 'R' })
    await waitFor(() => expect(window.location.pathname).toBe('/signin'))
  })
})

describe('reread() [frontend-components § 2.3]', () => {
  it('a reread() superseded by a refresh() still settles, with the newest read', async () => {
    const superseded = held()
    const newest = held()
    serve('GET /v1/me', me(true), superseded.answer, newest.answer)
    let value: ReturnType<typeof useSession> | null = null
    function Probe() {
      const session = useSession()
      useEffect(() => {
        value = session
      })
      return <p data-testid="state">{session.session.state}</p>
    }
    render(
      <I18nProvider lang="en">
        <SessionProvider>
          <Probe />
        </SessionProvider>
      </I18nProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('username-required'))
    let settled = false
    act(() => {
      void value!.reread().then(() => {
        settled = true
      })
    })
    await waitFor(() => expect(meReads()).toHaveLength(2))
    act(() => value!.refresh()) // supersedes the read reread() started
    await waitFor(() => expect(meReads()).toHaveLength(3))
    // The superseded read's answer is dropped and settles nothing.
    await act(async () => {
      superseded.release(json(200, ME(true)))
      await Promise.resolve()
    })
    expect(settled).toBe(false)
    act(() => newest.release(json(200, ME(false))))
    await waitFor(() => expect(settled).toBe(true))
    expect(screen.getByTestId('state')).toHaveTextContent('ready')
  })
})
