/**
 * The payroll screen against a fetch that answers like the API: a month
 * switch never shows the old month's lines with live buttons, a failed
 * re-read says so and stops decisions, and one click sends one POST.
 */
import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { currentMonth, shiftMonth } from '../money/spending'
import { Payroll } from './Payroll'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const line = (id: string, name: string, period: string) => ({
  line_id: id,
  staff_id: `s-${id}`,
  staff_name: name,
  centre_name: 'Udoy',
  period,
  basis: 'monthly',
  rate: '8000.00',
  classes_held: 0,
  base: '8000.00',
  owed: '8000.00',
  paid: '0.00',
  remaining: '8000.00',
  status: 'draft',
  adjustments: [],
  payments: [],
})

const now = currentMonth()
const before = shiftMonth(now, -1)
const posts = (suffix: string) =>
  fetchMock.mock.calls.filter(
    ([u, i]) => (i as RequestInit).method === 'POST' && (u as string).endsWith(suffix),
  )

describe('Payroll', () => {
  it('drops this month’s lines while the previous month loads', async () => {
    let answerBefore: (r: Response) => void = () => {}
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith(`/payroll/${now}`))
        return Promise.resolve(json(200, [line('l1', 'Sumi', now)]))
      return new Promise<Response>((r) => {
        answerBefore = r
      })
    })
    renderScreen(<Payroll />)
    expect(await screen.findByText(/Sumi/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Previous month' }))
    // Not Sumi's line for the month just left, under the new heading.
    expect(screen.queryByText(/Sumi/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    await act(async () => answerBefore(json(200, [line('l0', 'Rina', before)])))
    expect(await screen.findByText(/Rina/)).toBeInTheDocument()
  })

  it('says a re-read failed and allows no decision on the unconfirmed lines', async () => {
    fetchMock.mockResolvedValueOnce(json(200, [line('l1', 'Sumi', now)]))
    renderScreen(<Payroll />)
    const approve = await screen.findByRole('button', { name: 'Approve' })
    expect(approve).toBeEnabled()
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    expect(await screen.findByText('Offline.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Bonus or deduction' })).toBeDisabled()
  })

  it('sends one approval for a double click', async () => {
    let answer: (r: Response) => void = () => {}
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      if (init.method === 'POST')
        return new Promise<Response>((r) => {
          answer = r
        })
      return Promise.resolve(json(200, [line('l1', 'Sumi', now)]))
    })
    renderScreen(<Payroll />)
    const approve = await screen.findByRole('button', { name: 'Approve' })
    await userEvent.dblClick(approve)
    expect(posts('/payroll/lines/l1/approve')).toHaveLength(1)
    expect(screen.getByRole('button', { name: "Draw this month's salaries" })).toBeDisabled()
    await act(async () => answer(json(200, { ...line('l1', 'Sumi', now), status: 'approved' })))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: "Draw this month's salaries" })).toBeEnabled(),
    )
  })
})
