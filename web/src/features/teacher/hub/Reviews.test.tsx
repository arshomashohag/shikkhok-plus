/**
 * The teacher's Reviews screen and its entry on the listing editor,
 * against a fetch that answers like the API. What is asserted: the entry
 * exists only when the reviews read succeeds, and `HUB_REVIEWS_OFF` draws
 * nothing at all; below the threshold a batch shows the server's nulls as
 * a neutral line, never a number; the average is the server's label; a
 * reply goes out and comes back awaiting review; and Report opens the
 * report form for that review.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../../i18n/i18n'
import { json, renderScreen } from '../../../test/render'
import { HubReport } from '../../common/HubReport'
import { HubListing } from './Listing'
import { OwnerReviews } from './Reviews'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)
const BATCH_A = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const BATCH_B = '1c0f9e8d-7c6b-4d5e-8f3a-2b1c0d9e8f7a'
const REVIEW = 'a1111111-1111-4111-8111-111111111111'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const OFF = () =>
  json(404, {
    error: { code: 'HUB_REVIEWS_OFF', message_key: 'hub.review.off', retryable: false },
  })

const card = (over: Record<string, unknown> = {}) => ({
  id: REVIEW,
  batch_id: BATCH_A,
  rating: 4,
  body: 'Clear and patient.',
  tenure: '6_12m',
  published_month: '2026-11',
  reply_body: null,
  reply_month: null,
  my_reply_status: null,
  my_reply_body: null,
  my_reply_rejection_code: null,
  ...over,
})

const owner = {
  batches: [
    {
      batch_id: BATCH_A,
      batch_title: 'Physics · Batch A',
      review_count: 3,
      average_tenths: 43,
      average_label: '4.3',
      distribution: [0, 0, 1, 0, 2],
    },
    {
      batch_id: BATCH_B,
      batch_title: 'Chemistry · Batch B',
      review_count: null,
      average_tenths: null,
      average_label: null,
      distribution: null,
    },
  ],
  reviews: [card()],
}

const listing = {
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
  public_contact_phone: null,
  consent_version: '2026-11-14',
  published_at: '2026-11-15T10:00:00Z',
  checklist: [],
  publishable: true,
  runs_classes: false,
  consent_version_current: '2026-11-14',
  is_centre: false,
}

function serve(
  reviews: () => Response,
  extra?: (url: string, init: RequestInit) => Response | undefined,
) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET'
    const made = extra?.(url, init)
    if (made) return made
    if (url.endsWith('/v1/hub/reviews') && method === 'GET') return reviews()
    if (url.endsWith('/v1/hub/listing') && method === 'GET') return json(200, listing)
    if (url.includes('/v1/hub/areas') || url.includes('/v1/hub/media')) return json(200, [])
    return json(404, {
      error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
    })
  })
}

const calls = (needle: string, method: string) =>
  fetchMock.mock.calls.filter(
    ([u, init]) =>
      String(u).endsWith(needle) && ((init as RequestInit)?.method ?? 'GET') === method,
  )

describe('Teacher reviews', () => {
  it('teacher tab hidden on HUB_REVIEWS_OFF', async () => {
    serve(OFF)
    const { unmount } = renderScreen(<HubListing />)
    expect(await screen.findByDisplayValue('Sumi Akter')).toBeInTheDocument()
    await waitFor(() => expect(calls('/v1/hub/reviews', 'GET')).toHaveLength(1))
    expect(screen.queryByRole('link', { name: new RegExp(en('hub_reviews_title')) })).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    unmount()

    // Opened directly while off: no error, nothing drawn but the title.
    renderScreen(<OwnerReviews />)
    await waitFor(() => expect(calls('/v1/hub/reviews', 'GET').length).toBeGreaterThan(1))
    expect(screen.getByRole('heading', { name: en('hub_reviews_title') })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByRole('button', { name: en('auth_retry') })).toBeNull()

    fetchMock.mockReset()
    serve(() => json(200, owner))
    renderScreen(<HubListing />)
    const entry = await screen.findByRole('link', { name: new RegExp(en('hub_reviews_title')) })
    expect(entry).toHaveAttribute('href', '/more/hub/reviews')
  })

  it('shows the server average and a neutral row below the threshold', async () => {
    serve(() => json(200, owner))
    renderScreen(<OwnerReviews />)
    const rows = await screen.findByRole('list', { name: en('hub_reviews_title') })
    const a = within(rows).getByText('Physics · Batch A').closest('li') as HTMLElement
    expect(within(a).getByText(en('hub_reviews_average', '4.3'))).toBeInTheDocument()
    expect(within(a).getByText('3 reviews')).toBeInTheDocument()
    expect(within(a).getByText(en('hub_reviews_distribution', 5, 2))).toBeInTheDocument()
    const b = within(rows).getByText('Chemistry · Batch B').closest('li') as HTMLElement
    expect(within(b).getByText(en('hub_reviews_below_threshold'))).toBeInTheDocument()
    // The server's nulls: no average, no count, no distribution.
    expect(b.textContent).toBe(`Chemistry · Batch B${en('hub_reviews_below_threshold')}`)
    // The card: stars, the server's month, the tenure label, never a name.
    expect(screen.getByRole('img', { name: en('hub_review_stars', 4) })).toBeInTheDocument()
    expect(screen.getByText(en('hub_review_tenure_6_12m'), { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/Nov 2026/)).toBeInTheDocument()
  })

  it('teacher replies and sees awaiting review', async () => {
    serve(
      () => json(200, owner),
      (url, init) =>
        url.endsWith(`/v1/hub/reviews/${REVIEW}/reply`) && init.method === 'PUT'
          ? json(200, card({ my_reply_status: 'pending', my_reply_body: 'Thank you.' }))
          : undefined,
    )
    renderScreen(<OwnerReviews />)
    const box = await screen.findByLabelText(en('hub_reviews_reply_label'))
    expect(screen.getByRole('button', { name: en('hub_reviews_reply_send') })).toBeDisabled()
    await userEvent.type(box, ' Thank you. ')
    expect(screen.getByText('12/1000')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: en('hub_reviews_reply_send') }))

    expect(await screen.findByText(en('hub_review_status_pending'))).toBeInTheDocument()
    const [, init] = calls(`/v1/hub/reviews/${REVIEW}/reply`, 'PUT')[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ body: 'Thank you.' })
    expect(screen.getByRole('button', { name: en('hub_reviews_reply_delete') })).toBeEnabled()
  })

  it('deletes a reply only after the confirmation', async () => {
    serve(
      () =>
        json(200, {
          ...owner,
          reviews: [card({ my_reply_status: 'published', my_reply_body: 'Thank you.' })],
        }),
      (url, init) =>
        url.endsWith(`/v1/hub/reviews/${REVIEW}/reply`) && init.method === 'DELETE'
          ? new Response(null, { status: 204 })
          : undefined,
    )
    renderScreen(<OwnerReviews />)
    await userEvent.click(
      await screen.findByRole('button', { name: en('hub_reviews_reply_delete') }),
    )
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByText(en('hub_reviews_reply_delete_body'))).toBeInTheDocument()
    expect(calls(`/v1/hub/reviews/${REVIEW}/reply`, 'DELETE')).toHaveLength(0)
    await userEvent.click(
      within(sheet).getByRole('button', { name: en('hub_reviews_reply_delete') }),
    )
    expect(await screen.findByText(en('hub_reviews_reply_deleted'))).toBeInTheDocument()
    expect(calls(`/v1/hub/reviews/${REVIEW}/reply`, 'DELETE')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: en('hub_reviews_reply_delete') })).toBeNull()
  })

  it('report link prefills review kind', async () => {
    serve(
      () => json(200, owner),
      (url, init) =>
        url.endsWith('/v1/hub/reports') && init.method === 'POST'
          ? new Response(null, { status: 202 })
          : undefined,
    )
    renderScreen(
      <Routes>
        <Route path="/more/hub/reviews" element={<OwnerReviews />} />
        <Route path="/hub-report" element={<HubReport />} />
      </Routes>,
      '/more/hub/reviews',
    )
    const report = await screen.findByRole('link', { name: en('hub_reviews_report') })
    expect(report).toHaveAttribute('href', `/hub-report?kind=review&id=${REVIEW}`)
    await userEvent.click(report)
    expect(await screen.findByText(en('hub_report_target_review'))).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: /It is fake/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Send report' }))
    await waitFor(() => expect(calls('/v1/hub/reports', 'POST')).toHaveLength(1))
    const [, init] = calls('/v1/hub/reports', 'POST')[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      target_kind: 'review',
      target_id: REVIEW,
      reason: 'fake',
    })
  })
})
