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
  from_account: '01711234567',
}

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

it('approves as reported with the server’s own amount string', async () => {
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
  // The card itself stays: the teacher can still read what was loaded.
  expect(within(card).getByText('BJK400Q1IL')).toBeInTheDocument()
})

it('asks carry-or-waive only when less was received, and sends the choice', async () => {
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/approval')
      ? json(200, { ...review, status: 'approved' })
      : json(200, { pending: [review], decided_recently: [] }),
  )
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  await userEvent.click(within(card).getByRole('button', { name: 'Partial' }))
  const dialog = await screen.findByRole('dialog')
  const amount = within(dialog).getByLabelText('Amount you received')
  expect(amount).toHaveValue('1200')
  await userEvent.clear(amount)
  await userEvent.type(amount, '800')
  const confirm = within(dialog).getByRole('button', { name: 'Approve ৳800' })
  expect(confirm).toBeDisabled()
  await userEvent.click(within(dialog).getByLabelText(/Carry forward/))
  expect(confirm).toBeEnabled()
  await userEvent.click(confirm)
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([u]) => (u as string).endsWith('/approval'))).toBe(true),
  )
  const call = fetchMock.mock.calls.find(([u]) => (u as string).endsWith('/approval'))!
  expect(JSON.parse(call[1].body as string)).toMatchObject({
    received_amount: '800.00',
    shortfall_disposition: 'carried',
  })
})

it('never one-tap approves a short payment: the sheet opens with the reported amount', async () => {
  const short = {
    ...review,
    comparison: 'short',
    total_amount: '800.00',
    difference: '400.00',
    owed_together: '1200.00',
  }
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/approval')
      ? json(200, { ...short, status: 'approved' })
      : json(200, { pending: [short], decided_recently: [] }),
  )
  renderScreen(<Verify />)
  const card = await screen.findByRole('article', { name: 'Rafsan' })
  expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull()
  await userEvent.click(within(card).getByRole('button', { name: 'Approve ৳800…' }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByLabelText('Amount you received')).toHaveValue('800')
  // Short of what is owed together, so carry-or-waive must be chosen first.
  const confirm = within(dialog).getByRole('button', { name: 'Approve ৳800' })
  expect(confirm).toBeDisabled()
  await userEvent.click(within(dialog).getByLabelText(/Waive/))
  await userEvent.click(confirm)
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([u]) => (u as string).endsWith('/approval'))).toBe(true),
  )
  const call = fetchMock.mock.calls.find(([u]) => (u as string).endsWith('/approval'))!
  expect(JSON.parse(call[1].body as string)).toMatchObject({
    received_amount: '800.00',
    shortfall_disposition: 'waived',
  })
})

it('sends a duplicate transaction ID through the sheet, not one tap', async () => {
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
  expect(within(card).queryByRole('button', { name: 'Approve' })).toBeNull()
  expect(within(card).getByRole('button', { name: 'Approve anyway' })).toBeInTheDocument()
  expect(within(card).getByRole('button', { name: 'Reject as duplicate' })).toBeInTheDocument()
})
