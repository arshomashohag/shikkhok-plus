/**
 * The guardian's own join requests [H5], signed in for real against a
 * fetch that answers like the API. What is asserted: More shows the row
 * only while the server lists a request; each request reads its status or
 * the owner's answer from the server's codes; a `call_us` answer offers
 * the owner's published number to call; a request whose listing is gone
 * still reads and can be withdrawn; and a withdrawal is sent only from
 * its confirmation, which says the request is deleted completely.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearTokens } from '../../api/tokens'
import { translate } from '../../i18n/i18n'
import { json } from '../../test/render'
import { mockSignedIn, renderRoutes, type Call } from '../../test/signedIn'
import { More } from './More'
import { MyEnquiries } from './MyEnquiries'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
const MINE = '/v1/me/hub/enquiries'
const E1 = 'a1111111-1111-4111-8111-111111111111'
const E2 = 'b2222222-2222-4222-8222-222222222222'

afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
  localStorage.clear()
})

const ROUTES = [
  { path: '/more', element: <More /> },
  { path: '/hub-enquiries', element: <MyEnquiries /> },
]

const request = (over: Record<string, unknown> = {}) => ({
  id: E1,
  owner_public_name: 'Sumi Akter',
  batch_title: 'Physics · Batch A',
  student_name: 'Tasnim',
  class_level: 'class_7',
  message: null,
  share_contact: true,
  status: 'open',
  outcome: null,
  sent_on: '2026-11-20',
  owner_contact_phone: null,
  ...over,
})

const deletes = (calls: Call[]) => calls.filter((c) => c.method === 'DELETE')

describe('My join requests', () => {
  it('More shows the row only while the server lists a request', async () => {
    const empty = mockSignedIn(
      (method, url) => (method === 'GET' && url.endsWith(MINE) ? json(200, []) : undefined),
      'guardian',
    )
    const { unmount } = renderRoutes(ROUTES, '/more')
    expect(await screen.findByText(en('more_log_out'))).toBeInTheDocument()
    await waitFor(() => expect(empty.some((c) => c.url.endsWith(MINE))).toBe(true))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByText('My join requests')).toBeNull()
    unmount()

    mockSignedIn(
      (method, url) =>
        method === 'GET' && url.endsWith(MINE) ? json(200, [request()]) : undefined,
      'teacher',
    )
    renderRoutes(ROUTES, '/more')
    // Any lens: a teacher may have asked another teacher for their own child.
    const row = await screen.findByRole('link', { name: /My join requests/ })
    await userEvent.click(row)
    expect(await screen.findByText('Tasnim')).toBeInTheDocument()
  })

  it('reads each status from the server, with a fallback for a listing that is gone', async () => {
    mockSignedIn(
      (method, url) =>
        method === 'GET' && url.endsWith(MINE)
          ? json(200, [
              request(),
              request({
                id: E2,
                owner_public_name: null,
                batch_title: null,
                student_name: 'Rafi',
                status: 'closed',
                outcome: 'not_now',
              }),
            ])
          : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, '/hub-enquiries')

    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    const [open, closed] = items as [HTMLElement, HTMLElement]
    expect(within(open).getByText('Sumi Akter')).toBeInTheDocument()
    expect(within(open).getByText(/Physics · Batch A/)).toBeInTheDocument()
    expect(within(open).getByText(en('hub_enquiry_status_open'))).toBeInTheDocument()
    expect(within(closed).getByText(en('hub_enquiry_owner_unknown'))).toBeInTheDocument()
    expect(within(closed).getByText(en('hub_enquiry_outcome_not_now'))).toBeInTheDocument()
    // A closed request may be withdrawn too: withdrawal deletes it either way.
    expect(within(closed).getByRole('button', { name: 'Withdraw' })).toBeInTheDocument()
  })

  it('call_us shows owner number', async () => {
    mockSignedIn(
      (method, url) =>
        method === 'GET' && url.endsWith(MINE)
          ? json(200, [
              request({
                status: 'closed',
                outcome: 'call_us',
                owner_contact_phone: '+8801711000000',
              }),
            ])
          : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, '/hub-enquiries')

    expect(await screen.findByText(en('hub_enquiry_outcome_call_us'))).toBeInTheDocument()
    const call = screen.getByRole('link', { name: 'Call 01711-000000' })
    expect(call).toHaveAttribute('href', 'tel:+8801711000000')
  })

  it('a call_us answer without a number offers no link', async () => {
    mockSignedIn(
      (method, url) =>
        method === 'GET' && url.endsWith(MINE)
          ? json(200, [request({ status: 'closed', outcome: 'call_us' })])
          : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, '/hub-enquiries')
    expect(await screen.findByText(en('hub_enquiry_outcome_call_us'))).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Call / })).toBeNull()
  })

  it('my requests withdraw confirms then calls DELETE', async () => {
    let gone = false
    const calls = mockSignedIn((method, url) => {
      if (method === 'GET' && url.endsWith(MINE)) return json(200, gone ? [] : [request()])
      if (method === 'DELETE' && url.endsWith(`${MINE}/${E1}`)) {
        gone = true
        return new Response(null, { status: 204 })
      }
      return undefined
    }, 'guardian')
    renderRoutes(ROUTES, '/hub-enquiries')

    await userEvent.click(await screen.findByRole('button', { name: 'Withdraw' }))
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByText('This deletes your request completely.')).toBeInTheDocument()
    expect(deletes(calls)).toEqual([])

    // Cancel sends nothing.
    await userEvent.click(within(sheet).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(deletes(calls)).toEqual([])

    await userEvent.click(screen.getByRole('button', { name: 'Withdraw' }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Withdraw' }),
    )
    await waitFor(() => expect(deletes(calls)).toHaveLength(1))
    expect(deletes(calls)[0]!.url).toMatch(new RegExp(`${MINE}/${E1}$`))
    expect(await screen.findByText(en('hub_enquiry_withdrawn'))).toBeInTheDocument()
    expect(await screen.findByText(en('hub_enquiry_mine_empty'))).toBeInTheDocument()
  })

  it('a failed withdrawal keeps the request and offers retry', async () => {
    let attempt = 0
    const calls = mockSignedIn((method, url) => {
      if (method === 'GET' && url.endsWith(MINE)) return json(200, attempt > 1 ? [] : [request()])
      if (method === 'DELETE') {
        attempt += 1
        return attempt === 1
          ? json(503, {
              error: { code: 'UNAVAILABLE', message_key: 'error.unexpected', retryable: true },
            })
          : new Response(null, { status: 204 })
      }
      return undefined
    }, 'guardian')
    renderRoutes(ROUTES, '/hub-enquiries')

    await userEvent.click(await screen.findByRole('button', { name: 'Withdraw' }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Withdraw' }),
    )
    expect(await screen.findByText(/Your request was not withdrawn./)).toBeInTheDocument()
    expect(screen.getByText('Tasnim')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Withdraw' }),
    )
    await waitFor(() => expect(deletes(calls)).toHaveLength(2))
    expect(await screen.findByText(en('hub_enquiry_mine_empty'))).toBeInTheDocument()
  })
})
