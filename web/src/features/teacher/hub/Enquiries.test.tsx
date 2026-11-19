/**
 * The owner's join requests [H5]: the listing editor's switch and row, the
 * inbox list, one request, and "Add as student" through the prefilled
 * add-student form, against a fetch that answers like the API.
 *
 * What is asserted: the switch exists only while the server offers it and
 * the row only while the inbox read succeeds, so `HUB_ENQUIRIES_OFF` draws
 * neither and no error; the inbox itself, opened while off, says join
 * requests are unavailable; the list is drawn in the server's order; the
 * guardian's contact is a link only when the server sent one; the answers
 * offered are exactly `outcomes_allowed`; a refused answer reads in the
 * server's words; and adding a student from a request fills the form,
 * saves the student, then answers `added`, keeping the saved student and
 * offering Retry when only the answer failed.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../../i18n/i18n'
import { json, renderScreen } from '../../../test/render'
import { NewStudent } from '../people/NewStudent'
import { EnquiryDetail, OwnerEnquiries } from './Enquiries'
import { HubListing } from './Listing'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
const BATCH = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const E1 = 'a1111111-1111-4111-8111-111111111111'
const E2 = 'b2222222-2222-4222-8222-222222222222'
const INBOX = '/v1/hub/enquiries'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const refusal = (status: number, code: string, key: string, retryable = false) =>
  json(status, { error: { code, message_key: key, retryable } })
const OFF = () => refusal(404, 'HUB_ENQUIRIES_OFF', 'hub.enquiry.off')

const enquiry = (over: Record<string, unknown> = {}) => ({
  id: E1,
  batch_id: BATCH,
  batch_title: 'Physics · Batch A',
  student_name: 'Tasnim',
  class_level: 'class_7',
  message: 'Weak in algebra',
  status: 'open',
  outcome: null,
  received_at: '2026-11-20T04:30:00Z',
  guardian_phone: '+8801711000001',
  guardian_email: null,
  outcomes_allowed: ['added', 'not_now', 'call_us'],
  ...over,
})

const listing = (over: Record<string, unknown> = {}) => ({
  status: 'published',
  slug: 'sumi-apa',
  public_name: 'Sumi Akter',
  public_name_latin: null,
  headline_en: 'Maths and science',
  headline_bn: null,
  bio_en: 'Ten years of teaching.',
  bio_bn: null,
  qualifications: null,
  teaching_mode: ['in_person'],
  district_code: null,
  upazila_code: null,
  street_address: null,
  public_contact_phone: '+8801711999999',
  consent_version: '2026-11-14',
  published_at: '2026-11-15T10:00:00Z',
  checklist: [],
  publishable: true,
  runs_classes: false,
  consent_version_current: '2026-11-14',
  is_centre: false,
  accepts_enquiries: false,
  enquiries_offered: true,
  ...over,
})

type Extra = (method: string, url: string, body: unknown) => Response | undefined

/** Listing, areas and photos answer; `extra` answers first; the rest is a 404. */
function serve(extra: Extra, own = listing()) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET'
    const body = init.body ? (JSON.parse(init.body as string) as unknown) : undefined
    const made = extra(method, url, body)
    if (made) return made
    if (url.endsWith('/v1/hub/listing') && method === 'GET') return json(200, own)
    if (url.includes('/v1/hub/areas') || url.includes('/v1/hub/media')) return json(200, [])
    return refusal(404, 'NOT_FOUND', 'error.unexpected')
  })
}

const calls = (method: string, needle: string) =>
  fetchMock.mock.calls
    .filter(
      ([u, init]) =>
        String(u).split('?')[0]!.endsWith(needle) &&
        ((init as RequestInit)?.method ?? 'GET') === method,
    )
    .map(([u, init]) => ({
      url: String(u),
      body: (init as RequestInit).body
        ? (JSON.parse((init as RequestInit).body as string) as unknown)
        : undefined,
    }))

describe('The listing editor', () => {
  it('owner inbox hidden on HUB_ENQUIRIES_OFF', async () => {
    serve((method, url) => (method === 'GET' && url.endsWith(INBOX) ? OFF() : undefined))
    const { unmount } = renderScreen(<HubListing />)
    expect(await screen.findByDisplayValue('Sumi Akter')).toBeInTheDocument()
    await waitFor(() => expect(calls('GET', INBOX)).toHaveLength(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByRole('link', { name: /Join requests/ })).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    unmount()

    // Opened directly while off: a plain "not available", no retry.
    renderScreen(<OwnerEnquiries />)
    expect(await screen.findByText(en('hub_enquiry_off'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()

    fetchMock.mockReset()
    serve((method, url) => (method === 'GET' && url.endsWith(INBOX) ? json(200, []) : undefined))
    renderScreen(<HubListing />)
    const row = await screen.findByRole('link', { name: /Join requests/ })
    expect(row).toHaveAttribute('href', '/more/hub/enquiries')
  })

  it('listing toggle hidden when not offered', async () => {
    serve(() => undefined, listing({ enquiries_offered: false, accepts_enquiries: true }))
    const { unmount } = renderScreen(<HubListing />)
    expect(await screen.findByDisplayValue('Sumi Akter')).toBeInTheDocument()
    expect(screen.queryByRole('switch', { name: en('hub_enquiry_switch') })).toBeNull()
    unmount()

    fetchMock.mockReset()
    serve((method, url, body) =>
      method === 'PUT' && url.endsWith('/v1/hub/listing')
        ? json(200, listing({ ...(body as object) }))
        : undefined,
    )
    renderScreen(<HubListing />)
    const toggle = await screen.findByRole('switch', { name: en('hub_enquiry_switch') })
    expect(toggle).not.toBeChecked()
    // Typed but unsaved changes survive the switch.
    await userEvent.type(screen.getByDisplayValue('Maths and science'), ' for SSC')
    await userEvent.click(toggle)
    await waitFor(() => expect(toggle).toBeChecked())
    expect(calls('PUT', '/v1/hub/listing').map((c) => c.body)).toEqual([
      { accepts_enquiries: true },
    ])
    expect(screen.getByDisplayValue('Maths and science for SSC')).toBeInTheDocument()
  })

  it('a failed switch stays at what the server holds and offers retry', async () => {
    let attempt = 0
    serve(
      (method, url, body) => {
        if (method !== 'PUT' || !url.endsWith('/v1/hub/listing')) return undefined
        attempt += 1
        return attempt === 1
          ? refusal(503, 'UNAVAILABLE', 'error.unexpected', true)
          : json(200, listing({ ...(body as object) }))
      },
      listing({ accepts_enquiries: true }),
    )
    renderScreen(<HubListing />)
    const toggle = await screen.findByRole('switch', { name: en('hub_enquiry_switch') })
    expect(toggle).toBeChecked()
    await userEvent.click(toggle)
    expect(await screen.findByText(new RegExp(en('hub_enquiry_switch_failed')))).toBeInTheDocument()
    expect(toggle).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: en('web_hub_retry') }))
    await waitFor(() => expect(toggle).not.toBeChecked())
    expect(calls('PUT', '/v1/hub/listing').map((c) => c.body)).toEqual([
      { accepts_enquiries: false },
      { accepts_enquiries: false },
    ])
  })
})

describe('The inbox', () => {
  it('lists requests in the server order, open ones first', async () => {
    serve((method, url) =>
      method === 'GET' && url.endsWith(INBOX)
        ? json(200, [
            enquiry(),
            enquiry({
              id: E2,
              batch_id: null,
              batch_title: null,
              student_name: 'Rafi',
              status: 'closed',
              outcome: 'call_us',
              outcomes_allowed: [],
            }),
          ])
        : undefined,
    )
    renderScreen(<OwnerEnquiries />)

    const list = await screen.findByRole('list', { name: en('hub_enquiry_inbox_title') })
    const rows = within(list).getAllByRole('link')
    expect(rows.map((r) => within(r).getByText(/Tasnim|Rafi/).textContent)).toEqual([
      'Tasnim',
      'Rafi',
    ])
    expect(rows[0]).toHaveAttribute('href', `/more/hub/enquiries/${E1}`)
    expect(within(rows[0]!).getByText(en('hub_enquiry_needs_answer'))).toBeInTheDocument()
    expect(within(rows[0]!).getByText(/Class 7 · Physics · Batch A/)).toBeInTheDocument()
    expect(within(rows[1]!).getByText(en('hub_enquiry_answered_call_us'))).toBeInTheDocument()
    expect(within(rows[1]!).getByText(/Any class/)).toBeInTheDocument()
    // Nothing the guardian shared is on the list.
    expect(list.textContent).not.toContain('01711')
  })

  it('says so when there are none', async () => {
    serve((method, url) => (method === 'GET' && url.endsWith(INBOX) ? json(200, []) : undefined))
    renderScreen(<OwnerEnquiries />)
    expect(await screen.findByText(en('hub_enquiry_inbox_empty'))).toBeInTheDocument()
  })
})

function renderDetail(path = `/more/hub/enquiries/${E1}`) {
  return renderScreen(
    <Routes>
      <Route path="/more/hub/enquiries/:enquiryId" element={<EnquiryDetail />} />
      <Route path="/students/new" element={<NewStudent />} />
    </Routes>,
    path,
  )
}

describe('One request', () => {
  it('owner detail shows contact only when shared', async () => {
    let body = enquiry()
    serve((method, url) =>
      method === 'GET' && url.endsWith(`${INBOX}/${E1}`) ? json(200, body) : undefined,
    )
    const first = renderDetail()
    expect(await screen.findByText('Tasnim')).toBeInTheDocument()
    expect(screen.getByText('Class 7')).toBeInTheDocument()
    expect(screen.getByText('Weak in algebra')).toBeInTheDocument()
    expect(screen.getByText('Physics · Batch A')).toBeInTheDocument()
    expect(screen.getByText(/20 Nov 2026/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '01711-000001' })).toHaveAttribute(
      'href',
      'tel:+8801711000001',
    )
    first.unmount()

    body = enquiry({ guardian_phone: null, guardian_email: 'rina@example.com' })
    const second = renderDetail()
    expect(await screen.findByRole('link', { name: 'rina@example.com' })).toHaveAttribute(
      'href',
      'mailto:rina@example.com',
    )
    second.unmount()

    body = enquiry({ guardian_phone: null, guardian_email: null, outcomes_allowed: ['not_now'] })
    renderDetail()
    expect(await screen.findByText(en('hub_enquiry_contact_not_shared'))).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /01711|@/ })).toBeNull()
    // Only what the server allows is offered.
    expect(screen.getByRole('button', { name: 'Not now' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add as student' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Ask them to call' })).toBeNull()
  })

  it('answers with the outcome chosen and shows the answered state', async () => {
    serve((method, url, body) => {
      if (method === 'GET' && url.endsWith(`${INBOX}/${E1}`)) return json(200, enquiry())
      if (method === 'POST' && url.endsWith(`${INBOX}/${E1}/close`))
        return json(
          200,
          enquiry({
            status: 'closed',
            outcome: (body as { outcome: string }).outcome,
            outcomes_allowed: [],
          }),
        )
      return undefined
    })
    renderDetail()
    await userEvent.click(await screen.findByRole('button', { name: 'Ask them to call' }))
    expect(await screen.findByText(en('hub_enquiry_answered_call_us'))).toBeInTheDocument()
    expect(calls('POST', `${INBOX}/${E1}/close`).map((c) => c.body)).toEqual([
      { outcome: 'call_us' },
    ])
    expect(screen.queryByRole('button', { name: 'Not now' })).toBeNull()
  })

  it('a refused answer reads in the server words', async () => {
    serve((method, url) => {
      if (method === 'GET' && url.endsWith(`${INBOX}/${E1}`)) return json(200, enquiry())
      if (method === 'POST')
        return refusal(409, 'ENQUIRY_ALREADY_CLOSED', 'hub.enquiry.already_closed')
      return undefined
    })
    renderDetail()
    await userEvent.click(await screen.findByRole('button', { name: 'Not now' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(en('hub_enquiry_already_closed'))
    expect(within(alert).queryByRole('button')).toBeNull()
  })

  it('a request that is gone or switched off reads as unavailable', async () => {
    serve((method, url) =>
      method === 'GET' && url.endsWith(`${INBOX}/${E1}`)
        ? refusal(404, 'ENQUIRY_NOT_FOUND', 'hub.enquiry.not_found')
        : undefined,
    )
    const { unmount } = renderDetail()
    expect(await screen.findByText(en('hub_enquiry_not_found'))).toBeInTheDocument()
    unmount()

    fetchMock.mockReset()
    serve((method, url) => (method === 'GET' && url.endsWith(`${INBOX}/${E1}`) ? OFF() : undefined))
    renderDetail()
    expect(await screen.findByText(en('hub_enquiry_off'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Not now' })).toBeNull()
  })
})

const batch = (id: string, name: string) => ({
  id,
  name,
  active: true,
  enrollment_count: 0,
  accepted_count: 0,
  default_fee: '1200.00',
  fee_due_day: 10,
  marksheet_visible: false,
  schedule: [],
  subject_options: [],
  subjects: ['Physics'],
  teacher_display_name: null,
})

const created = {
  student_id: 's9',
  display_name: 'Tasnim',
  student_phone: null,
  guardian_phone: '01711000001',
  student_email: null,
  guardian_email: null,
  student_state: 'absent',
  guardian_state: 'pending',
  enrollments: [],
  total_outstanding: '0.00',
  is_removable: false,
}

describe('Add as student', () => {
  function serveAdd(close: () => Response | Promise<Response>, detail = enquiry()) {
    let closed = false
    serve((method, url) => {
      if (method === 'GET' && url.endsWith(`${INBOX}/${E1}`))
        return json(
          200,
          closed ? { ...detail, status: 'closed', outcome: 'added', outcomes_allowed: [] } : detail,
        )
      if (method === 'POST' && url.endsWith(`${INBOX}/${E1}/close`)) {
        const answer = close()
        return answer instanceof Response && answer.ok
          ? ((closed = true), answer)
          : (answer as Response)
      }
      if (url.endsWith('/v1/batches'))
        return json(200, [batch('b0', 'Chemistry B'), batch(BATCH, 'Physics A')])
      if (method === 'GET' && url.split('?')[0]!.endsWith('/v1/students')) return json(200, [])
      if (method === 'POST' && url.endsWith('/v1/students')) return json(201, created)
      return undefined
    })
  }

  it('add as student prefills and closes with added after save', async () => {
    serveAdd(() => json(200, enquiry({ status: 'closed', outcome: 'added', outcomes_allowed: [] })))
    renderDetail()
    await userEvent.click(await screen.findByRole('button', { name: 'Add as student' }))

    // The form, filled from the request the server holds.
    expect(await screen.findByText(en('hub_enquiry_prefilled'))).toBeInTheDocument()
    expect(screen.getByLabelText('Student name')).toHaveValue('Tasnim')
    expect(screen.getByLabelText('Guardian phone (optional)')).toHaveValue('01711-000001')
    expect(screen.getByLabelText('Fee in Physics A (optional)')).toBeInTheDocument()
    expect(calls('GET', `${INBOX}/${E1}`).length).toBeGreaterThanOrEqual(2)

    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    await waitFor(() => expect(calls('POST', `${INBOX}/${E1}/close`)).toHaveLength(1))
    expect(calls('POST', '/v1/students').map((c) => c.body)).toEqual([
      expect.objectContaining({
        display_name: 'Tasnim',
        guardian_phone: '01711000001',
        enrollments: [{ batch_id: BATCH, fee_amount: null }],
      }),
    ])
    expect(calls('POST', `${INBOX}/${E1}/close`).map((c) => c.body)).toEqual([{ outcome: 'added' }])
    // Back on the request, now answered.
    expect(await screen.findByText(en('hub_enquiry_answered_added'))).toBeInTheDocument()
  })

  it('fills a shared email when the guardian has no phone', async () => {
    serveAdd(
      () => json(200, enquiry()),
      enquiry({ guardian_phone: null, guardian_email: 'rina@example.com', batch_id: null }),
    )
    renderScreen(
      <Routes>
        <Route path="/students/new" element={<NewStudent />} />
      </Routes>,
      `/students/new?enquiry=${E1}`,
    )
    expect(await screen.findByLabelText('Guardian email (optional)')).toHaveValue(
      'rina@example.com',
    )
    expect(screen.getByLabelText('Guardian phone (optional)')).toHaveValue('')
    expect(screen.getByText(en('student_add_no_batch'))).toBeInTheDocument()
  })

  it('close failure after save keeps student and offers retry', async () => {
    let attempt = 0
    serveAdd(() => {
      attempt += 1
      if (attempt === 1) throw new TypeError('Failed to fetch')
      return json(200, enquiry({ status: 'closed', outcome: 'added', outcomes_allowed: [] }))
    })
    renderDetail()
    await userEvent.click(await screen.findByRole('button', { name: 'Add as student' }))
    await screen.findByText(en('hub_enquiry_prefilled'))
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(en('hub_enquiry_saved_not_closed'))
    expect(calls('POST', '/v1/students')).toHaveLength(1)
    // The student is saved: nothing offers to save it again.
    expect(screen.getByRole('button', { name: 'Add student' })).toBeDisabled()

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(en('hub_enquiry_answered_added'))).toBeInTheDocument()
    expect(calls('POST', `${INBOX}/${E1}/close`)).toHaveLength(2)
    expect(calls('POST', '/v1/students')).toHaveLength(1)
  })
})
