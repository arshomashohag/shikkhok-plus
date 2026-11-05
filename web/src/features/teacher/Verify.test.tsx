import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../test/render'
import { Verify } from './Verify'

const review = {
  submission_id: 's1',
  batch_name: 'Physics · Batch A',
  children: [
    {
      claim_id: 'c1',
      enrollment_id: 'e1',
      display_name: 'Rafsan',
      owed: '1200.00',
      period: '2026-10',
      approved_amount: null,
    },
  ],
  comparison: 'matches',
  difference: '0.00',
  owed_together: '1200.00',
  total_amount: '1200.00',
  method: { kind: 'mobile', provider: 'bKash' },
  paid_on: '2026-10-16',
  status: 'pending',
  submitted_at: new Date().toISOString(),
  transaction_id: 'BJK400Q1IL',
  from_account: null,
}

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const href = (el: HTMLElement) => el.getAttribute('href')

it('approves as reported with the server’s own amount string, in one tap', async () => {
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/approval')
      ? json(200, { ...review, status: 'approved' })
      : json(200, { pending: [review], decided_recently: [] }),
  )
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(within(card).getByText('৳1,200')).toBeInTheDocument()
  await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([u]) => (u as string).endsWith('/v1/payments/s1/approval')),
    ).toBe(true),
  )
  const call = fetchMock.mock.calls.find(([u]) => (u as string).endsWith('/approval'))!
  expect(JSON.parse(call[1].body as string)).toEqual({
    received_amount: '1200.00',
    note: null,
    correcting: false,
  })
})

it('hides the decision buttons when a refresh failed: never approve from stale data', async () => {
  fetchMock.mockResolvedValueOnce(json(200, { pending: [review], decided_recently: [] }))
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(within(card).getByRole('button', { name: 'Approve' })).toBeInTheDocument()

  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
  await act(async () => {
    window.dispatchEvent(new Event('online'))
  })
  await waitFor(() => expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull())
  expect(within(card).queryByRole('link', { name: 'Reject' })).toBeNull()
  // The card itself stays: the teacher can still read what was loaded.
  expect(within(card).getByText('BJK400Q1IL')).toBeInTheDocument()
})

it('sends Reject and Partial to the payment, opening the right control', async () => {
  fetchMock.mockResolvedValue(json(200, { pending: [review], decided_recently: [] }))
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(href(within(card).getByRole('link', { name: 'Reject' }))).toBe('/verify/s1?act=reject')
  expect(href(within(card).getByRole('link', { name: 'Partial' }))).toBe('/verify/s1?act=approve')
})

it('never one-tap approves a short payment', async () => {
  const short = {
    ...review,
    comparison: 'short',
    total_amount: '800.00',
    difference: '400.00',
    owed_together: '1200.00',
  }
  fetchMock.mockResolvedValue(json(200, { pending: [short], decided_recently: [] }))
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull()
  expect(href(within(card).getByRole('link', { name: 'Approve ৳800…' }))).toBe(
    '/verify/s1?act=approve',
  )
})

it('sends an overpayment to review', async () => {
  const over = { ...review, comparison: 'over', total_amount: '1500.00', difference: '300.00' }
  fetchMock.mockResolvedValue(json(200, { pending: [over], decided_recently: [] }))
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull()
  expect(href(within(card).getByRole('link', { name: 'Review' }))).toBe('/verify/s1')
})

it('turns a reused transaction ID into a review, with the warning in the server’s order', async () => {
  const dup = {
    ...review,
    duplicate_of: {
      submission_id: 's0',
      display_name: 'Sakib',
      amount: '1500.00',
      status: 'approved',
      decided_at: null,
    },
  }
  fetchMock.mockResolvedValue(json(200, { pending: [dup], decided_recently: [] }))
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(within(card).getByText('This ID was already used.')).toBeInTheDocument()
  // "Used before for {name} ({decision}, {amount})", as Android fills it.
  expect(within(card).getByText(/Used before for Sakib \(Paid, ৳1,500\)/)).toBeInTheDocument()
  expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull()
  expect(href(within(card).getByRole('link', { name: 'Approve anyway' }))).toBe('/verify/s1')
  expect(href(within(card).getByRole('link', { name: 'Reject as duplicate' }))).toBe(
    '/verify/s1?act=reject',
  )
})

it('links a payment decided today back to its detail', async () => {
  fetchMock.mockResolvedValue(
    json(200, {
      pending: [],
      decided_recently: [
        {
          submission_id: 's9',
          display_name: 'Tasnim',
          batch_name: 'Math',
          amount: '800.00',
          status: 'approved',
          decided_at: new Date().toISOString(),
        },
      ],
    }),
  )
  renderScreen(<Verify />)
  expect(href(await screen.findByRole('link', { name: /Tasnim/ }))).toBe('/verify/s9')
  expect(screen.getByText('All caught up')).toBeInTheDocument()
})
