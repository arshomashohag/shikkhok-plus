import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { FamilyFees } from './FamilyFees'
import { PayScreen } from './PayScreen'
import { PaymentsScreen } from './PaymentsScreen'
import type { Reader } from '../reader'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const methods = {
  teacher_display_name: 'Mahfuz',
  services: [],
  methods: [
    {
      method_id: 'm-bkash',
      kind: 'mobile',
      provider: 'bKash',
      mobile_number: '01711000001',
      account_name: null,
      account_number: null,
      branch_name: null,
      note: null,
    },
  ],
}

const sent = (status = 'pending') => ({
  submission_id: 's1',
  status,
  total_amount: '1500.00',
  paid_on: '2026-11-04',
  claims: [
    {
      claim_id: 'c1',
      enrollment_id: 'y-a',
      display_name: 'আয়ান',
      period: '2026-11',
      claimed_amount: '1500.00',
    },
  ],
})

function route(reader: Reader, path: string, element: React.ReactElement, at: string) {
  const base = reader === 'me' ? '/my/:seat' : '/child/:seat'
  return renderScreen(
    <Routes>
      <Route path={`${base}/${path}`} element={element} />
      <Route path="*" element={<div>elsewhere</div>} />
    </Routes>,
    at,
  )
}

const posted = () => {
  const call = fetchMock.mock.calls.find(
    ([u, init]) =>
      (u as string).endsWith('/v1/payments') && (init as RequestInit).method === 'POST',
  )
  return call ? JSON.parse((call[1] as RequestInit).body as string) : null
}

describe('PayScreen', () => {
  it('a student pays by bKash: owed amount filled in, exact body, sent page', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/v1/me/enrollments'))
        return json(200, [
          { enrollment_id: 'e1', batch_name: 'Physics A', teacher_display_name: 'Mahfuz' },
        ])
      if (url.includes('/v1/me/enrollments/e1/payment-methods')) return json(200, methods)
      if (url.includes('/v1/payments/owed'))
        return json(200, {
          owed_together: '1200.00',
          children: [{ enrollment_id: 'e1', display_name: 'তাসনিম', owed: '1200.00' }],
        })
      if (url.endsWith('/v1/payments')) return json(201, { ...sent(), total_amount: '1200.00' })
      return json(404, {})
    })
    route('me', 'pay', <PayScreen reader="me" />, '/my/e1/pay')

    await userEvent.click(await screen.findByRole('button', { name: /bKash/ }))
    const amount = screen.getByLabelText('Amount')
    await waitFor(() => expect(amount).toHaveValue('1200'))
    expect(screen.getByText(/Owed for তাসনিম: ৳1,200/)).toBeInTheDocument()

    const send = screen.getByRole('button', { name: 'Send for checking' })
    expect(send).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Transaction ID'), 'BJK40')
    expect(screen.getByText(/This looks too short/)).toBeInTheDocument()
    expect(send).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Transaction ID'), '0Q1IL')
    await userEvent.click(send)

    expect(await screen.findByText('Payment sent')).toBeInTheDocument()
    const body = posted()
    expect(body).toEqual({
      enrollment_ids: ['e1'],
      payment_method_id: 'm-bkash',
      cash: false,
      amount: '1200.00',
      paid_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      transaction_id: 'BJK400Q1IL',
      from_account: null,
      note: null,
      client_mutation_id: expect.any(String),
    })
    expect(screen.getByText(/against TrxID BJK400Q1IL/)).toBeInTheDocument()
  })

  it('a guardian pays for two children in one batch together, in cash, and a retry reuses its key', async () => {
    let attempts = 0
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/v1/guardian/home'))
        return json(200, {
          children: [
            {
              key: 'k1',
              display_name: 'তাসনিম জাহান',
              batch_count: 1,
              batches: [
                { enrollment_id: 't-a', batch_name: 'Physics A', teacher_display_name: 'Mahfuz' },
              ],
            },
            {
              key: 'k2',
              display_name: 'আয়ান রহমান',
              batch_count: 1,
              batches: [
                { enrollment_id: 'y-a', batch_name: 'Physics A', teacher_display_name: 'Mahfuz' },
              ],
            },
          ],
        })
      if (url.includes('/v1/children/t-a/payment-methods')) return json(200, methods)
      if (url.includes('/v1/payments/owed')) {
        const both = url.includes('t-a') && url.includes('y-a')
        return json(200, {
          owed_together: both ? '2400.00' : '1200.00',
          children: both
            ? [
                { enrollment_id: 't-a', display_name: 'তাসনিম জাহান', owed: '1200.00' },
                { enrollment_id: 'y-a', display_name: 'আয়ান রহমান', owed: '1200.00' },
              ]
            : [{ enrollment_id: 'y-a', display_name: 'আয়ান রহমান', owed: '1200.00' }],
        })
      }
      if (url.endsWith('/v1/payments')) {
        attempts += 1
        if (attempts === 1) throw new TypeError('Failed to fetch')
        return json(201, sent())
      }
      return json(404, {})
    })
    route('child', 'pay', <PayScreen reader="child" />, '/child/y-a/pay')

    await userEvent.click(await screen.findByRole('button', { name: /Cash in hand/ }))
    // Opened for আয়ান: only his seat is chosen; the server's owed fills the amount.
    await waitFor(() => expect(screen.getByLabelText('Amount')).toHaveValue('1200'))
    const tasnim = screen.getByRole('button', { name: 'তাসনিম জাহান' })
    expect(tasnim).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(tasnim)
    // A changed choice re-reads what is owed; the untouched amount follows it.
    await waitFor(() => expect(screen.getByLabelText('Amount')).toHaveValue('2400'))

    await userEvent.click(screen.getByRole('button', { name: 'Send for checking' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't send. No connection.")
    await userEvent.click(screen.getByRole('button', { name: 'Send for checking' }))
    expect(await screen.findByText('Payment sent')).toBeInTheDocument()

    const bodies = fetchMock.mock.calls
      .filter(([u]) => (u as string).endsWith('/v1/payments'))
      .map(([, init]) => JSON.parse((init as RequestInit).body as string))
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toEqual(bodies[1])
    expect(bodies[0]).toMatchObject({
      enrollment_ids: ['t-a', 'y-a'],
      payment_method_id: null,
      cash: true,
      amount: '2400.00',
      transaction_id: null,
      from_account: null,
    })
  })

  it('says so when there is nothing to pay for', async () => {
    fetchMock.mockImplementation(async () => json(200, []))
    route('me', 'pay', <PayScreen reader="me" />, '/my/e1/pay')
    expect(await screen.findByText('Nothing to pay for yet')).toBeInTheDocument()
  })

  it('a resend the teacher already approved says so', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/v1/me/enrollments'))
        return json(200, [
          { enrollment_id: 'e1', batch_name: 'Physics A', teacher_display_name: 'Mahfuz' },
        ])
      if (url.includes('payment-methods')) return json(200, methods)
      if (url.includes('/v1/payments/owed'))
        return json(200, {
          owed_together: '0.00',
          children: [{ enrollment_id: 'e1', display_name: 'তাসনিম', owed: '0.00' }],
        })
      return json(201, sent('approved'))
    })
    route('me', 'pay', <PayScreen reader="me" />, '/my/e1/pay')
    await userEvent.click(await screen.findByRole('button', { name: /bKash/ }))
    expect(await screen.findByText(/Nothing is owed for তাসনিম right now/)).toBeInTheDocument()
    expect(screen.getByLabelText('Amount')).toHaveValue('')
    await userEvent.type(screen.getByLabelText('Amount'), '500')
    await userEvent.type(screen.getByLabelText('Transaction ID'), 'ABCDEF1234')
    await userEvent.click(screen.getByRole('button', { name: 'Send for checking' }))
    expect(await screen.findByText('Already recorded')).toBeInTheDocument()
  })
})

describe('PaymentsScreen (G2)', () => {
  it('shows a child’s payments by month with the child’s name in the title', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/payments'))
        return json(200, {
          display_name: 'তাসনিম জাহান',
          year: 2026,
          paid_this_year: '26400.00',
          months: [
            {
              period: '2026-10',
              lines: [
                {
                  enrollment_id: 't-a',
                  batch_name: 'রসায়ন',
                  amount: '1200.00',
                  state: 'verifying',
                  due_date: '2026-10-10',
                  sent_on: '2026-10-15',
                  decided_on: null,
                  channel: 'Nagad',
                },
                {
                  enrollment_id: 't-b',
                  batch_name: 'উচ্চতর গণিত',
                  amount: '1500.00',
                  state: 'due',
                  due_date: '2026-10-20',
                  sent_on: null,
                  decided_on: null,
                  channel: null,
                },
              ],
            },
          ],
        })
      return json(200, {
        payable: [
          {
            enrollment_id: 't-b',
            batch_name: 'উচ্চতর গণিত',
            period: '2026-10',
            amount_due: '1500.00',
            total_due: '1500.00',
            later_periods: 0,
            days_late: null,
            due_date: '2026-10-20',
          },
        ],
      })
    })
    route('child', 'payments', <PaymentsScreen reader="child" />, '/child/t-a/payments')
    expect(await screen.findByRole('heading', { name: "তাসনিম's payments" })).toBeInTheDocument()
    expect(screen.getByText('Paid in 2026: ৳26,400')).toBeInTheDocument()
    expect(screen.getByText('৳1,500', { selector: '.hero-amount' })).toBeInTheDocument()
    expect(screen.getByText(/You sent it 15 Oct · Nagad/)).toBeInTheDocument()
    expect(screen.getByText('Due by 20 Oct')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Send money' })).toHaveAttribute(
      'href',
      '/child/t-a/pay',
    )
  })

  it('asks not to pay again while payments cannot load', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    route('child', 'payments', <PaymentsScreen reader="child" />, '/child/t-a/payments')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Please don't pay again until this loads",
    )
  })

  it('sends a student, who has no payments list, to their fee history', async () => {
    renderScreen(
      <Routes>
        <Route path="/my/:seat/payments" element={<PaymentsScreen reader="me" />} />
        <Route path="/my/:seat/fees" element={<div>fees here</div>} />
      </Routes>,
      '/my/e1/payments',
    )
    expect(await screen.findByText('fees here')).toBeInTheDocument()
  })
})

describe('FamilyFees', () => {
  const fees = {
    total_outstanding: '3600.00',
    cycles: [
      {
        period: '2026-10',
        charged: '1200.00',
        outstanding: '1200.00',
        due_date: '2026-10-10',
        status: 'unpaid',
      },
      {
        period: '2026-09',
        charged: '1200.00',
        outstanding: '0.00',
        due_date: '2026-09-10',
        status: 'paid',
      },
    ],
    month_states: [
      {
        period: '2026-09',
        state: 'paid',
        history_line: {
          amount: '1200.00',
          channel: 'bKash',
          paid_on: '2026-09-08',
          status: 'approved_full',
          covered_names: [],
          decision_note: null,
        },
      },
      { period: '2026-10', state: 'unpaid', history_line: null },
    ],
  }

  it.each([
    ['me', '/my/e1/fees', '/v1/me/fees?enrollment_id=e1'],
    ['child', '/child/e1/fees', '/v1/children/e1/fees'],
  ] as const)('reads %s’s fees from the right endpoint', async (reader, at, endpoint) => {
    fetchMock.mockResolvedValue(json(200, fees))
    route(reader, 'fees', <FamilyFees reader={reader} />, at)
    expect(await screen.findByText('Outstanding: ৳3,600')).toBeInTheDocument()
    expect(fetchMock.mock.calls[0]![0]).toBe(endpoint)
    expect(screen.getByText(/৳1,200 by bKash on 8 Sept? · approved/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Send money' })).toHaveAttribute(
      'href',
      reader === 'me' ? '/my/e1/pay' : '/child/e1/pay',
    )
  })
})
