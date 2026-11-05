/**
 * The desktop layouts of the teacher's screens, rendered with a window
 * wide enough for the side rail (`useWide`). Written from the web boards:
 * the main action moves into the page header, lists become tables with
 * the columns a phone has no room for, and Today gains its three figures.
 * Every value shown is the server's, unchanged.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../test/render'
import { Batches } from './Batches'
import { StudentsList } from './people/StudentsList'
import { Today } from './Today'
import { Verify } from './Verify'

const fetchMock = vi.fn()

function wideWindow(wide: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: wide,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

function api(routes: Record<string, unknown>) {
  fetchMock.mockImplementation(async (url: string) => {
    const path = new URL(url, 'http://x').pathname
    if (path in routes) return json(200, routes[path])
    throw new Error(`unexpected ${url}`)
  })
}

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const batch = (id: string, name: string, patch: Record<string, unknown> = {}) => ({
  id,
  name,
  active: true,
  enrollment_count: 4,
  accepted_count: 3,
  default_fee: '1200.00',
  fee_due_day: 10,
  marksheet_visible: false,
  schedule: [{ weekday: 5, start_time: '16:00', end_time: '17:30' }],
  subject_options: [],
  subjects: ['Physics'],
  teacher_display_name: null,
  ...patch,
})

const student = {
  student_id: 's1',
  display_name: 'Tasnim',
  student_phone: '+8801611477203',
  guardian_phone: null,
  student_state: 'accepted',
  guardian_state: 'absent',
  is_removable: false,
  total_outstanding: '4500.00',
  enrollments: [
    {
      enrollment_id: 'e1',
      batch_id: 'b1',
      batch_name: 'Physics A',
      fee_amount: '1200.00',
      status: 'active',
      inactive_from: null,
      outstanding: '4500.00',
      is_removable: false,
    },
  ],
}

describe('Students on a wide window', () => {
  it('is a table with the phone, its state, the batches and what is owed', async () => {
    wideWindow(true)
    api({ '/v1/students': [student], '/v1/batches': [batch('b1', 'Physics A')] })
    renderScreen(<StudentsList />)
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('columnheader', { name: 'Owed' })).toBeInTheDocument()
    expect(within(table).getByRole('link', { name: 'Tasnim' })).toBeInTheDocument()
    expect(within(table).getByText('01611-477203')).toBeInTheDocument()
    expect(within(table).getByText('Accepted')).toBeInTheDocument()
    expect(within(table).getByText('No phone')).toBeInTheDocument()
    expect(within(table).getByText('৳4,500')).toBeInTheDocument()
    // The add action sits in the header, once; there is no floating button.
    expect(screen.getAllByRole('link', { name: 'Add student' })).toHaveLength(1)
    expect(document.querySelector('.fab')).toBeNull()
  })

  it('stays a list on a phone', async () => {
    wideWindow(false)
    api({ '/v1/students': [student], '/v1/batches': [] })
    renderScreen(<StudentsList />)
    expect(await screen.findByText('Tasnim')).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
    expect(document.querySelector('.fab')).not.toBeNull()
  })
})

describe('Batches on a wide window', () => {
  it('puts New batch in the header and adds the empty tile, with no floating button', async () => {
    wideWindow(true)
    api({ '/v1/batches': [batch('b1', 'Physics A')] })
    renderScreen(<Batches />)
    expect(await screen.findByText('Physics A')).toBeInTheDocument()
    expect(screen.getByText('3 of 4 joined')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /New batch/ })).toHaveLength(2)
    expect(document.querySelector('.fab')).toBeNull()
  })
})

describe('Today on a wide window', () => {
  it('shows what is owed, what waits to be verified, and the next class', async () => {
    wideWindow(true)
    api({
      '/v1/me/today': {
        date: '2026-10-17',
        has_batches: true,
        outstanding: {
          total: '48600.00',
          overdue: '31200.00',
          overdue_students: 12,
          batch_count: 7,
        },
        classes: [
          {
            session_id: 'c1',
            batch_id: 'b1',
            batch_name: 'Batch A',
            subject_name: 'Physics',
            start_time: '16:00',
            end_time: '17:30',
            status: 'scheduled',
            is_next: true,
            starts_in_minutes: 35,
            topic: null,
            topic_logged: false,
            topic_version: 0,
            attendance_version: 0,
            exam_id: null,
            exam_title: null,
          },
        ],
        to_verify: [],
        to_verify_count: 4,
      },
    })
    renderScreen(<Today />)
    expect(await screen.findByText('৳48,600')).toBeInTheDocument()
    expect(screen.getByText('Verify payments')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('Next: Physics · Batch A in 35 min')).toBeInTheDocument()
  })
})

const review = (id: string, name: string, patch: Record<string, unknown> = {}) => ({
  submission_id: id,
  batch_name: 'Physics · Batch A',
  children: [
    {
      claim_id: `c-${id}`,
      enrollment_id: `e-${id}`,
      display_name: name,
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
  transaction_id: `TX${id}`,
  from_account: null,
  ...patch,
})

describe('Verify on a wide window', () => {
  function renderQueue() {
    renderScreen(
      <Routes>
        <Route path="/verify" element={<Verify />} />
        <Route path="/verify/:id" element={<p>opened payment</p>} />
      </Routes>,
      '/verify',
    )
  }

  it('lists the queue beside the chosen payment, moved with the arrow keys', async () => {
    wideWindow(true)
    api({
      '/v1/claims/queue': {
        pending: [review('s1', 'Rafsan'), review('s2', 'Sumaiya', { total_amount: '800.00' })],
        decided_recently: [],
      },
    })
    renderQueue()
    const first = await screen.findByRole('button', { name: /Rafsan/ })
    expect(first).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('article', { name: 'Rafsan' })).toBeInTheDocument()
    await userEvent.keyboard('{ArrowDown}')
    expect(screen.getByRole('button', { name: /Sumaiya/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('article', { name: 'Sumaiya' })).toBeInTheDocument()
  })

  it('R opens the rejection of the chosen payment; it never rejects from the list', async () => {
    wideWindow(true)
    api({ '/v1/claims/queue': { pending: [review('s1', 'Rafsan')], decided_recently: [] } })
    renderQueue()
    await screen.findByRole('article', { name: 'Rafsan' })
    await userEvent.keyboard('r')
    expect(await screen.findByText('opened payment')).toBeInTheDocument()
    expect(fetchMock.mock.calls.every(([u]) => !(u as string).includes('/rejection'))).toBe(true)
  })

  it('A approves in one tap only what matches and is new', async () => {
    wideWindow(true)
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/approval')
        ? json(200, { ...review('s1', 'Rafsan'), status: 'approved' })
        : json(200, { pending: [review('s1', 'Rafsan')], decided_recently: [] }),
    )
    renderQueue()
    await screen.findByRole('article', { name: 'Rafsan' })
    await userEvent.keyboard('a')
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => (u as string).endsWith('/s1/approval'))).toBe(true),
    )
  })

  it('A on a short payment opens it instead of approving', async () => {
    wideWindow(true)
    api({
      '/v1/claims/queue': {
        pending: [
          review('s1', 'Rafsan', {
            comparison: 'short',
            difference: '400.00',
            total_amount: '800.00',
          }),
        ],
        decided_recently: [],
      },
    })
    renderQueue()
    await screen.findByRole('article', { name: 'Rafsan' })
    await userEvent.keyboard('a')
    expect(await screen.findByText('opened payment')).toBeInTheDocument()
    expect(fetchMock.mock.calls.every(([u]) => !(u as string).includes('/approval'))).toBe(true)
  })
})
