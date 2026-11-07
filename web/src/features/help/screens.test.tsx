/**
 * The help centre against a mocked API, signed in for real.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens } from '../../api/tokens'
import { translate, translateMessage } from '../../i18n/i18n'
import { json } from '../../test/render'
import { mockSignedIn, renderRoutes, type Call, type Handler } from '../../test/signedIn'
import { More } from '../account/More'
import { resetUnreadCount } from '../account/area/unread'
import { helpRoutes } from './index'
import { resetNewReplies } from './newReplies'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
const routes = [...helpRoutes, { path: '/more', element: <More /> }]
let calls: Call[] = []

const now = new Date().toISOString()
function ticket(id: string, patch: Record<string, unknown> = {}) {
  return {
    ticket_id: id,
    subject: `Question ${id}`,
    status: 'open',
    created_at: now,
    updated_at: now,
    has_new_reply: false,
    preview: `Preview ${id}`,
    ...patch,
  }
}
function detail(status: 'open' | 'answered' | 'closed', extra: object[] = []) {
  return {
    ticket: ticket('t1', { status }),
    messages: [
      { message_id: 'm1', author: 'requester', body: 'How do I add a batch?', created_at: now },
      { message_id: 'm2', author: 'support', body: 'Use the + button.', created_at: now },
      ...extra,
    ],
  }
}
const error = (status: number, key: string, retryable: boolean) =>
  json(status, { error: { code: 'X', message_key: key, retryable } })

function serve(handler: Handler, lens: 'teacher' | 'student' | 'guardian' = 'teacher') {
  calls = mockSignedIn(handler, lens)
}

beforeEach(() => {
  localStorage.clear()
  resetUnreadCount()
  resetNewReplies()
})
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

describe('Help centre list', () => {
  it('lists questions with where each stands, and the new-reply mark', async () => {
    serve(
      (method, url) =>
        url.endsWith('/v1/me/help/tickets') && method === 'GET'
          ? json(200, {
              new_replies: 1,
              tickets: [
                ticket('t1', { status: 'answered', has_new_reply: true }),
                ticket('t2', { status: 'open' }),
                ticket('t3', { status: 'closed' }),
              ],
            })
          : undefined,
      'student',
    )
    renderAt('/help')
    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(3)
    expect(within(rows[0]!).getByText(en('help_status_answered'))).toBeInTheDocument()
    expect(within(rows[0]!).getByText(en('help_new_reply'))).toBeInTheDocument()
    expect(within(rows[1]!).getByText(en('help_status_open'))).toBeInTheDocument()
    expect(within(rows[1]!).queryByText(en('help_new_reply'))).toBeNull()
    expect(within(rows[2]!).getByText(en('help_status_closed'))).toBeInTheDocument()
    expect(screen.getByText(en('web_help_new_replies', 1))).toBeInTheDocument()
    expect(within(rows[0]!).getByRole('link')).toHaveAttribute('href', '/help/t1')
  })

  it('explains itself when empty and offers to ask', async () => {
    serve((_m, url) =>
      url.endsWith('/v1/me/help/tickets') ? json(200, { new_replies: 0, tickets: [] }) : undefined,
    )
    renderAt('/help')
    expect(await screen.findByText(en('help_empty_title'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: en('help_ask') })).toHaveAttribute('href', '/help/new')
  })

  it('says why it failed and tries again', async () => {
    let fail = true
    serve((_m, url) => {
      if (!url.endsWith('/v1/me/help/tickets')) return undefined
      if (fail) return error(503, 'error.unexpected', true)
      return json(200, { new_replies: 0, tickets: [ticket('t1')] })
    })
    renderAt('/help')
    const retry = await screen.findByRole('button', { name: en('auth_retry') })
    fail = false
    await userEvent.click(retry)
    expect(await screen.findByText('Question t1')).toBeInTheDocument()
  })

  it('shows the count of new replies on More', async () => {
    serve((_m, url) =>
      url.endsWith('/v1/me/help/tickets')
        ? json(200, { new_replies: 2, tickets: [ticket('t1', { has_new_reply: true })] })
        : undefined,
    )
    renderAt('/more')
    const row = (await screen.findByText(en('more_help'))).closest('a')!
    expect(row).toHaveAttribute('href', '/help')
    expect(await within(row).findByLabelText(en('web_help_new_replies', 2))).toHaveTextContent('2')
  })
})

describe('Ask a question', () => {
  it('refuses a blank question without sending, then sends it trimmed', async () => {
    serve((method, url) => {
      if (url.endsWith('/v1/me/help/tickets') && method === 'POST') return json(201, detail('open'))
      if (url.endsWith('/v1/me/help/tickets/t1')) return json(200, detail('open'))
      return undefined
    })
    renderAt('/help/new')
    expect(await screen.findByText(en('help_privacy_hint'))).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: en('help_send') }))
    expect(screen.getAllByText(en('web_help_required'))).toHaveLength(2)
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)

    await userEvent.type(screen.getByLabelText(en('help_subject_label')), '  Adding a batch ')
    await userEvent.type(screen.getByLabelText(en('help_body_label')), 'Where is the button?')
    expect(screen.getByText(en('help_char_count', 14, 120))).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: en('help_send') }))

    expect(await screen.findByText(en('web_help_sent'))).toBeInTheDocument()
    const post = calls.find((c) => c.method === 'POST')!
    expect(post.body).toEqual({ subject: 'Adding a batch', body: 'Where is the button?' })
  })

  it('flags a subject over the limit', async () => {
    serve(() => undefined)
    renderAt('/help/new')
    const subject = await screen.findByLabelText(en('help_subject_label'))
    await userEvent.click(subject)
    await userEvent.paste('x'.repeat(121))
    await userEvent.type(screen.getByLabelText(en('help_body_label')), 'Body')
    await userEvent.click(screen.getByRole('button', { name: en('help_send') }))
    expect(screen.getByText(en('web_help_too_long', 120))).toBeInTheDocument()
    expect(subject).toHaveAttribute('aria-invalid', 'true')
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('says when too many questions were asked today, without offering to retry', async () => {
    serve((method, url) =>
      url.endsWith('/v1/me/help/tickets') && method === 'POST'
        ? error(409, 'help.ticket.too_many', false)
        : undefined,
    )
    renderAt('/help/new')
    await userEvent.type(await screen.findByLabelText(en('help_subject_label')), 'S')
    await userEvent.type(screen.getByLabelText(en('help_body_label')), 'B')
    await userEvent.click(screen.getByRole('button', { name: en('help_send') }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(translateMessage('en', 'help.ticket.too_many'))
    expect(within(alert).queryByRole('button')).toBeNull()
    // What was typed is still there.
    expect(screen.getByLabelText(en('help_subject_label'))).toHaveValue('S')
  })

  it('offline: says nothing was sent, and Try again sends it', async () => {
    let offline = true
    serve((method, url) => {
      // A thrown TypeError is how fetch reports no connection.
      if (offline && method === 'POST') throw new TypeError('Failed to fetch')
      if (url.endsWith('/v1/me/help/tickets') && method === 'POST') return json(201, detail('open'))
      if (url.endsWith('/v1/me/help/tickets/t1')) return json(200, detail('open'))
      return undefined
    })
    renderAt('/help/new')
    await userEvent.type(await screen.findByLabelText(en('help_subject_label')), 'S')
    await userEvent.type(screen.getByLabelText(en('help_body_label')), 'B')
    await userEvent.click(screen.getByRole('button', { name: en('help_send') }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(en('web_help_send_offline'))
    offline = false
    await userEvent.click(within(alert).getByRole('button', { name: en('auth_retry') }))
    expect(await screen.findByText(en('web_help_sent'))).toBeInTheDocument()
  })
})

describe('A question’s thread', () => {
  it('labels support’s messages and replies on the thread', async () => {
    serve((method, url, body) => {
      if (url.endsWith('/v1/me/help/tickets/t1') && method === 'GET')
        return json(200, detail('answered'))
      if (url.endsWith('/v1/me/help/tickets/t1/messages') && method === 'POST')
        return json(
          200,
          detail('open', [
            {
              message_id: 'm3',
              author: 'requester',
              body: (body as { body: string }).body,
              created_at: now,
            },
          ]),
        )
      return undefined
    })
    renderAt('/help/t1')
    expect(await screen.findByText('Use the + button.')).toBeInTheDocument()
    expect(screen.getByText(en('help_from_support'))).toBeInTheDocument()
    expect(screen.getByText(en('help_from_you'))).toBeInTheDocument()
    expect(screen.queryByText(en('help_closed_notice'))).toBeNull()

    await userEvent.type(screen.getByLabelText(en('help_reply_label')), '  Thanks, found it ')
    await userEvent.click(screen.getByRole('button', { name: en('web_help_reply_send') }))
    expect(await screen.findByText('Thanks, found it')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ body: 'Thanks, found it' })
    expect(screen.getByLabelText(en('help_reply_label'))).toHaveValue('')
  })

  it('warns that replying reopens a closed question', async () => {
    serve((_m, url) =>
      url.endsWith('/v1/me/help/tickets/t1') ? json(200, detail('closed')) : undefined,
    )
    renderAt('/help/t1')
    expect(await screen.findByText(en('help_closed_notice'))).toBeInTheDocument()
    expect(screen.getByText(en('help_status_closed'))).toBeInTheDocument()
  })

  it('says a question that is not there is not there', async () => {
    serve((_m, url) =>
      url.endsWith('/v1/me/help/tickets/t1')
        ? error(404, 'help.ticket.not_found', false)
        : undefined,
    )
    renderAt('/help/t1')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(translateMessage('en', 'help.ticket.not_found'))
    expect(within(alert).queryByRole('button')).toBeNull()
  })

  it('a failed reply keeps the text and offers Try again', async () => {
    let fail = true
    serve((method, url) => {
      if (url.endsWith('/v1/me/help/tickets/t1') && method === 'GET')
        return json(200, detail('open'))
      if (url.endsWith('/messages')) {
        if (fail) {
          fail = false
          return error(503, 'error.unexpected', true)
        }
        return json(200, detail('open'))
      }
      return undefined
    })
    renderAt('/help/t1')
    await userEvent.type(await screen.findByLabelText(en('help_reply_label')), 'Hello')
    await userEvent.click(screen.getByRole('button', { name: en('web_help_reply_send') }))
    const alert = await screen.findByRole('alert')
    expect(screen.getByLabelText(en('help_reply_label'))).toHaveValue('Hello')
    await userEvent.click(within(alert).getByRole('button', { name: en('auth_retry') }))
    await waitFor(() => expect(screen.getByLabelText(en('help_reply_label'))).toHaveValue(''))
  })
})

function renderAt(path: string) {
  return renderRoutes(routes, path)
}

it('every request names the web client', async () => {
  serve((_m, url) =>
    url.endsWith('/v1/me/help/tickets') ? json(200, { new_replies: 0, tickets: [] }) : undefined,
  )
  renderAt('/help')
  await screen.findByText(en('help_empty_title'))
  for (const c of calls) expect(c.headers['X-Client-Platform']).toBe('web')
})
