/**
 * The centre screens' destructive taps against a scripted API: each one
 * asks first, sends nothing until confirmed, and sends nothing when
 * cancelled [UX-9].
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { Payroll } from './Payroll'
import type { SalaryLine } from './payroll'
import { Timetable } from './Timetable'

type Handler = () => Response
const fetchMock = vi.fn()
let routes: Record<string, Handler> = {}

function serve(table: Record<string, unknown>) {
  routes = Object.fromEntries(
    Object.entries(table).map(([k, v]) => [
      k,
      typeof v === 'function' ? (v as Handler) : () => json(200, v),
    ]),
  )
}

const sent = (method: string, part: string) =>
  fetchMock.mock.calls.filter(
    ([u, init]) => ((init as RequestInit)?.method ?? 'GET') === method && String(u).includes(part),
  )

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = new URL(url, 'http://x').pathname
    const method = init?.method ?? 'GET'
    const key = Object.keys(routes).find((k) => {
      const [m, p] = k.split(' ')
      return m === method && (p === path || (p?.endsWith('*') && path.startsWith(p.slice(0, -1))))
    })
    if (!key)
      return json(404, {
        error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
      })
    return routes[key]!()
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const LINE: SalaryLine = {
  line_id: 'l1',
  staff_id: 's1',
  staff_name: 'Sumi',
  centre_name: 'Udoy',
  period: '2026-11',
  basis: 'monthly',
  rate: '8000.00',
  classes_held: 0,
  base: '8000.00',
  owed: '8500.00',
  paid: '0.00',
  remaining: '8500.00',
  status: 'draft',
  adjustments: [
    { adjustment_id: 'a1', kind: 'addition', label: 'Eid bonus', amount: '1000.00' },
    { adjustment_id: 'a2', kind: 'deduction', label: 'Advance', amount: '500.00' },
  ],
  payments: [],
}

describe('Payroll: removing a bonus or deduction', () => {
  function open() {
    serve({
      'GET /v1/centre/payroll/*': [LINE],
      'DELETE /v1/centre/payroll/lines/l1/adjustments/a2': LINE,
    })
    renderScreen(<Payroll />)
  }

  it('names each Remove button by its adjustment', async () => {
    open()
    expect(await screen.findByRole('button', { name: 'Remove Eid bonus' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Advance' })).toBeInTheDocument()
  })

  it('sends nothing on the tap, and removes only once confirmed', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Advance' }))
    const dialog = screen.getByRole('dialog', { name: 'Remove this bonus or deduction?' })
    expect(dialog).toHaveTextContent('“Advance” will no longer be counted in Sumi’s pay')
    expect(sent('DELETE', '/adjustments/')).toHaveLength(0)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(sent('DELETE', '/adjustments/a2')).toHaveLength(1))
    expect(sent('DELETE', '/adjustments/a1')).toHaveLength(0)
  })

  it('sends nothing when cancelled', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Advance' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(sent('DELETE', '/adjustments/')).toHaveLength(0)
  })

  it('asks before throwing away a typed bonus or deduction [UX-10]', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: 'Bonus or deduction' }))
    const sheet = screen.getByRole('dialog', { name: 'Bonus or deduction' })
    await userEvent.type(within(sheet).getByLabelText('Amount'), '300')
    await userEvent.keyboard('{Escape}')
    expect(screen.getByRole('dialog', { name: 'Discard what you typed?' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(within(sheet).getByLabelText('Amount')).toHaveValue('300')
  })
})

describe('Rooms: stopping a room', () => {
  function open() {
    serve({
      'GET /v1/centre/timetable': [],
      'GET /v1/centre/members': [],
      'GET /v1/centre/rooms': [
        { room_id: 'r1', name: 'Room 2', archived: false },
        { room_id: 'r2', name: 'Lab', archived: true },
      ],
      'PATCH /v1/centre/rooms/*': { room_id: 'r1', name: 'Room 2', archived: true },
    })
    renderScreen(<Timetable />)
  }

  async function openRooms() {
    open()
    await userEvent.click(await screen.findByRole('button', { name: 'Rooms' }))
    return screen.findByRole('button', { name: 'Stop using' })
  }

  it('sends nothing on the tap, and stops the room only once confirmed', async () => {
    await userEvent.click(await openRooms())
    const dialog = screen.getByRole('dialog', { name: 'Stop using Room 2?' })
    expect(sent('PATCH', '/rooms/')).toHaveLength(0)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Stop using' }))
    await waitFor(() => expect(sent('PATCH', '/v1/centre/rooms/r1')).toHaveLength(1))
    expect(JSON.parse(sent('PATCH', '/rooms/r1')[0]![1].body as string)).toEqual({
      archived: true,
    })
  })

  it('sends nothing when cancelled, and Escape closes only the question', async () => {
    await userEvent.click(await openRooms())
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Stop using Room 2?' })).toBeNull()
    // The rooms sheet underneath stays open.
    expect(screen.getByRole('dialog', { name: 'Rooms' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Stop using' }))
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'Stop using Room 2?' })).getByRole('button', {
        name: 'Cancel',
      }),
    )
    expect(sent('PATCH', '/rooms/')).toHaveLength(0)
  })

  it('uses a room again without asking, since nothing is lost', async () => {
    open()
    await userEvent.click(await screen.findByRole('button', { name: 'Rooms' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Use again' }))
    await waitFor(() => expect(sent('PATCH', '/v1/centre/rooms/r2')).toHaveLength(1))
  })
})
