/**
 * The account screens against a mocked API, signed in for real: tokens in
 * storage, `/v1/me` answering, the session resolving its lens.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens, readTokens, saveTokens } from '../../../api/tokens'
import { I18nProvider } from '../../../i18n/i18n'
import { PwaProvider } from '../../../pwa/pwa'
import { SessionProvider, useSession } from '../../../session/session'
import { json } from '../../../test/render'
import { More } from '../More'
import { accountRoutes } from './index'
import { resetUnreadCount } from './unread'

type Handler = (method: string, url: string, body: unknown) => Response | undefined

const calls: { method: string; url: string; body: unknown }[] = []
let handler: Handler = () => undefined

function me(lens: 'teacher' | 'student' | 'guardian', patch: Record<string, unknown> = {}) {
  return {
    self_name: 'Rokeya Jahan',
    phone: '+8801911000003',
    address_house: '12',
    address_road: 'Road 5',
    address_city: 'Dhaka',
    address_postcode: '1205',
    lenses: [{ kind: lens, count: 1 }],
    ...patch,
  }
}

function serve(meBody: unknown, routes: Handler) {
  handler = (method, url, body) =>
    url.endsWith('/v1/me') && method === 'GET' ? json(200, meBody) : routes(method, url, body)
}

beforeEach(() => {
  calls.length = 0
  localStorage.clear()
  resetUnreadCount()
  saveTokens({ access_token: 'A', refresh_token: 'R', expires_in: 900 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const body = init.body ? JSON.parse(init.body as string) : undefined
      calls.push({ method, url, body })
      return (
        handler(method, url, body) ??
        json(404, {
          error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
        })
      )
    }),
  )
})
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

function Ready({ children }: { children: ReactNode }) {
  const { session } = useSession()
  if (session.state === 'signed-out') return <p>signed out</p>
  return session.state === 'ready' ? children : null
}

function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname}</p>
}

function renderAt(path: string) {
  // StrictMode, as main.tsx renders: effects run their cleanup once on
  // mount, which is how the deletion screen once signed out too early.
  return render(
    <StrictMode>
      <I18nProvider lang="en">
        <PwaProvider>
          <SessionProvider>
            <MemoryRouter initialEntries={[path]}>
              <Ready>
                <Routes>
                  {accountRoutes.map((r) => (
                    <Route key={r.path} path={r.path} element={r.element} />
                  ))}
                  <Route path="/more" element={<More />} />
                  <Route path="*" element={<Where />} />
                </Routes>
              </Ready>
            </MemoryRouter>
          </SessionProvider>
        </PwaProvider>
      </I18nProvider>
    </StrictMode>,
  )
}

const inbox = {
  unread: 2,
  items: [
    {
      notification_id: 'n1',
      kind: 'fee_reminder',
      batch_name: 'Physics · Batch A',
      child_name: 'Tasnim',
      amount: '1200.00',
      period: '2026-10',
      created_at: new Date().toISOString(),
      read: false,
      enrollment_id: 'seat1',
      source_id: null,
      preview: null,
    },
    {
      notification_id: 'n2',
      kind: 'notice',
      batch_name: 'Physics · Batch A',
      child_name: 'Tasnim',
      amount: null,
      period: null,
      created_at: new Date().toISOString(),
      read: true,
      enrollment_id: 'seat1',
      source_id: 'a1',
      preview: 'Bring the worksheet',
    },
  ],
}

describe('Inbox', () => {
  it('lists what the server sent, and opening an item marks it read and goes where it points', async () => {
    serve(me('guardian'), (method, url) => {
      if (url.split('?')[0]!.endsWith('/v1/me/notifications') && method === 'GET')
        return json(200, inbox)
      if (url.endsWith('/v1/me/notifications/n1/read')) return new Response(null, { status: 204 })
      return undefined
    })
    renderAt('/inbox')
    expect(await screen.findByText('Fee reminder · Tasnim · Physics · Batch A')).toBeInTheDocument()
    expect(screen.getByText('Bring the worksheet')).toBeInTheDocument()
    expect(screen.getByText('2 unread')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Fee reminder · Tasnim · Physics · Batch A'))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/child/seat1/fees'))
    expect(
      calls.some((c) => c.method === 'POST' && c.url.endsWith('/v1/me/notifications/n1/read')),
    ).toBe(true)
  })

  it('marks everything read with one call', async () => {
    serve(me('guardian'), (method, url) => {
      if (url.split('?')[0]!.endsWith('/v1/me/notifications') && method === 'GET')
        return json(200, inbox)
      if (url.split('?')[0]!.endsWith('/v1/me/notifications/read'))
        return new Response(null, { status: 204 })
      return undefined
    })
    renderAt('/inbox')
    await userEvent.click(await screen.findByRole('button', { name: 'Mark all read' }))
    await waitFor(() =>
      expect(
        calls.filter(
          (c) => c.method === 'POST' && c.url.split('?')[0]!.endsWith('/v1/me/notifications/read'),
        ),
      ).toHaveLength(1),
    )
    // PO-10: both the read and "mark all read" name the kinds this
    // client draws, so the server's count covers only those.
    for (const c of calls.filter((c) => c.url.includes('/v1/me/notifications'))) {
      expect(new URL(c.url, 'http://x').searchParams.getAll('kind')).toContain('class_rescheduled')
    }
  })

  it('shows a cancelled class with its day and time', async () => {
    const classInbox = {
      unread: 1,
      items: [
        {
          notification_id: 'c1',
          kind: 'class_cancelled',
          batch_name: 'Physics',
          child_name: null,
          created_at: '2026-11-05T03:00:00Z',
          read: false,
          source_id: 's1',
          class_date: '2099-04-12',
          class_time: '16:00:00',
        },
      ],
    }
    serve(me('student'), (method, url) =>
      url.split('?')[0]!.endsWith('/v1/me/notifications') && method === 'GET'
        ? json(200, classInbox)
        : undefined,
    )
    renderAt('/inbox')
    expect(await screen.findByText('Class cancelled · Physics')).toBeInTheDocument()
    expect(screen.getByText('The class on 12 Apr, 4:00 pm will not be held.')).toBeInTheDocument()
  })

  it('says so when there is nothing', async () => {
    serve(me('student'), (_method, url) =>
      url.split('?')[0]!.endsWith('/v1/me/notifications')
        ? json(200, { unread: 0, items: [] })
        : undefined,
    )
    renderAt('/inbox')
    expect(await screen.findByText('Nothing here yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark all read' })).toBeNull()
  })

  it('opens a payment decision on its own page, and marks it read', async () => {
    serve(me('student'), (_method, url) => {
      if (url.endsWith('/v1/me/notifications/n9'))
        return json(200, {
          notification_id: 'n9',
          kind: 'payment_partial',
          available: true,
          batch_name: 'Physics · Batch A',
          child_name: null,
          created_at: new Date().toISOString(),
          read: false,
          payment: {
            claim_id: 'c1',
            period: '2026-10',
            claimed: '1200.00',
            approved: '800.00',
            outcome: 'partial',
            reason: 'Only 800 arrived',
          },
        })
      if (url.endsWith('/n9/read')) return new Response(null, { status: 204 })
      return undefined
    })
    renderAt('/inbox/n9')
    expect(
      await screen.findByText('Payment partly approved · Physics · Batch A'),
    ).toBeInTheDocument()
    expect(screen.getByText('৳1,200')).toBeInTheDocument()
    expect(screen.getByText('৳800')).toBeInTheDocument()
    expect(screen.getByText('Partly approved')).toBeInTheDocument()
    expect(screen.getByText('Only 800 arrived')).toBeInTheDocument()
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/n9/read'))).toBe(true))
  })

  it('says when an item is no longer available', async () => {
    serve(me('student'), (_method, url) =>
      url.endsWith('/v1/me/notifications/gone')
        ? json(200, {
            notification_id: 'gone',
            kind: 'notice',
            available: false,
            batch_name: 'X',
            created_at: new Date().toISOString(),
            read: true,
          })
        : undefined,
    )
    renderAt('/inbox/gone')
    expect(await screen.findByText('This update is no longer available.')).toBeInTheDocument()
  })
})

describe('Edit profile', () => {
  it('offers Save only for a complete address, sends the exact body, and returns to More', async () => {
    serve(me('guardian'), (method, url, body) =>
      url.endsWith('/v1/me') && method === 'PATCH'
        ? json(200, { ...me('guardian'), ...(body as object) })
        : undefined,
    )
    renderAt('/profile/edit')
    const postcode = await screen.findByLabelText('Postcode')
    const save = screen.getByRole('button', { name: 'Save' })
    expect(screen.getByText('01911-000003')).toBeInTheDocument()

    await userEvent.clear(postcode)
    await userEvent.type(postcode, '12')
    expect(save).toBeDisabled()
    await userEvent.tab()
    expect(screen.getByText('Postcodes have 4 digits')).toBeInTheDocument()

    await userEvent.clear(postcode)
    await userEvent.type(postcode, '১২০৯')
    const name = screen.getByLabelText('Full name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Rokeya Begum')
    await userEvent.click(save)

    await waitFor(() => expect(screen.getByText('Saved.')).toBeInTheDocument())
    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch?.body).toEqual({
      self_name: 'Rokeya Begum',
      address_house: '12',
      address_road: 'Road 5',
      address_city: 'Dhaka',
      address_postcode: '1209',
    })
  })

  it('shows the server’s message when saving is refused', async () => {
    serve(me('guardian'), (method, url) =>
      url.endsWith('/v1/me') && method === 'PATCH'
        ? json(422, {
            error: { code: 'VALIDATION', message_key: 'signup.name.required', retryable: false },
          })
        : undefined,
    )
    renderAt('/profile/edit')
    await userEvent.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please enter your name.')
  })
})

describe('My children', () => {
  it('lists each child with their batches, linking into the child’s batch', async () => {
    serve(me('guardian'), (_method, url) =>
      url.endsWith('/v1/guardian/home')
        ? json(200, {
            children: [
              {
                key: 'k1',
                display_name: 'Tasnim Jahan',
                batch_count: 2,
                batches: [
                  {
                    enrollment_id: 'e1',
                    batch_name: 'Physics · Batch A',
                    teacher_display_name: 'Mahfuz',
                  },
                  { enrollment_id: 'e2', batch_name: 'Math · Batch B', teacher_display_name: null },
                ],
              },
            ],
          })
        : undefined,
    )
    renderAt('/profile/children')
    const card = await screen.findByRole('article', { name: 'Tasnim Jahan' })
    expect(within(card).getByText('2 batches')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Physics · Batch A/ })).toHaveAttribute(
      'href',
      '/child/e1',
    )
    expect(screen.getByText(/01911-000003/)).toBeInTheDocument()
  })
})

describe('Delete account', () => {
  it('a student: deleted and kept, Delete only for their own number, then signed out', async () => {
    serve(me('student'), (method, url) => {
      if (url.endsWith('/v1/me/deletion-summary'))
        return json(200, { batch_count: 0, student_count: 0, outstanding: '0.00' })
      if (url.endsWith('/v1/me') && method === 'DELETE') return json(200, { status: 'deleted' })
      return undefined
    })
    renderAt('/profile/delete')
    expect(await screen.findByText(/Your login and your profile/)).toBeInTheDocument()
    expect(screen.getByText(/Any payment you submitted/)).toBeInTheDocument()
    expect(
      screen.getByText(/Attendance, marks and fee records your teachers wrote/),
    ).toBeInTheDocument()

    const confirm = screen.getByRole('button', { name: 'Delete' })
    const number = screen.getByLabelText('Type your number to confirm.')
    await userEvent.type(number, '000003')
    expect(confirm).toBeDisabled()
    await userEvent.clear(number)
    await userEvent.type(number, '01911000004')
    expect(confirm).toBeDisabled()
    await userEvent.clear(number)
    await userEvent.type(number, '01911-000003')
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)

    expect(await screen.findByText('Your account is deleted')).toBeInTheDocument()
    // It stays up until Close: the screen must not end the session the
    // moment it mounts (StrictMode runs effect cleanups once on mount).
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getByText('Your account is deleted')).toBeInTheDocument()
    expect(screen.queryByText('signed out')).toBeNull()
    const deletes = calls.filter((c) => c.method === 'DELETE')
    expect(deletes).toHaveLength(1)
    expect(deletes[0]?.url).toMatch(/\/v1\/me$/)
    expect(deletes[0]?.body).toBeUndefined()

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(readTokens()).toBeNull()
    expect(await screen.findByText('signed out')).toBeInTheDocument()
  })

  it('a teacher who owns batches is told what they lose and what stays owed', async () => {
    serve(me('teacher', { phone: '+8801711000001' }), (_method, url) =>
      url.endsWith('/v1/me/deletion-summary')
        ? json(200, { batch_count: 2, student_count: 7, outstanding: '37200.00' })
        : undefined,
    )
    renderAt('/profile/delete')
    expect(await screen.findByText('You have 2 batches with 7 students.')).toBeInTheDocument()
    expect(screen.getByText('Your access to all 2 batches and their records')).toBeInTheDocument()
    expect(
      screen.getByText('Your 7 students keep their own attendance, marks and fee history'),
    ).toBeInTheDocument()
    expect(screen.getByText(/৳37,200 recorded as owed stays on those records/)).toBeInTheDocument()
    expect(screen.queryByText(/Any payment you submitted/)).toBeNull()
  })

  it('offers nothing to delete until the summary has loaded', async () => {
    serve(me('teacher'), (_method, url) =>
      url.endsWith('/v1/me/deletion-summary')
        ? json(503, {
            error: { code: 'TRANSIENT', message_key: 'error.unexpected', retryable: true },
          })
        : undefined,
    )
    renderAt('/profile/delete')
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull()
  })

  it('keeps the account and says so when the server refuses', async () => {
    serve(me('student'), (method, url) => {
      if (url.endsWith('/v1/me/deletion-summary'))
        return json(200, { batch_count: 0, student_count: 0, outstanding: '0.00' })
      if (method === 'DELETE')
        return json(503, {
          error: { code: 'TRANSIENT', message_key: 'error.unexpected', retryable: true },
        })
      return undefined
    })
    renderAt('/profile/delete')
    await userEvent.type(
      await screen.findByLabelText('Type your number to confirm.'),
      '01911000003',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
    expect(readTokens()).not.toBeNull()
  })
})

describe('More', () => {
  it('a guardian sees the inbox with its unread count, children, edit and delete', async () => {
    serve(me('guardian'), (_method, url) =>
      url.split('?')[0]!.endsWith('/v1/me/notifications') ? json(200, inbox) : undefined,
    )
    renderAt('/more')
    expect(await screen.findByRole('link', { name: /Notifications/ })).toHaveAttribute(
      'href',
      '/inbox',
    )
    expect(await screen.findByLabelText('2 unread')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /My children/ })).toHaveAttribute(
      'href',
      '/profile/children',
    )
    expect(screen.getByRole('link', { name: /Edit/ })).toHaveAttribute('href', '/profile/edit')
    expect(screen.getByRole('link', { name: /Delete account/ })).toHaveAttribute(
      'href',
      '/profile/delete',
    )
    expect(screen.queryByRole('link', { name: /Where students pay/ })).toBeNull()
  })

  it('a teacher keeps Getting paid and Your records, and has no children row', async () => {
    serve(me('teacher'), (_method, url) =>
      url.split('?')[0]!.endsWith('/v1/me/notifications')
        ? json(200, { unread: 0, items: [] })
        : undefined,
    )
    renderAt('/more')
    expect(await screen.findByRole('link', { name: /Where students pay/ })).toHaveAttribute(
      'href',
      '/payment-methods',
    )
    expect(screen.getByRole('link', { name: /Collections/ })).toHaveAttribute(
      'href',
      '/collections',
    )
    expect(screen.queryByRole('link', { name: /My children/ })).toBeNull()
  })
})
