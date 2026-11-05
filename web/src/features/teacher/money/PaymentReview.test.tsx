import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { json, renderScreen } from '../../../test/render'
import { PaymentReviewScreen } from './PaymentReview'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const base = {
  submission_id: 's1',
  batch_name: 'Math · Batch B',
  children: [
    {
      claim_id: 'c1',
      enrollment_id: 'e1',
      display_name: 'Tasnim',
      owed: '1200.00',
      period: '2026-10',
      approved_amount: null,
    },
    {
      claim_id: 'c2',
      enrollment_id: 'e2',
      display_name: 'Ayan',
      owed: '800.00',
      period: '2026-10',
      approved_amount: null,
    },
  ],
  comparison: 'short',
  difference: '500.00',
  owed_together: '2000.00',
  total_amount: '1500.00',
  method: { kind: 'mobile', provider: 'bKash', mobile_number: '01711000001' },
  paid_on: '2026-11-04',
  status: 'pending',
  submitted_at: '2026-11-05T03:00:00Z',
  submitted_by: 'guardian',
  submitter_phone: '+8801911000003',
  transaction_id: 'BJK400Q1IL',
  decided_at: null,
  decision_note: null,
}

function show(path: string) {
  return renderScreen(
    <Routes>
      <Route path="/verify/:submissionId" element={<PaymentReviewScreen />} />
    </Routes>,
    path,
  )
}

const posted = (suffix: string) => {
  const call = fetchMock.mock.calls.find(([u]) => (u as string).endsWith(suffix))
  return call ? (JSON.parse(call[1].body as string) as unknown) : undefined
}

it('names the child who carries a shortfall on a payment two children share', async () => {
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/approval')
      ? json(200, { ...base, status: 'approved', decided_at: '2026-11-05T04:00:00Z' })
      : json(200, base),
  )
  show('/verify/s1?act=approve')
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByRole('heading')).toHaveTextContent('Approve ৳1,500 of ৳2,000')
  expect(within(dialog).getByLabelText('Amount you received')).toHaveValue('1500')
  expect(within(dialog).getByText('৳500 short')).toBeInTheDocument()

  const confirm = within(dialog).getByRole('button', { name: 'Approve ৳1,500' })
  await userEvent.click(within(dialog).getByLabelText(/Carry forward/))
  expect(confirm).toBeDisabled() // still needs the child
  expect(within(dialog).getByText('Carry ৳500 onto')).toBeInTheDocument()
  await userEvent.click(within(dialog).getByRole('radio', { name: /^Ayan/ }))
  expect(confirm).toBeEnabled()
  await userEvent.click(confirm)

  await waitFor(() => expect(posted('/v1/payments/s1/approval')).toBeDefined())
  expect(posted('/approval')).toEqual({
    received_amount: '1500.00',
    shortfall_disposition: 'carried',
    carried_by_enrollment_id: 'e2',
    credit_to_enrollment_id: null,
    note: null,
    correcting: false,
  })
  // The decision replaces the controls.
  expect(await screen.findByText(/Approved by you/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Change decision…' })).toBeInTheDocument()
})

it('credits an overpayment to the child named', async () => {
  const over = { ...base, comparison: 'over', total_amount: '2500.00', difference: '500.00' }
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/approval') ? json(200, { ...over, status: 'approved' }) : json(200, over),
  )
  show('/verify/s1')
  await userEvent.click(await screen.findByRole('button', { name: 'Approve' }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('Credit the extra to')).toBeInTheDocument()
  expect(within(dialog).queryByLabelText(/Carry forward/)).toBeNull()
  await userEvent.click(within(dialog).getByRole('radio', { name: /^Tasnim/ }))
  await userEvent.click(within(dialog).getByRole('button', { name: 'Approve ৳2,500' }))
  await waitFor(() => expect(posted('/approval')).toBeDefined())
  expect(posted('/approval')).toEqual({
    received_amount: '2500.00',
    shortfall_disposition: null,
    carried_by_enrollment_id: null,
    credit_to_enrollment_id: 'e1',
    note: null,
    correcting: false,
  })
})

it('changes a decision by rejecting with correcting: true', async () => {
  const approved = {
    ...base,
    children: [base.children[0]],
    comparison: 'matches',
    difference: '0.00',
    owed_together: '1200.00',
    total_amount: '1200.00',
    status: 'approved',
    decided_at: '2026-11-05T04:00:00Z',
    decision_note: 'Thanks',
  }
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/rejection')
      ? json(200, { ...approved, status: 'rejected', decision_note: 'Wrong TrxID' })
      : json(200, approved),
  )
  show('/verify/s1')
  expect(await screen.findByText('“Thanks”')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Change decision…' }))
  await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
  const dialog = await screen.findByRole('dialog')
  await userEvent.type(within(dialog).getByLabelText('Note to them (optional)'), 'Wrong TrxID')
  await userEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))
  await waitFor(() => expect(posted('/rejection')).toBeDefined())
  expect(posted('/rejection')).toEqual({ note: 'Wrong TrxID', correcting: true })
  expect(await screen.findByText(/Rejected by you/)).toBeInTheDocument()
})

it('re-reads a payment someone else decided meanwhile, and says so', async () => {
  const matches = {
    ...base,
    children: [base.children[0]],
    comparison: 'matches',
    difference: '0.00',
    owed_together: '1200.00',
    total_amount: '1200.00',
  }
  let reads = 0
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/approval'))
      return json(409, {
        error: {
          code: 'PAYMENT_ALREADY_DECIDED',
          message_key: 'fees.verification.already_decided',
          retryable: false,
        },
      })
    reads += 1
    return json(
      200,
      reads === 1
        ? matches
        : { ...matches, status: 'rejected', decided_at: '2026-11-05T04:00:00Z' },
    )
  })
  show('/verify/s1')
  await userEvent.click(await screen.findByRole('button', { name: 'Approve' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already recorded a decision')
  expect(await screen.findByText(/Rejected by you/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
})

it('shows the facts and the server’s duplicate warning, and reverses the defaults', async () => {
  const dup = {
    ...base,
    children: [base.children[0]],
    comparison: 'matches',
    owed_together: '1200.00',
    total_amount: '1200.00',
    difference: '0.00',
    duplicate_of: {
      submission_id: 's0',
      display_name: 'Sakib',
      amount: '1500.00',
      status: 'approved',
      decided_at: '2026-10-12T05:00:00Z',
    },
  }
  fetchMock.mockResolvedValue(json(200, dup))
  show('/verify/s1')
  expect(await screen.findByText('01911-000003 (guardian)')).toBeInTheDocument()
  expect(screen.getByText('bKash → 01711-000001')).toBeInTheDocument()
  expect(screen.getByText(/Used before for Sakib \(Paid, ৳1,500, 12 Oct\)/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reject as duplicate' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve anyway' })).toBeInTheDocument()
})
