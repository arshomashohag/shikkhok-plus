/**
 * Sharing interest in a listed batch [0049], opened from a public batch
 * page's "I'm interested" link: `/ui/hub-interest?owner=<slug>&batch=<id>`.
 *
 * What is asserted: the screen names whom the number would go to before
 * anything is sent; nothing is sent until the adult-guardian box is
 * ticked; the share carries the declaration and nothing typed; an interest
 * already shared and an account without a phone each say so instead of
 * offering to share; the switch being off reads as unavailable; a link
 * without a valid batch sends nothing.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../i18n/i18n'
import { json, renderScreen } from '../../test/render'
import { HubInterest } from './HubInterest'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
const BATCH = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const LINK = `/hub-interest?owner=sumi-apa&batch=${BATCH}`
const TARGET = `/v1/hub/owners/sumi-apa/batches/${BATCH}/interest-target`
const SHARE = `/v1/hub/owners/sumi-apa/batches/${BATCH}/interest`

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const target = (over: Record<string, unknown> = {}) => ({
  owner_public_name: 'Sumi Akter',
  batch_title: 'Physics · Batch A',
  has_phone: true,
  already_shared: false,
  ...over,
})

const shared = {
  id: 'i1',
  owner_public_name: 'Sumi Akter',
  batch_title: 'Physics · Batch A',
  status: 'open',
  shared_on: '2026-11-28',
}

function serve(read: () => Response, share: () => Response = () => json(201, shared)) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0]!
    if (path.endsWith(TARGET) && (init.method ?? 'GET') === 'GET') return read()
    if (path.endsWith(SHARE) && init.method === 'POST') return share()
    return json(404, {
      error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
    })
  })
}

const posts = () =>
  fetchMock.mock.calls
    .filter(([u, init]) => String(u).endsWith(SHARE) && (init as RequestInit)?.method === 'POST')
    .map(([, init]) => JSON.parse((init as RequestInit).body as string) as unknown)

describe('HubInterest', () => {
  it('names the owner, needs the declaration, then shares with nothing typed', async () => {
    serve(() => json(200, target()))
    renderScreen(<HubInterest />, LINK)

    expect(await screen.findByText('To Sumi Akter')).toBeInTheDocument()
    expect(screen.getByText('Physics · Batch A')).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_interest_explain', 'Sumi Akter'))).toBeInTheDocument()
    const declaration = screen.getByRole('checkbox', { name: en('hub_enquiry_declaration') })
    expect(declaration).not.toBeChecked()

    const share = screen.getByRole('button', { name: 'Share my number' })
    await userEvent.click(share)
    expect(await screen.findByText(en('web_hub_interest_declaration_required'))).toBeInTheDocument()
    expect(posts()).toEqual([])

    await userEvent.click(declaration)
    await userEvent.click(share)
    await waitFor(() => expect(posts()).toEqual([{ declares_adult_guardian: true }]))
    expect(await screen.findByText(en('web_hub_interest_shared', 'Sumi Akter'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: en('hub_enquiry_mine_link') })).toBeInTheDocument()
  })

  it('an interest already shared shows the way to it instead of a button', async () => {
    serve(() => json(200, target({ already_shared: true })))
    renderScreen(<HubInterest />, LINK)

    expect(await screen.findByText(en('web_hub_interest_already'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Share my number' })).toBeNull()
  })

  it('an account without a phone is sent to add one, and nothing is offered', async () => {
    serve(() => json(200, target({ has_phone: false })))
    renderScreen(<HubInterest />, LINK)

    expect(await screen.findByText(en('hub_interest_needs_phone'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: en('web_hub_interest_add_phone') })).toHaveAttribute(
      'href',
      '/settings/contact/phone',
    )
    expect(screen.queryByRole('button', { name: 'Share my number' })).toBeNull()
  })

  it('reads as unavailable while join requests are switched off', async () => {
    serve(() =>
      json(404, {
        error: { code: 'HUB_ENQUIRIES_OFF', message_key: 'hub.enquiry.off', retryable: false },
      }),
    )
    renderScreen(<HubInterest />, LINK)

    expect(await screen.findByText(en('hub_enquiry_off'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Share my number' })).toBeNull()
  })

  it('a link without a valid batch reads not valid and reads nothing', async () => {
    serve(() => json(200, target()))
    renderScreen(<HubInterest />, '/hub-interest?owner=sumi-apa&batch=not-a-uuid')

    expect(await screen.findByText(en('hub_report_link_invalid'))).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/interest'))).toEqual([])
  })
})
