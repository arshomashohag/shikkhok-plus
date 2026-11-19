/**
 * The guardian's reviews against a fetch that answers like the API. What
 * is asserted is that the screens render the server's decisions and none
 * of their own: the entry exists only while the reviewable list has a row,
 * `can_write` alone decides whether the form is editable, a not-yet member
 * reads the server's reason and day, a delete is sent only after the
 * confirmation, and a refusal reads in the server's words with what was
 * typed kept.
 */
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearTokens } from '../../../api/tokens'
import { translate } from '../../../i18n/i18n'
import { json } from '../../../test/render'
import { mockSignedIn, renderRoutes, type Call } from '../../../test/signedIn'
import { GuardianHome } from '../../guardian/GuardianHome'
import { MyReviews } from './MyReviews'
import { ReviewEditor } from './ReviewEditor'
import {
  REVIEW_STATUS_KEY,
  standingNote,
  statusText,
  type MyReviewState,
  type ReviewStatus,
} from './mappers'

const BATCH = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)

afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
  localStorage.clear()
})

const ROUTES = [
  { path: '/children', element: <GuardianHome /> },
  { path: '/reviews', element: <MyReviews /> },
  { path: '/reviews/:batchId', element: <ReviewEditor /> },
]

const row = (over: Record<string, unknown> = {}) => ({
  batch_id: BATCH,
  batch_title: 'Physics · Batch A',
  owner_public_name: 'Sumi Akter',
  state: 'eligible',
  eligible_from: null,
  ...over,
})

const review = (over: Record<string, unknown> = {}) => ({
  rating: 4,
  body: 'Clear and patient.',
  status: 'pending',
  rejection_code: null,
  tenure: 'lt_6m',
  published_month: null,
  reply_body: null,
  ...over,
})

const mine = (over: Record<string, unknown> = {}) => ({
  standing: 'eligible',
  waiting_on: null,
  eligible_from: null,
  can_write: true,
  edit_until: null,
  review: null,
  ...over,
})

const MY_REVIEW = `/v1/hub/batches/${BATCH}/my-review`
const sent = (calls: Call[], method: string) =>
  calls.filter((c) => c.method === method && c.url.endsWith(MY_REVIEW))

describe('Guardian reviews', () => {
  it('entry hidden when reviewable empty or reviews off', async () => {
    const home = { children: [{ key: 'k1', display_name: 'Tasnim', batch_count: 0 }] }
    // Reviews off: the server lists nothing the guardian has not already reviewed.
    let answered = 0
    const listed = mockSignedIn((_method, url) => {
      if (url.endsWith('/v1/guardian/home')) return json(200, home)
      if (!url.endsWith('/v1/hub/reviewable')) return undefined
      answered += 1
      return json(200, [])
    }, 'guardian')
    const { unmount } = renderRoutes(ROUTES, '/children')
    expect(await screen.findByText('Tasnim')).toBeInTheDocument()
    await waitFor(() => expect(answered).toBeGreaterThan(0))
    // Let the empty answer land before asserting nothing was drawn for it.
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)))
    expect(listed.some((c) => c.url.endsWith('/v1/hub/reviewable'))).toBe(true)
    expect(document.body.textContent).not.toContain(en('hub_reviews_title'))
    expect(screen.queryByRole('link', { name: new RegExp(en('hub_reviews_title')) })).toBeNull()
    unmount()

    mockSignedIn(
      (_method, url) =>
        url.endsWith('/v1/guardian/home')
          ? json(200, home)
          : url.endsWith('/v1/hub/reviewable')
            ? json(200, [row()])
            : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, '/children')
    const entry = await screen.findByRole('link', { name: new RegExp(en('hub_reviews_title')) })
    await userEvent.click(entry)
    expect(await screen.findByText('Physics · Batch A')).toBeInTheDocument()
    expect(screen.getByText(en('hub_reviews_state_eligible'))).toBeInTheDocument()
  })

  it('editor submits and shows awaiting review', async () => {
    const calls = mockSignedIn((method, url, body) => {
      if (!url.endsWith(MY_REVIEW)) return undefined
      if (method === 'GET') return json(200, mine())
      const b = body as { rating: number; body: string | null }
      return json(
        200,
        mine({
          edit_until: '2026-12-19',
          review: review({ rating: b.rating, body: b.body }),
        }),
      )
    }, 'guardian')
    renderRoutes(ROUTES, `/reviews/${BATCH}`)

    expect(await screen.findByText(en('hub_review_privacy_note'))).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: en('hub_review_submit') })
    expect(submit).toBeDisabled()
    await userEvent.click(screen.getByRole('radio', { name: en('hub_review_star_5') }))
    await userEvent.type(screen.getByLabelText(en('hub_review_body_label')), '  Very good.  ')
    expect(screen.getByText('14/1000')).toBeInTheDocument()
    await userEvent.click(submit)

    expect(await screen.findByText(en('hub_review_status_pending'))).toBeInTheDocument()
    expect(sent(calls, 'PUT').map((c) => c.body)).toEqual([{ rating: 5, body: 'Very good.' }])
    expect(screen.getByText(en('hub_review_edit_until', '19 Dec 2026'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: en('hub_review_save') })).toBeInTheDocument()
  })

  it('not yet eligible shows server reason and date', async () => {
    const calls = mockSignedIn(
      (method, url) =>
        url.endsWith(MY_REVIEW) && method === 'GET'
          ? json(
              200,
              mine({
                standing: 'not_yet',
                waiting_on: 'tenure',
                eligible_from: '2026-12-19',
                can_write: false,
              }),
            )
          : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, `/reviews/${BATCH}`)
    expect(await screen.findByText(en('hub_review_not_yet_eligible'))).toBeInTheDocument()
    expect(screen.getByText(en('hub_review_eligible_from', '19 Dec 2026'))).toBeInTheDocument()
    // can_write is false: nothing to fill in, nothing to send.
    expect(screen.queryByRole('radio')).toBeNull()
    expect(screen.queryByRole('button', { name: en('hub_review_submit') })).toBeNull()
    expect(sent(calls, 'PUT')).toEqual([])

    // A write refused with the same standing reads the server's key and its date.
    const note = standingNote(
      mine({ standing: 'not_yet', waiting_on: 'attendance', can_write: false }) as MyReviewState,
    )
    expect(note).toEqual({ messageKey: 'hub.review.needs_attendance', eligibleFrom: null })
    expect(standingNote(mine({ standing: 'closed', can_write: false }) as MyReviewState)).toEqual({
      messageKey: 'hub.review.window_closed',
      eligibleFrom: null,
    })
    expect(standingNote(mine() as MyReviewState)).toBeNull()
  })

  it('says a review cannot be written when nothing else would show', async () => {
    // Switched off with no review, and an author whose review is gone:
    // no review, no standing note and no form, so the screen says so.
    for (const state of [
      mine({ can_write: false }),
      mine({ standing: 'author_only', can_write: false }),
    ]) {
      mockSignedIn(
        (method, url) =>
          url.endsWith(MY_REVIEW) && method === 'GET' ? json(200, state) : undefined,
        'guardian',
      )
      const { unmount } = renderRoutes(ROUTES, `/reviews/${BATCH}`)
      expect(await screen.findByText(en('hub_review_unavailable'))).toBeInTheDocument()
      expect(screen.queryByRole('radio')).toBeNull()
      unmount()
    }

    // A waiting member reads their reason instead.
    mockSignedIn(
      (method, url) =>
        url.endsWith(MY_REVIEW) && method === 'GET'
          ? json(200, mine({ standing: 'not_yet', waiting_on: 'attendance', can_write: false }))
          : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, `/reviews/${BATCH}`)
    expect(await screen.findByText(en('hub_review_needs_attendance'))).toBeInTheDocument()
    expect(screen.queryByText(en('hub_review_unavailable'))).toBeNull()
  })

  it('edit closed shows read-only with delete', async () => {
    mockSignedIn(
      (method, url) =>
        url.endsWith(MY_REVIEW) && method === 'GET'
          ? json(
              200,
              mine({
                can_write: false,
                review: review({
                  status: 'rejected',
                  rejection_code: 'personal_info',
                  reply_body: null,
                }),
              }),
            )
          : undefined,
      'guardian',
    )
    renderRoutes(ROUTES, `/reviews/${BATCH}`)
    expect(await screen.findByText('Clear and patient.')).toBeInTheDocument()
    expect(
      screen.getByText(
        en('hub_review_status_not_published', en('hub_review_reason_personal_info')),
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('img', { name: en('hub_review_stars', 4) })).toBeInTheDocument()
    expect(screen.queryByRole('radio')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: en('hub_review_save') })).toBeNull()
    expect(screen.getByRole('button', { name: en('hub_review_delete') })).toBeEnabled()
  })

  it('delete confirms then calls DELETE', async () => {
    let gone = false
    const calls = mockSignedIn((method, url) => {
      if (!url.endsWith(MY_REVIEW)) return undefined
      if (method === 'DELETE') {
        gone = true
        return new Response(null, { status: 204 })
      }
      return json(200, mine({ edit_until: '2026-12-19', review: gone ? null : review() }))
    }, 'guardian')
    renderRoutes(ROUTES, `/reviews/${BATCH}`)

    await userEvent.click(await screen.findByRole('button', { name: en('hub_review_delete') }))
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByText(en('hub_review_delete_body'))).toBeInTheDocument()
    // Cancel sends nothing.
    await userEvent.click(within(sheet).getByRole('button', { name: en('action_cancel') }))
    expect(sent(calls, 'DELETE')).toEqual([])

    await userEvent.click(screen.getByRole('button', { name: en('hub_review_delete') }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: en('hub_review_delete'),
      }),
    )
    expect(await screen.findByText(en('hub_review_deleted'))).toBeInTheDocument()
    expect(sent(calls, 'DELETE')).toHaveLength(1)
    expect(screen.queryByText('Clear and patient.')).toBeNull()
  })

  it('contact error shows server message', async () => {
    mockSignedIn((method, url) => {
      if (!url.endsWith(MY_REVIEW)) return undefined
      if (method === 'GET') return json(200, mine())
      return json(400, {
        error: {
          code: 'REVIEW_CONTAINS_CONTACT',
          message_key: 'hub.review.contains_contact',
          retryable: false,
          details: { field: 'body' },
        },
      })
    }, 'guardian')
    renderRoutes(ROUTES, `/reviews/${BATCH}`)

    await userEvent.click(await screen.findByRole('radio', { name: en('hub_review_star_3') }))
    await userEvent.type(screen.getByLabelText(en('hub_review_body_label')), 'Call 01712345678')
    await userEvent.click(screen.getByRole('button', { name: en('hub_review_submit') }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(en('hub_review_contains_contact'))
    // Not retryable: the words have to change first, and they are kept.
    expect(within(alert).queryByRole('button')).toBeNull()
    expect(screen.getByLabelText(en('hub_review_body_label'))).toHaveValue('Call 01712345678')
    expect(screen.getByRole('radio', { name: en('hub_review_star_3') })).toBeChecked()
  })

  it('words every status from the server and never a raw code', () => {
    const t = (key: string, ...args: (string | number)[]) => en(key, ...args)
    const statuses: ReviewStatus[] = [
      'pending',
      'approved',
      'published',
      'rejected',
      'removed',
      'held',
    ]
    expect(Object.keys(REVIEW_STATUS_KEY).sort()).toEqual([...statuses].sort())
    expect(statusText('approved', null, t)).toBe('Approved, appears Friday')
    expect(statusText('removed', 'off_topic', t)).toBe('Not published: it is not about the class')
    // A code this client does not know reads as the general reason.
    expect(statusText('rejected', 'brand_new', t)).toBe('Not published: it breaks the review rules')
    for (const s of statuses) expect(statusText(s, 'abusive', t)).not.toMatch(/hub_review/)
  })
})
