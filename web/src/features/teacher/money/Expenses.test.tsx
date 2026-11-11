/** Expenses and the monthly summary: the form's body, the mappers, the screens. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { MoneyFormatError } from '../../../core/money'
import { json, renderScreen } from '../../../test/render'
import { Expenses, MoneySummaryScreen } from './Expenses'
import { expenseBody, mapSummary, openExpense, shiftMonth } from './spending'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const summary = {
  month: '2026-11',
  collected: { monthly: '1000.00', exam: '500.00', other: '0.00', total: '1500.00' },
  spent_total: '850.00',
  spent_by_category: [{ category: 'printing', total: '850.00' }],
  net: '650.00',
  net_kind: 'surplus',
  owed_monthly: '1000.00',
  owed_extra: '500.00',
  extra_fees: [
    { extra_fee_id: 'f1', label: 'Half-yearly exam fee', collected: '500.00', spent: '850.00' },
  ],
}

describe('expenseBody', () => {
  const filled = { ...openExpense('k1', '2026-11-05'), what: '  Printing  ', typed: '850' }

  it('sends the trimmed description, the amount as a string and the retry key', () => {
    expect(expenseBody(filled)).toEqual({
      category: 'printing',
      what: 'Printing',
      amount: '850.00',
      spent_on: '2026-11-05',
      payee: null,
      note: null,
      extra_fee_id: null,
      client_mutation_id: 'k1',
    })
  })

  it('sends nothing for a blank description or a zero amount', () => {
    expect(expenseBody({ ...filled, what: ' ' })).toBeNull()
    expect(expenseBody({ ...filled, typed: '0' })).toBeNull()
  })
})

describe('mapSummary', () => {
  it('keeps the server verdict and fails loudly on a number', () => {
    expect(mapSummary(summary as never).netKind).toBe('surplus')
    expect(() => mapSummary({ ...summary, net: 650 } as never)).toThrow(MoneyFormatError)
  })
})

it('moves months across a year boundary', () => {
  expect(shiftMonth('2026-01', -1)).toBe('2025-12')
  expect(shiftMonth('2026-12', 1)).toBe('2027-01')
})

function at(path: string, element: React.ReactElement) {
  return renderScreen(
    <Routes>
      <Route path={path} element={element} />
    </Routes>,
    path,
  )
}

describe('Expenses', () => {
  it('lists the month, crosses out a voided expense and voids another', async () => {
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
      if (init.method === 'POST')
        return json(200, {
          expense_id: 'e1',
          category: 'printing',
          what: 'Printing',
          amount: '850.00',
          spent_on: '2026-11-05',
          voided: true,
        })
      return json(200, {
        month: '2026-11',
        total: '850.00',
        by_category: [{ category: 'printing', total: '850.00' }],
        expenses: [
          {
            expense_id: 'e1',
            category: 'printing',
            what: 'Question paper printing',
            amount: '850.00',
            spent_on: '2026-11-05',
            voided: false,
          },
          {
            expense_id: 'e2',
            category: 'printing',
            what: 'Question paper printing',
            amount: '850.00',
            spent_on: '2026-11-05',
            voided: true,
            void_reason: 'Entered twice',
          },
        ],
      })
    })
    at('/expenses', <Expenses />)
    expect(await screen.findByText('৳850 spent')).toBeInTheDocument()
    expect(screen.getByText(/Entered twice/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Void' }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Void' }).at(-1)!)
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) => (u as string).includes('/v1/expenses/e1/void')),
      ).toBe(true),
    )
  })

  it('asks before a stray Escape throws away a typed expense [UX-10]', async () => {
    fetchMock.mockImplementation(async () =>
      json(200, { month: '2026-11', total: '0.00', by_category: [], expenses: [] }),
    )
    at('/expenses', <Expenses />)
    await userEvent.click((await screen.findAllByRole('button', { name: 'Record an expense' }))[0]!)
    // Untouched: Escape closes at once.
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()

    await userEvent.click(screen.getAllByRole('button', { name: 'Record an expense' })[0]!)
    await userEvent.type(screen.getByLabelText('What it was'), 'Chalk')
    await userEvent.keyboard('{Escape}')
    expect(screen.getByRole('dialog', { name: 'Discard what you typed?' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('What it was')).toHaveValue('Chalk')
  })
})

describe('MoneySummaryScreen', () => {
  it('shows the server verdict and each fee against what was spent for it', async () => {
    fetchMock.mockResolvedValue(json(200, summary))
    at('/money-summary', <MoneySummaryScreen />)
    expect(await screen.findByText('Left over')).toBeInTheDocument()
    expect(screen.getByText('৳650')).toBeInTheDocument()
    expect(screen.getByText('Collected ৳500 · spent ৳850')).toBeInTheDocument()
  })
})
