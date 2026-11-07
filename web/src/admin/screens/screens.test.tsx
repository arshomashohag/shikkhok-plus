/**
 * The admin screens inside the admin app, against a mocked API, signed
 * in with an admin token. Who is an administrator is the server's to
 * say; the client only reacts to a 403 (and a 401, in AdminApp.test).
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../i18n/i18n'
import { json } from '../../test/render'
import '../strings'
import { peekAdminSession, resetAdminSessionForTests } from '../session'
import { renderAdmin, serveAdmin, type Call, type Handler } from '../test/renderAdmin'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
let calls: Call[] = []
const now = new Date().toISOString()

function serve(handler: Handler) {
  calls = serveAdmin(handler)
}
const renderAt = (path: string) => renderAdmin(path)

afterEach(() => {
  vi.unstubAllGlobals()
  resetAdminSessionForTests()
  sessionStorage.clear()
})

const overview = {
  generated_at: now,
  accounts: 1234,
  new_7_days: 12,
  new_30_days: 57,
  active_7_days: 640,
  active_30_days: 980,
  teachers: 88,
  centres: 4,
  centre_members: 19,
  students: 901,
  guardians: 377,
  batches: 140,
  seats: 1650,
  platforms: [
    { platform: 'android', accounts: 1100, active_7_days: 600, active_30_days: 900 },
    { platform: 'web', accounts: 210, active_7_days: 70, active_30_days: 150 },
  ],
  both_platforms: 96,
  no_platform: 20,
  versions: [
    { platform: 'android', version: '1.4.0', accounts: 800 },
    { platform: 'web', version: '0.1.0', accounts: 150 },
  ],
  help_open: 3,
  help_answered: 5,
  help_closed: 41,
}

const forbidden = json(403, {
  error: { code: 'FORBIDDEN', message_key: 'authz.lens.not_available', retryable: false },
})

describe('Overview', () => {
  it('shows the server’s counts, with Android and web side by side', async () => {
    serve((_m, url) => (url.endsWith('/v1/admin/overview') ? json(200, overview) : undefined))
    renderAt('/')
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('640')).toBeInTheDocument()
    expect(screen.getByText('901')).toBeInTheDocument()
    expect(screen.getByText(en('web_admin_role_guardians'))).toBeInTheDocument()
    expect(
      screen.getByText(en('web_admin_platform_accounts', '1,100', '1,234')),
    ).toBeInTheDocument()
    expect(screen.getByText(en('web_admin_platform_active', '70', '150'))).toBeInTheDocument()
    expect(screen.getByText(en('web_admin_not_reported_help'))).toBeInTheDocument()
    expect(screen.getByText('1.4.0')).toBeInTheDocument()
    const open = screen.getByText(en('web_admin_status_open')).closest('a')!
    expect(open).toHaveAttribute('href', '/help/tickets?status=open')
    expect(within(open).getByText('3')).toBeInTheDocument()
  })

  it('sends the admin token, to the same origin', async () => {
    serve((_m, url) => (url === '/v1/admin/overview' ? json(200, overview) : undefined))
    renderAt('/')
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    const call = calls.find((c) => c.url === '/v1/admin/overview')!
    expect(call.headers.Authorization).toBe('Bearer ADMIN')
  })

  it('tells a number that is no longer an administrator, with Log out and no Try again', async () => {
    serve((_m, url) => (url.endsWith('/v1/admin/overview') ? forbidden : undefined))
    renderAt('/')
    expect(await screen.findByText(en('web_admin_not_admin_title'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
    expect(screen.queryByRole('navigation')).toBeNull()
    const main = screen.getByRole('main')
    await userEvent.click(within(main).getByRole('button', { name: en('more_log_out') }))
    expect(peekAdminSession()).toBeNull()
    expect(await screen.findByText(en('web_admin_signin_title'))).toBeInTheDocument()
  })

  it('says admin is not available here on a 404 from off the admin edge', async () => {
    serve(() =>
      json(404, {
        error: { code: 'NOT_AVAILABLE', message_key: 'authz.lens.not_available', retryable: false },
      }),
    )
    renderAt('/')
    expect(await screen.findByText(en('web_admin_unavailable'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()
  })
})

describe('Teachers & centres', () => {
  it('lists them, names the unnamed, and links a solo teacher to their questions', async () => {
    serve((_m, url) =>
      url.endsWith('/v1/admin/teachers')
        ? json(200, {
            workspaces: [
              {
                workspace_id: 'w1',
                kind: 'teacher',
                name: 'Karim Uddin',
                platforms: ['android', 'web'],
                joined_at: now,
                last_seen_at: now,
                ref: 'a1b2c3d4e5',
              },
              {
                workspace_id: 'w2',
                kind: 'centre',
                name: null,
                platforms: [],
                joined_at: now,
                last_seen_at: null,
                ref: null,
              },
            ],
          })
        : undefined,
    )
    renderAt('/teachers')
    expect(await screen.findByText('Karim Uddin')).toBeInTheDocument()
    expect(screen.getByText(en('web_admin_unnamed_centre'))).toBeInTheDocument()
    expect(screen.getByText(en('web_admin_never_seen'))).toBeInTheDocument()
    const links = screen.getAllByRole('link', { name: en('web_admin_help_questions') })
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', '/help/tickets?ref=a1b2c3d4e5')

    await userEvent.type(screen.getByRole('searchbox'), 'karim')
    expect(screen.queryByText(en('web_admin_unnamed_centre'))).toBeNull()
    expect(screen.getByText('Karim Uddin')).toBeInTheDocument()
  })
})

describe('Help centre, support side', () => {
  it('names teachers by name and everyone else only by role and reference', async () => {
    serve((_m, url) =>
      url.endsWith('/v1/admin/help/requesters')
        ? json(200, {
            requesters: [
              {
                requester: {
                  ref: '00aa11bb22',
                  roles: ['centre_member'],
                  name: 'Nasrin',
                  centre: 'Alo Coaching',
                },
                tickets: 2,
                open: 1,
                last_activity: now,
              },
              {
                requester: { ref: 'a1b2c3d4e5', roles: ['student'], name: null, centre: null },
                tickets: 1,
                open: 0,
                last_activity: now,
              },
              {
                // A name sent where none belongs is never drawn.
                requester: { ref: 'ffffeeee00', roles: ['guardian'], name: 'Rokeya Jahan' },
                tickets: 1,
                open: 0,
                last_activity: now,
              },
            ],
          })
        : undefined,
    )
    renderAt('/help')
    expect(await screen.findByText('Nasrin · Alo Coaching')).toBeInTheDocument()
    expect(screen.getByText('Student · #A1B2C3D4E5')).toBeInTheDocument()
    expect(screen.getByText('Guardian · #FFFFEEEE00')).toBeInTheDocument()
    expect(screen.queryByText(/Rokeya/)).toBeNull()
    expect(screen.getByText('Student · #A1B2C3D4E5').closest('a')).toHaveAttribute(
      'href',
      '/help/tickets?ref=a1b2c3d4e5',
    )
  })

  it('filters tickets by status on the server', async () => {
    serve((_m, url) =>
      url.includes('/v1/admin/help/tickets')
        ? json(200, {
            tickets: [
              {
                ticket_id: 't1',
                subject: 'Marks not saving',
                status: 'open',
                platform: 'web',
                created_at: now,
                updated_at: now,
                message_count: 3,
                preview: 'It spins',
                requester: { ref: 'a1b2c3d4e5', roles: ['guardian'] },
              },
            ],
          })
        : undefined,
    )
    renderAt('/help/tickets')
    expect(await screen.findByText('Marks not saving')).toBeInTheDocument()
    expect(screen.getByText('Guardian · #A1B2C3D4E5')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: en('web_admin_status_answered') }))
    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith('/v1/admin/help/tickets?status=answered'))).toBe(
        true,
      ),
    )
  })

  it('replies as support, then closes and reopens the ticket', async () => {
    const ticket = (status: string) => ({
      ticket_id: 't1',
      subject: 'Fee not showing',
      status,
      platform: 'android',
      created_at: now,
      updated_at: now,
      message_count: 1,
      preview: 'p',
      requester: { ref: 'a1b2c3d4e5', roles: ['student'] },
    })
    const first = {
      message_id: 'm1',
      author: 'requester',
      body: 'Where is my fee?',
      created_at: now,
    }
    const answer = {
      message_id: 'm2',
      author: 'support',
      body: 'Pull to refresh.',
      created_at: now,
    }
    serve((method, url) => {
      if (url.endsWith('/v1/admin/help/tickets/t1') && method === 'GET')
        return json(200, { ticket: ticket('open'), messages: [first] })
      if (url.endsWith('/v1/admin/help/tickets/t1/messages') && method === 'POST')
        return json(200, { ticket: ticket('answered'), messages: [first, answer] })
      if (url.endsWith('/v1/admin/help/tickets/t1/status') && method === 'PUT')
        return json(200, {
          ticket: ticket(calls.filter((c) => c.method === 'PUT').length === 1 ? 'closed' : 'open'),
          messages: [first, answer],
        })
      return undefined
    })
    renderAt('/help/tickets/t1')
    expect(await screen.findByText('Where is my fee?')).toBeInTheDocument()
    // The person who asked is a role and a reference, in the header and the thread.
    expect(screen.getAllByText('Student · #A1B2C3D4E5')).toHaveLength(2)

    await userEvent.type(screen.getByLabelText(en('web_admin_reply_label')), 'Pull to refresh.')
    await userEvent.click(screen.getByRole('button', { name: en('web_admin_reply_send') }))
    expect(await screen.findByText('Pull to refresh.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ body: 'Pull to refresh.' })
    expect(screen.getByText(en('web_admin_status_answered'))).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: en('web_admin_close') }))
    expect(await screen.findByRole('button', { name: en('web_admin_reopen') })).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'PUT')[0]!.body).toEqual({ status: 'closed' })

    await userEvent.click(screen.getByRole('button', { name: en('web_admin_reopen') }))
    expect(await screen.findByRole('button', { name: en('web_admin_close') })).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'PUT')[1]!.body).toEqual({ status: 'open' })
  })

  it('a refused ticket read shows the administrators-only page', async () => {
    serve(() => forbidden)
    renderAt('/help/tickets/t1')
    expect(await screen.findByText(en('web_admin_not_admin_title'))).toBeInTheDocument()
  })
})
