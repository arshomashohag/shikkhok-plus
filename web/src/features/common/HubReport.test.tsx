/**
 * Reporting a public hub page, opened from the page's "Report this page"
 * link: `/ui/hub-report?kind=owner_listing|batch_listing|media&id=<uuid>`.
 *
 * What is asserted: the target comes from the query and nowhere else, a
 * malformed link sends nothing, the server's refusals read as the brief
 * words them, a dropped connection keeps what was typed and offers Retry,
 * and a signed-out reader is taken through sign-in and back to the form.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../../App'
import { clearTokens, saveTokens } from '../../api/tokens'
import { I18nProvider } from '../../i18n/i18n'
import { PwaProvider } from '../../pwa/pwa'
import { SessionProvider } from '../../session/session'
import { json, renderScreen } from '../../test/render'
import { HubReport } from './HubReport'

const OWNER = '6f1c2b0e-3a4d-4e5f-8a9b-0c1d2e3f4a5b'
const BATCH = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const REPORT = (kind: string, id: string) => `/hub-report?kind=${kind}&id=${id}`

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
  clearTokens()
  localStorage.removeItem('sp.lens')
  sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

const posts = () =>
  fetchMock.mock.calls
    .filter(([u, init]) => String(u).endsWith('/v1/hub/reports') && init?.method === 'POST')
    .map(([, init]) => JSON.parse((init as RequestInit).body as string) as unknown)

/** The report endpoint answers with `answer`; anything else is a 404. */
function serve(answer: () => Response | Promise<Response>) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    if (url.endsWith('/v1/hub/reports') && init.method === 'POST') return answer()
    return json(404, {
      error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
    })
  })
}

const refusal =
  (status: number, code: string, key: string, retryable = false) =>
  () =>
    json(status, { error: { code, message_key: key, retryable } })

async function fill(reason: RegExp, note: string) {
  await userEvent.click(await screen.findByRole('radio', { name: reason }))
  if (note) await userEvent.type(screen.getByLabelText(/Anything we should know/), note)
}

const send = () => userEvent.click(screen.getByRole('button', { name: 'Send report' }))

describe('HubReport', () => {
  it('opens from the query, sends reason and note', async () => {
    serve(() => new Response(null, { status: 202 }))
    renderScreen(<HubReport />, REPORT('batch_listing', BATCH))

    expect(await screen.findByText("A batch's public page")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send report' })).toBeDisabled()
    await fill(/It is fake/, 'Same photo as another centre')
    await send()

    await waitFor(() =>
      expect(posts()).toEqual([
        {
          target_kind: 'batch_listing',
          target_id: BATCH,
          reason: 'fake',
          note: 'Same photo as another centre',
        },
      ]),
    )
    expect(await screen.findByText(/Thank you. We will look at this page./)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send report' })).not.toBeInTheDocument()
  })

  it('reports a photo: kind=media renders the form and submits it', async () => {
    serve(() => new Response(null, { status: 202 }))
    renderScreen(<HubReport />, REPORT('media', OWNER))

    expect(await screen.findByText('A photo on a public page')).toBeInTheDocument()
    await fill(/It shows personal information/, '')
    await send()

    await waitFor(() =>
      expect(posts()).toEqual([
        { target_kind: 'media', target_id: OWNER, reason: 'personal_info' },
      ]),
    )
    expect(await screen.findByText(/Thank you. We will look at this page./)).toBeInTheDocument()
  })

  it('sends no note when none was written', async () => {
    serve(() => new Response(null, { status: 202 }))
    renderScreen(<HubReport />, REPORT('owner_listing', OWNER))

    await fill(/It shows personal information/, '')
    await send()

    await waitFor(() =>
      expect(posts()).toEqual([
        { target_kind: 'owner_listing', target_id: OWNER, reason: 'personal_info' },
      ]),
    )
  })

  it.each([
    ['review', "A guardian's review"],
    ['reply', "A teacher's reply to a review"],
  ])('reports a %s by the review id the link carries', async (kind, target) => {
    serve(() => new Response(null, { status: 202 }))
    renderScreen(<HubReport />, REPORT(kind, BATCH))

    expect(await screen.findByText(target)).toBeInTheDocument()
    await fill(/It is abusive/, '')
    await send()

    await waitFor(() =>
      expect(posts()).toEqual([{ target_kind: kind, target_id: BATCH, reason: 'abusive' }]),
    )
  })

  it.each([
    ['an unknown kind', REPORT('bogus', OWNER)],
    ['a kind near a real one', REPORT('reviews', OWNER)],
    ['no kind', `/hub-report?id=${OWNER}`],
    ['no id', '/hub-report?kind=owner_listing'],
    ['an id that is not a UUID', REPORT('owner_listing', 'sumi-apa')],
    ['a UUID with extra text', REPORT('owner_listing', `${OWNER}x`)],
    ['nothing at all', '/hub-report'],
  ])('rejects bad kind or id without a request: %s', async (_, path) => {
    serve(() => new Response(null, { status: 202 }))
    renderScreen(<HubReport />, path)

    expect(await screen.findByText("This link isn't valid.")).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send report' })).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('failure keeps input and offers retry', async () => {
    let attempt = 0
    serve(() => {
      attempt += 1
      if (attempt === 1) throw new TypeError('Failed to fetch')
      return new Response(null, { status: 202 })
    })
    renderScreen(<HubReport />, REPORT('owner_listing', OWNER))

    await fill(/It is misleading/, 'Claims a board result it never had')
    await send()

    expect(await screen.findByText(/Your report was not sent./)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /It is misleading/ })).toBeChecked()
    expect(screen.getByLabelText(/Anything we should know/)).toHaveValue(
      'Claims a board result it never had',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(/Thank you. We will look at this page./)).toBeInTheDocument()
    const body = {
      target_kind: 'owner_listing',
      target_id: OWNER,
      reason: 'misleading',
      note: 'Claims a board result it never had',
    }
    expect(posts()).toEqual([body, body])
  })

  it.each([
    [
      'REPORT_TARGET_NOT_FOUND',
      refusal(404, 'REPORT_TARGET_NOT_FOUND', 'hub.report_target_not_found'),
      'This listing can no longer be reported.',
    ],
    [
      'REPORT_ALREADY_FILED',
      refusal(409, 'REPORT_ALREADY_FILED', 'hub.report_already_filed'),
      "You've already reported this.",
    ],
    [
      'HUB_REPORT_CEILING',
      refusal(429, 'HUB_REPORT_CEILING', 'hub.report_ceiling'),
      'You have sent a lot of reports today. Try again tomorrow.',
    ],
  ])('a %s refusal says so and offers no retry', async (_, answer, words) => {
    serve(answer)
    renderScreen(<HubReport />, REPORT('owner_listing', OWNER))

    await fill(/Something else/, '')
    await send()

    expect(await screen.findByText(new RegExp(words.replace('.', '\\.')))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Something else/ })).toBeChecked()
  })
})

describe('HubReport from a signed-out start', () => {
  it('signed-out user is sent through sign-in and back', async () => {
    const path = REPORT('owner_listing', OWNER)
    window.history.replaceState(null, '', path)
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      if (method === 'POST' && url.endsWith('/v1/auth/password'))
        return json(200, {
          access_token: 'A',
          refresh_token: 'R',
          expires_in: 900,
          mfa_required: false,
        })
      if (method === 'GET' && url.endsWith('/v1/me'))
        return json(200, {
          self_name: 'Rina Begum',
          phone: null,
          username: 'rina_b',
          username_required: false,
          lenses: [{ kind: 'guardian', count: 1 }],
          workspaces: [],
        })
      return json(404, {
        error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
      })
    })
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

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/signin')
    await userEvent.type(screen.getByLabelText('Username, phone or email'), 'rina_b')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Report this page' })).toBeInTheDocument()
    expect(`${window.location.pathname}${window.location.search}`).toBe(path)
    expect(await screen.findByRole('radio', { name: /It is fake/ })).toBeInTheDocument()
  })

  it('a signed-in reader lands on the form directly', async () => {
    saveTokens({ access_token: 'A', refresh_token: 'R', expires_in: 900 })
    const path = REPORT('batch_listing', BATCH)
    window.history.replaceState(null, '', path)
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if ((init.method ?? 'GET') === 'GET' && url.endsWith('/v1/me'))
        return json(200, {
          self_name: 'Karim Uddin',
          phone: null,
          username: 'karim',
          username_required: false,
          lenses: [{ kind: 'teacher', count: 1 }],
          workspaces: [],
        })
      return json(404, {
        error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
      })
    })
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

    expect(await screen.findByRole('heading', { name: 'Report this page' })).toBeInTheDocument()
    expect(`${window.location.pathname}${window.location.search}`).toBe(path)
  })
})
