/** Exam and other fees, as screens. */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { json, renderScreen } from '../../../test/render'
import { BatchExtraFees, ExtraFeeDetail, RaiseExtraFee } from './ExtraFees'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const fee = {
  extra_fee_id: 'fee-1',
  purpose: 'exam',
  label: 'Half-yearly exam fee',
  exam_title: null,
  amount: '500.00',
  due_on: '2026-11-15',
  created_at: '2026-11-06T04:00:00Z',
  student_count: 2,
  paid_count: 1,
  waived_count: 0,
  owing_count: 1,
  charged_total: '1000.00',
  collected_total: '500.00',
  owed_total: '500.00',
}

function at(path: string, route: string, element: React.ReactElement) {
  return renderScreen(
    <Routes>
      <Route path={route} element={element} />
      <Route path="*" element={<p>elsewhere</p>} />
    </Routes>,
    path,
  )
}

describe('BatchExtraFees', () => {
  it('lists each fee with the server totals', async () => {
    fetchMock.mockResolvedValue(json(200, { fees: [fee], chargeable_students: [] }))
    at('/batches/b1/fees', '/batches/:batchId/fees', <BatchExtraFees />)
    expect(await screen.findByText('Half-yearly exam fee')).toBeInTheDocument()
    expect(screen.getByText('৳500 of ৳1,000 collected')).toBeInTheDocument()
  })

  it('says what fees are for when there are none', async () => {
    fetchMock.mockResolvedValue(json(200, { fees: [], chargeable_students: [] }))
    at('/batches/b1/fees', '/batches/:batchId/fees', <BatchExtraFees />)
    expect(await screen.findByText(/No exam or other fees yet/)).toBeInTheDocument()
  })
})

describe('RaiseExtraFee', () => {
  it('offers the students the server names and sends a waiver as zero', async () => {
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (url.endsWith('/exams')) return json(200, [])
      if (init.method === 'POST') return json(201, fee)
      return json(200, {
        fees: [],
        chargeable_students: [
          { enrollment_id: 'e1', display_name: 'Tania' },
          { enrollment_id: 'e2', display_name: 'Rafi' },
        ],
      })
    })
    at('/batches/b1/fees/new', '/batches/:batchId/fees/new', <RaiseExtraFee />)
    await userEvent.type(await screen.findByLabelText('Name families see'), 'Half-yearly exam fee')
    await userEvent.type(screen.getByLabelText('Amount per student'), '500')
    await userEvent.selectOptions(screen.getByLabelText('Rafi'), 'waive')
    await userEvent.click(screen.getByRole('button', { name: 'Raise for 2 students' }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit).method === 'POST')
      expect(call).toBeDefined()
      expect(JSON.parse((call![1] as RequestInit).body as string)).toMatchObject({
        purpose: 'exam',
        label: 'Half-yearly exam fee',
        amount: '500.00',
        seat_amounts: [{ enrollment_id: 'e2', amount: '0.00' }],
      })
    })
  })
})

describe('ExtraFeeDetail', () => {
  it('shows each student with the status the server sent', async () => {
    fetchMock.mockResolvedValue(
      json(200, {
        ...fee,
        students: [
          {
            enrollment_id: 'e1',
            display_name: 'Tania',
            charged: '500.00',
            paid: '500.00',
            owed: '0.00',
            status: 'paid',
          },
          {
            enrollment_id: 'e2',
            display_name: 'Rafi',
            charged: '500.00',
            paid: '0.00',
            owed: '500.00',
            status: 'unpaid',
          },
        ],
      }),
    )
    at('/extra-fees/fee-1', '/extra-fees/:feeId', <ExtraFeeDetail />)
    expect(await screen.findByText('Tania')).toBeInTheDocument()
    expect(screen.getByText('৳0 paid · ৳500 owed')).toBeInTheDocument()
    // Only a student who still owes can have cash recorded.
    expect(screen.getAllByRole('button', { name: 'Record payment' })).toHaveLength(1)
  })
})
