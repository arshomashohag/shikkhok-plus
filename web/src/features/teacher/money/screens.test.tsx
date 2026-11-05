/** Fee history, payment methods and collections, as screens. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { json, renderScreen } from '../../../test/render'
import { BatchMonthScreen } from './BatchMonth'
import { Collections } from './Collections'
import { EditPaymentMethod, NewPaymentMethod, PaymentMethods } from './PaymentMethods'
import { SeatFees } from './SeatFees'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const calls = (method: string, suffix: string) =>
  fetchMock.mock.calls.filter(
    ([u, init]) =>
      (u as string).split('?')[0]!.endsWith(suffix) && (init as RequestInit).method === method,
  )

function at(path: string, route: string, element: React.ReactElement) {
  return renderScreen(
    <Routes>
      <Route path={route} element={element} />
      <Route path="*" element={<p>elsewhere</p>} />
    </Routes>,
    path,
  )
}

describe('SeatFees', () => {
  it('shows what is outstanding, the strip, and each month with its payment line', async () => {
    fetchMock.mockResolvedValue(
      json(200, {
        cycles: [
          {
            period: '2026-10',
            charged: '1200.00',
            outstanding: '400.00',
            status: 'partly_paid',
            due_date: '2026-10-10',
          },
          {
            period: '2026-11',
            charged: '1200.00',
            outstanding: '1200.00',
            status: 'unpaid',
            due_date: '2026-11-10',
          },
        ],
        total_outstanding: '1600.00',
        month_states: [
          {
            period: '2026-10',
            state: 'partly_paid',
            history_line: {
              amount: '800.00',
              channel: 'bKash',
              paid_on: '2026-10-12',
              status: 'approved_partial',
              covered_names: [],
              decision_note: 'Rest next month',
            },
          },
          { period: '2026-11', state: 'unpaid', history_line: null },
        ],
      }),
    )
    at('/seats/e1/fees?name=Tasnim&batch=Math', '/seats/:enrollmentId/fees', <SeatFees />)
    expect(await screen.findByText('Outstanding: ৳1,600')).toBeInTheDocument()
    expect(screen.getByText('Tasnim · Math')).toBeInTheDocument()
    expect(screen.getByText('৳800 by bKash on 12 Oct · partly approved')).toBeInTheDocument()
    expect(screen.getByText('Note: Rest next month')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Progress' })).toHaveAttribute(
      'href',
      '/seats/e1/progress?name=Tasnim&batch=Math',
    )
    // Newest first.
    const months = screen.getAllByText(/^(October|November)$/).map((n) => n.textContent)
    expect(months).toEqual(['November', 'October'])
    expect(screen.getByLabelText('October: Partly paid')).toBeInTheDocument()
  })

  it('says nothing has been charged yet', async () => {
    fetchMock.mockResolvedValue(
      json(200, { cycles: [], total_outstanding: '0.00', month_states: [] }),
    )
    at('/seats/e1/fees', '/seats/:enrollmentId/fees', <SeatFees />)
    expect(await screen.findByText('No fee has been charged yet.')).toBeInTheDocument()
  })

  const owing = {
    cycles: [
      {
        period: '2026-10',
        charged: '1500.00',
        outstanding: '1500.00',
        status: 'unpaid',
        due_date: '2026-10-10',
      },
    ],
    total_outstanding: '1500.00',
    month_states: [],
  }

  it('records cash received, asking carry or waive only when short', async () => {
    fetchMock.mockImplementation(async (_u: string, init: RequestInit) =>
      init.method === 'POST' ? json(201, {}) : json(200, owing),
    )
    at('/seats/e1/fees?name=Tasnim', '/seats/:enrollmentId/fees', <SeatFees />)
    await userEvent.click(await screen.findByRole('button', { name: 'Record payment' }))

    const sheet = screen.getByRole('dialog')
    expect(within(sheet).getByText('Owed now: ৳1,500')).toBeInTheDocument()
    const amount = within(sheet).getByLabelText('Amount you received')
    expect(amount).toHaveValue('1500')
    expect(within(sheet).getByLabelText('Received as')).toHaveValue('cash')
    expect(within(sheet).queryByText('Carry forward')).toBeNull()

    await userEvent.clear(amount)
    await userEvent.type(amount, '1000')
    const confirm = within(sheet).getByRole('button', { name: 'Record ৳1,000' })
    expect(confirm).toBeDisabled()
    await userEvent.click(within(sheet).getByText('Carry forward'))
    await userEvent.type(
      within(sheet).getByLabelText('Note to the family (optional)'),
      'Rest later',
    )
    await userEvent.click(confirm)

    expect(await screen.findByText('Payment recorded')).toBeInTheDocument()
    const [sent] = calls('POST', '/v1/enrollments/e1/payments')
    expect(JSON.parse(sent![1].body as string)).toEqual({
      amount: '1000.00',
      channel: 'cash',
      reference: null,
      note: 'Rest later',
      shortfall_disposition: 'carried',
      client_mutation_id: expect.any(String),
    })
    // The history is read again, so what shows is what the server recorded.
    expect(calls('GET', '/v1/enrollments/e1/fees').length).toBe(2)
  })

  it('keeps the sheet open with the server’s refusal, and resends under the same key', async () => {
    let posts = 0
    fetchMock.mockImplementation(async (_u: string, init: RequestInit) => {
      if (init.method !== 'POST') return json(200, owing)
      posts += 1
      return posts === 1
        ? json(400, {
            error: {
              code: 'SHORTFALL_DISPOSITION_REQUIRED',
              message_key: 'fees.verification.disposition_required',
              retryable: false,
            },
          })
        : json(201, {})
    })
    at('/seats/e1/fees', '/seats/:enrollmentId/fees', <SeatFees />)
    await userEvent.click(await screen.findByRole('button', { name: 'Record payment' }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Record ৳1,500' }))

    expect(await within(sheet).findByRole('alert')).toHaveTextContent(
      'Choose whether the rest stays owed or is waived.',
    )
    await userEvent.click(within(sheet).getByRole('button', { name: 'Record ৳1,500' }))
    expect(await screen.findByText('Payment recorded')).toBeInTheDocument()
    const [first, second] = calls('POST', '/v1/enrollments/e1/payments').map(
      ([, init]) => JSON.parse((init as RequestInit).body as string) as Record<string, unknown>,
    )
    expect(second!.client_mutation_id).toBe(first!.client_mutation_id)
  })
})

describe('PaymentMethods', () => {
  it('explains the empty state and offers both kinds', async () => {
    fetchMock.mockResolvedValue(json(200, []))
    at('/payment-methods', '/payment-methods', <PaymentMethods />)
    expect(await screen.findByText('No payment methods yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '+ Mobile banking' })).toHaveAttribute(
      'href',
      '/payment-methods/new?kind=mobile',
    )
    expect(screen.getByRole('link', { name: '+ Bank account' })).toHaveAttribute(
      'href',
      '/payment-methods/new?kind=bank',
    )
  })

  it('removes a method after confirming', async () => {
    const method = {
      method_id: 'm1',
      kind: 'mobile',
      provider: 'bKash',
      mobile_number: '01711000001',
      account_name: null,
      account_number: null,
      branch_name: null,
      note: null,
    }
    fetchMock.mockImplementation(async (_u: string, init: RequestInit) =>
      init.method === 'DELETE' ? new Response(null, { status: 204 }) : json(200, [method]),
    )
    at('/payment-methods', '/payment-methods', <PaymentMethods />)
    expect(await screen.findByText('01711-000001')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(calls('DELETE', '/v1/payment-methods/m1')).toHaveLength(1))
  })

  it('adds a mobile method with exactly its fields', async () => {
    fetchMock.mockResolvedValue(json(201, { method_id: 'm2' }))
    at('/payment-methods/new?kind=mobile', '/payment-methods/new', <NewPaymentMethod />)
    const save = await screen.findByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Service'), 'Nag')
    await userEvent.click(screen.getByRole('button', { name: 'Nagad' }))
    await userEvent.type(screen.getByLabelText('Number to send money to'), '01711000001')
    await userEvent.click(save)
    await waitFor(() => expect(calls('POST', '/v1/payment-methods')).toHaveLength(1))
    expect(JSON.parse(calls('POST', '/v1/payment-methods')[0]![1].body as string)).toEqual({
      kind: 'mobile',
      provider: 'Nagad',
      mobile_number: '01711000001',
      note: null,
    })
    expect(await screen.findByText('elsewhere')).toBeInTheDocument()
  })

  it('edits a bank method and shows the server’s refusal in words', async () => {
    const bank = {
      method_id: 'm3',
      kind: 'bank',
      provider: 'DBBL',
      account_name: 'M Rahman',
      account_number: '123',
      branch_name: 'Dhanmondi',
      mobile_number: null,
      note: null,
    }
    fetchMock.mockImplementation(async (_u: string, init: RequestInit) =>
      init.method === 'PATCH'
        ? json(400, {
            error: {
              code: 'VALIDATION',
              message_key: 'fees.method.field_too_long',
              retryable: false,
            },
          })
        : json(200, [bank]),
    )
    at('/payment-methods/m3', '/payment-methods/:methodId', <EditPaymentMethod />)
    expect(await screen.findByDisplayValue('Dhanmondi')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('One of the fields is too long')
    expect(JSON.parse(calls('PATCH', '/v1/payment-methods/m3')[0]![1].body as string)).toEqual({
      kind: 'bank',
      provider: 'DBBL',
      account_number: '123',
      account_name: 'M Rahman',
      branch_name: 'Dhanmondi',
      note: null,
    })
  })
})

describe('Collections', () => {
  const report = {
    months: [
      {
        period: '2026-09',
        charged: '3000.00',
        collected: '3000.00',
        charged_bar: 100,
        collected_bar: 100,
        in_progress: false,
      },
      {
        period: '2026-10',
        charged: '3000.00',
        collected: '1200.00',
        charged_bar: 100,
        collected_bar: 40,
        in_progress: false,
      },
      {
        period: '2026-11',
        charged: '3000.00',
        collected: '0.00',
        charged_bar: 100,
        collected_bar: 0,
        in_progress: true,
      },
    ],
    outstanding: '4800.00',
    owing_students: 4,
  }
  const batches = [
    { id: 'b1', name: 'Physics' },
    { id: 'b2', name: 'Math' },
  ]
  const month = (period: string) => ({
    period,
    charged: '1500.00',
    collected: '600.00',
    counts: { paid: 1, checking: 0, owed: 2 },
    seats: [],
  })

  it('leads with the last finished month, by batch, and one batch failing keeps the rest', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/v1/analytics/collections')) return json(200, report)
      if (url === '/v1/batches') return json(200, batches)
      if (url.startsWith('/v1/batches/b2/fees'))
        return json(503, {
          error: { code: 'TRANSIENT', message_key: 'error.unexpected', retryable: true },
        })
      return json(200, month('2026-10'))
    })
    at('/collections', '/collections', <Collections />)
    expect(await screen.findByText('Collected in October')).toBeInTheDocument()
    expect(screen.getByText('৳4,800')).toBeInTheDocument()
    expect(screen.getByText('October by batch')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Physics/ })).toHaveAttribute(
      'href',
      '/batches/b1/month/2026-10',
    )
    expect(screen.getByText('1 paid · 0 checking · 2 owed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(([u]) =>
        (u as string).includes('/v1/batches/b1/fees?period=2026-10'),
      ),
    ).toBe(true)
  })

  it('asks for only the chosen batches', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/v1/analytics/collections')) return json(200, report)
      if (url === '/v1/batches') return json(200, batches)
      return json(200, month('2026-10'))
    })
    at('/collections', '/collections', <Collections />)
    await userEvent.click(await screen.findByRole('button', { name: 'Math' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u]) => (u as string) === '/v1/analytics/collections?months=6&batch_id=b2',
        ),
      ).toBe(true),
    )
  })
})

describe('BatchMonth', () => {
  it('filters seats by the server’s state and opens a seat’s fees', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url === '/v1/batches'
        ? json(200, [{ id: 'b1', name: 'Physics' }])
        : json(200, {
            period: '2026-10',
            charged: '3600.00',
            collected: '1200.00',
            counts: { paid: 1, checking: 1, owed: 1 },
            seats: [
              { enrollment_id: 'a', display_name: 'Anika', outstanding: '0.00', state: 'paid' },
              {
                enrollment_id: 'b',
                display_name: 'Babul',
                outstanding: '1200.00',
                state: 'checking',
                verifying: '1200.00',
              },
              {
                enrollment_id: 'c',
                display_name: 'Chandni',
                outstanding: '1200.00',
                state: 'unpaid',
                days_overdue: 25,
              },
            ],
          }),
    )
    at('/batches/b1/month/2026-10', '/batches/:batchId/month/:period', <BatchMonthScreen />)
    expect(await screen.findByText('of ৳3,600 collected')).toBeInTheDocument()
    expect(screen.getByText('৳1,200 sent')).toBeInTheDocument()
    expect(screen.getByText('৳1,200 owed · 25 days late')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Owed 1' }))
    expect(screen.queryByText('Anika')).toBeNull()
    expect(screen.getByRole('link', { name: /Chandni/ })).toHaveAttribute(
      'href',
      '/seats/c/fees?name=Chandni&batch=Physics',
    )
  })

  it('offers Record payment on a seat that still owes, and only there', async () => {
    fetchMock.mockImplementation(async (url: string, init: RequestInit) =>
      url === '/v1/batches'
        ? json(200, [{ id: 'b1', name: 'Physics' }])
        : init.method === 'POST'
          ? json(201, {})
          : json(200, {
              period: '2026-10',
              charged: '2400.00',
              collected: '1200.00',
              counts: { paid: 1, checking: 0, owed: 1 },
              seats: [
                { enrollment_id: 'a', display_name: 'Anika', outstanding: '0.00', state: 'paid' },
                {
                  enrollment_id: 'c',
                  display_name: 'Chandni',
                  outstanding: '1200.00',
                  state: 'unpaid',
                  days_overdue: 25,
                },
              ],
            }),
    )
    at('/batches/b1/month/2026-10', '/batches/:batchId/month/:period', <BatchMonthScreen />)
    const record = await screen.findAllByRole('button', { name: 'Record payment' })
    expect(record).toHaveLength(1)
    await userEvent.click(record[0]!)
    const sheet = screen.getByRole('dialog')
    expect(within(sheet).getByText('Chandni')).toBeInTheDocument()
    await userEvent.click(within(sheet).getByRole('button', { name: 'Record ৳1,200' }))
    expect(await screen.findByText('Payment recorded')).toBeInTheDocument()
    expect(calls('POST', '/v1/enrollments/c/payments')).toHaveLength(1)
  })
})
