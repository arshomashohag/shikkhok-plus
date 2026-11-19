/**
 * The join-request form, opened from a public page's "Ask to join" link:
 * `/ui/hub-enquiry?owner=<slug>[&batch=<id>]` [H5].
 *
 * What is asserted: the target is the link's and the server names it; the
 * share choice and the declaration are both required before anything is
 * sent, and the share choice starts unchosen; an open request already with
 * this owner shows the way to it instead of a form; every refusal reads in
 * the server's words with what was typed kept; join requests switched off
 * reads as unavailable; and a signed-out guardian is taken through sign-in
 * and back to the form.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../../App'
import { clearTokens } from '../../api/tokens'
import { BUNDLES, I18nProvider, translate } from '../../i18n/i18n'
import { PwaProvider } from '../../pwa/pwa'
import { SessionProvider } from '../../session/session'
import { json, renderScreen } from '../../test/render'
import { HubEnquiry } from './HubEnquiry'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
const BATCH = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const FORM = `/hub-enquiry?owner=sumi-apa&batch=${BATCH}`
const TARGET = '/v1/hub/owners/sumi-apa/enquiry-target'
const SEND = '/v1/hub/owners/sumi-apa/enquiries'

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

const target = (over: Record<string, unknown> = {}) => ({
  owner_public_name: 'Sumi Akter',
  batch_title: 'Physics · Batch A',
  contact_kind: 'phone',
  already_open: false,
  ...over,
})

const refusal = (status: number, code: string, key: string, retryable = false) =>
  json(status, { error: { code, message_key: key, retryable } })

const OFF = () => refusal(404, 'HUB_ENQUIRIES_OFF', 'hub.enquiry.off')

const sent = {
  id: 'e1',
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
}

/** The target read and the send answer as given; anything else is a 404. */
function serve(
  read: () => Response | Promise<Response>,
  send: () => Response | Promise<Response> = () => json(201, sent),
) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0]!
    if (path.endsWith(TARGET) && (init.method ?? 'GET') === 'GET') return read()
    if (path.endsWith(SEND) && init.method === 'POST') return send()
    return refusal(404, 'NOT_FOUND', 'error.unexpected')
  })
}

const posts = () =>
  fetchMock.mock.calls
    .filter(([u, init]) => String(u).endsWith(SEND) && (init as RequestInit)?.method === 'POST')
    .map(([, init]) => JSON.parse((init as RequestInit).body as string) as unknown)

async function fillRequired() {
  await userEvent.type(await screen.findByLabelText("Student's name"), 'Tasnim')
  await userEvent.selectOptions(screen.getByLabelText('Class'), 'class_7')
}

const send = () => userEvent.click(screen.getByRole('button', { name: 'Send request' }))

describe('HubEnquiry', () => {
  it('form names the target and requires the share choice and declaration', async () => {
    serve(() => json(200, target()))
    renderScreen(<HubEnquiry />, FORM)

    expect(await screen.findByText('To Sumi Akter')).toBeInTheDocument()
    expect(screen.getByText('Physics · Batch A')).toBeInTheDocument()
    // The batch the link named is the one asked about.
    const read = fetchMock.mock.calls.find(([u]) => String(u).includes(TARGET))!
    expect(new URL(String(read[0]), 'http://x').searchParams.get('batch_id')).toBe(BATCH)

    const share = screen.getByRole('radio', { name: 'Share my phone number with Sumi Akter' })
    const keep = screen.getByRole('radio', { name: "Don't share it" })
    // Nothing is chosen for the guardian.
    expect(share).not.toBeChecked()
    expect(keep).not.toBeChecked()
    expect(screen.getByText(en('hub_enquiry_share_help'))).toBeInTheDocument()
    const declaration = screen.getByRole('checkbox', {
      name: "I am the student's parent or guardian, and 18 or older.",
    })
    expect(declaration).not.toBeChecked()

    await fillRequired()
    await send()
    expect(await screen.findByText(en('hub_enquiry_share_required'))).toBeInTheDocument()
    expect(screen.getByText(en('hub_enquiry_declaration_required'))).toBeInTheDocument()
    expect(posts()).toEqual([])

    await userEvent.click(share)
    await send()
    expect(screen.queryByText(en('hub_enquiry_share_required'))).toBeNull()
    expect(screen.getByText(en('hub_enquiry_declaration_required'))).toBeInTheDocument()
    expect(posts()).toEqual([])

    await userEvent.click(declaration)
    await userEvent.type(screen.getByLabelText('Message (optional)'), '  Weak in algebra  ')
    expect(screen.getByText('19/300')).toBeInTheDocument()
    await send()

    await waitFor(() =>
      expect(posts()).toEqual([
        {
          student_name: 'Tasnim',
          class_level: 'class_7',
          message: 'Weak in algebra',
          batch_id: BATCH,
          share_contact: true,
          declares_adult_guardian: true,
        },
      ]),
    )
    expect(await screen.findByText(en('hub_enquiry_sent'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See my join requests' })).toHaveAttribute(
      'href',
      '/hub-enquiries',
    )
  })

  it('an email account is asked about its email, and may send without sharing', async () => {
    serve(() => json(200, target({ contact_kind: 'email', batch_title: null })))
    renderScreen(<HubEnquiry />, '/hub-enquiry?owner=sumi-apa')

    expect(
      await screen.findByRole('radio', { name: 'Share my email address with Sumi Akter' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /phone number/ })).toBeNull()
    await fillRequired()
    await userEvent.click(screen.getByRole('radio', { name: "Don't share it" }))
    await userEvent.click(screen.getByRole('checkbox', { name: /parent or guardian/ }))
    await send()

    await waitFor(() =>
      expect(posts()).toEqual([
        {
          student_name: 'Tasnim',
          class_level: 'class_7',
          share_contact: false,
          declares_adult_guardian: true,
        },
      ]),
    )
  })

  it('already open shows link to my requests', async () => {
    serve(() => json(200, target({ already_open: true })))
    renderScreen(<HubEnquiry />, FORM)

    expect(
      await screen.findByText('You already have a request with this teacher'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See my join requests' })).toHaveAttribute(
      'href',
      '/hub-enquiries',
    )
    expect(screen.queryByRole('button', { name: 'Send request' })).toBeNull()
    expect(screen.queryByLabelText("Student's name")).toBeNull()
  })

  it('contact refusal shows server message', async () => {
    serve(
      () => json(200, target()),
      () =>
        json(400, {
          error: {
            code: 'ENQUIRY_CONTAINS_CONTACT',
            message_key: 'hub.enquiry.contains_contact',
            retryable: false,
            details: { field: 'message' },
          },
        }),
    )
    renderScreen(<HubEnquiry />, FORM)

    await fillRequired()
    await userEvent.type(screen.getByLabelText('Message (optional)'), 'Call 01711000000')
    await userEvent.click(screen.getByRole('radio', { name: "Don't share it" }))
    await userEvent.click(screen.getByRole('checkbox', { name: /parent or guardian/ }))
    await send()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(en('hub_enquiry_contains_contact'))
    expect(within(alert).queryByRole('button', { name: 'Try again' })).toBeNull()
    // What was typed stays, so the guardian can take the number out.
    expect(screen.getByLabelText('Message (optional)')).toHaveValue('Call 01711000000')
    expect(screen.getByRole('radio', { name: "Don't share it" })).toBeChecked()
  })

  it('the share choice uses the words the contact refusal tells the guardian to tick', () => {
    // "To give the teacher your number, tick Share": the box it names is the share choice.
    expect(translate('en', 'hub_enquiry_contains_contact')).toContain('tick Share')
    expect(translate('en', 'hub_enquiry_share_phone', 'X')).toMatch(/^Share /)
    expect(translate('en', 'hub_enquiry_share_email', 'X')).toMatch(/^Share /)
    expect(BUNDLES.bn.hub_enquiry_contains_contact).toContain('শেয়ার')
    expect(BUNDLES.bn.hub_enquiry_share_phone).toContain('শেয়ার')
    expect(BUNDLES.bn.hub_enquiry_share_email).toContain('শেয়ার')
  })

  it('a request already open at send time names it and links to my requests', async () => {
    serve(
      () => json(200, target()),
      () => refusal(409, 'ENQUIRY_ALREADY_OPEN', 'hub.enquiry.already_open'),
    )
    renderScreen(<HubEnquiry />, FORM)
    await fillRequired()
    await userEvent.click(screen.getByRole('radio', { name: /Share my phone/ }))
    await userEvent.click(screen.getByRole('checkbox', { name: /parent or guardian/ }))
    await send()

    expect(await screen.findByRole('alert')).toHaveTextContent(en('hub_enquiry_already_open'))
    expect(screen.getByRole('link', { name: 'See my join requests' })).toHaveAttribute(
      'href',
      '/hub-enquiries',
    )
  })

  it('a dropped connection keeps what was typed and offers retry', async () => {
    let attempt = 0
    serve(
      () => json(200, target()),
      () => {
        attempt += 1
        if (attempt === 1) throw new TypeError('Failed to fetch')
        return json(201, sent)
      },
    )
    renderScreen(<HubEnquiry />, FORM)
    await fillRequired()
    await userEvent.click(screen.getByRole('radio', { name: /Share my phone/ }))
    await userEvent.click(screen.getByRole('checkbox', { name: /parent or guardian/ }))
    await send()

    expect(await screen.findByText(/Your request was not sent./)).toBeInTheDocument()
    expect(screen.getByLabelText("Student's name")).toHaveValue('Tasnim')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(en('hub_enquiry_sent'))).toBeInTheDocument()
    expect(posts()).toHaveLength(2)
  })

  it.each([
    ['HUB_ENQUIRIES_OFF', OFF, 'hub_enquiry_off'],
    [
      'ENQUIRY_TARGET_NOT_FOUND',
      () => refusal(404, 'ENQUIRY_TARGET_NOT_FOUND', 'hub.enquiry.target_not_found'),
      'hub_enquiry_target_not_found',
    ],
  ])('a %s target reads as unavailable, with no form', async (_, read, key) => {
    serve(read)
    renderScreen(<HubEnquiry />, FORM)

    expect(await screen.findByText(en(key))).toBeInTheDocument()
    expect(screen.queryByLabelText("Student's name")).toBeNull()
    expect(screen.queryByRole('button', { name: 'Send request' })).toBeNull()
  })

  it.each([
    ['no owner', '/hub-enquiry'],
    ['an empty owner', '/hub-enquiry?owner='],
    ['a batch that is not a UUID', '/hub-enquiry?owner=sumi-apa&batch=physics'],
  ])('rejects a malformed link without a request: %s', async (_, path) => {
    serve(() => json(200, target()))
    renderScreen(<HubEnquiry />, path)

    expect(await screen.findByText(en('hub_report_link_invalid'))).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('HubEnquiry from a signed-out start', () => {
  it('signed-out enquiry link signs in then returns', async () => {
    window.history.replaceState(null, '', FORM)
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
          phone: '+8801711000001',
          username: 'rina_b',
          username_required: false,
          lenses: [{ kind: 'guardian', count: 1 }],
          workspaces: [],
        })
      if (method === 'GET' && url.split('?')[0]!.endsWith(TARGET)) return json(200, target())
      return refusal(404, 'NOT_FOUND', 'error.unexpected')
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

    expect(await screen.findByRole('heading', { name: 'Ask to join' })).toBeInTheDocument()
    expect(`${window.location.pathname}${window.location.search}`).toBe(FORM)
    expect(await screen.findByText('To Sumi Akter')).toBeInTheDocument()
  })
})
