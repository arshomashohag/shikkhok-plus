/**
 * The students & notices screens, against a fetch that answers like the
 * API. What matters most: writes send what the server expects, refusals
 * are worded by the server's key, and no action is offered on a stale read.
 */
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { Dues } from '../Dues'
import { mapBatch } from '../mappers'
import { AddStudent } from './AddStudent'
import { NoticesTab } from './NoticesTab'
import { StudentsTab } from './StudentsTab'

type Handler = (method: string, url: string, body: unknown) => Response | undefined

const fetchMock = vi.fn()
function api(handler: Handler) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
    const body = init.body ? (JSON.parse(init.body as string) as unknown) : undefined
    const answer = handler(init.method ?? 'GET', url, body)
    if (!answer) throw new Error(`unexpected ${init.method} ${url}`)
    return answer
  })
}
const calls = (method: string, suffix: string) =>
  fetchMock.mock.calls.filter(
    ([u, i]) => (i as RequestInit).method === method && (u as string).endsWith(suffix),
  )
const bodyOf = (call: unknown[]) => JSON.parse((call[1] as RequestInit).body as string) as unknown

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const batch = {
  id: 'b1',
  name: 'Physics · Batch A',
  active: true,
  enrollment_count: 2,
  accepted_count: 1,
  default_fee: '1200.00',
  fee_due_day: 10,
  marksheet_visible: false,
  schedule: [],
  subject_options: [],
  subjects: ['Physics'],
  teacher_display_name: null,
}

const seat = (id: string, name: string, patch: Record<string, unknown> = {}) => ({
  enrollment_id: id,
  display_name: name,
  fee_amount: null,
  guardian_phone: '+8801911000003',
  guardian_state: 'accepted',
  inactive_from: null,
  is_removable: true,
  status: 'active',
  student_state: 'accepted',
  ...patch,
})

const noFees = {
  charged: '0.00',
  collected: '0.00',
  counts: { checking: 0, owed: 0, paid: 0 },
  period: '2026-11',
  seats: [],
}

const error = (status: number, code: string, key: string) =>
  json(status, { error: { code, message_key: key, retryable: false } })

describe('Add student (T8)', () => {
  function renderAdd() {
    renderScreen(
      <Routes>
        <Route path="/batches/:batchId/students/new" element={<AddStudent />} />
        <Route path="/batches/:batchId" element={<p>batch screen</p>} />
      </Routes>,
      '/batches/b1/students/new',
    )
  }

  it('keeps the batch fee by default and sends the normalised numbers', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches') && m === 'GET') return json(200, [batch])
      if (u.endsWith('/roster')) return json(200, [seat('e1', 'Tasnim')])
      if (u.endsWith('/enrollments') && m === 'POST') return json(201, seat('e2', 'Rafsan'))
    })
    renderAdd()
    await userEvent.type(await screen.findByLabelText("Student's phone"), '01711-845220')
    await userEvent.type(screen.getByLabelText('Student name'), 'Rafsan')
    await userEvent.type(screen.getByLabelText('Guardian phone (optional)'), '+8801913554108')
    expect(screen.getByRole('switch')).toBeChecked()
    expect(screen.getByText('Batch fee · ৳1,200')).toBeInTheDocument()
    expect(screen.queryByLabelText('Fee for this student (optional)')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    await screen.findByText('batch screen')
    expect(bodyOf(calls('POST', '/enrollments')[0]!)).toEqual({
      display_name: 'Rafsan',
      student_phone: '01711845220',
      guardian_phone: '01913554108',
      fee_amount: null,
    })
  })

  it('asks for a different fee only when the toggle is off, as a money string', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches') && m === 'GET') return json(200, [batch])
      if (u.endsWith('/roster')) return json(200, [])
      if (u.endsWith('/enrollments') && m === 'POST') return json(201, seat('e2', 'Rafsan'))
    })
    renderAdd()
    await userEvent.type(await screen.findByLabelText("Student's phone"), '01711845220')
    await userEvent.type(screen.getByLabelText('Student name'), 'Rafsan')
    await userEvent.click(screen.getByRole('switch'))
    const fee = screen.getByLabelText('Fee for this student (optional)')
    await userEvent.type(fee, '1,000.5')
    await userEvent.click(screen.getByRole('button', { name: 'Save & add next' }))
    // Stays open, says how many were added, and clears for the next one.
    expect(await screen.findByText(/1 added so far/)).toBeInTheDocument()
    expect(screen.getByLabelText("Student's phone")).toHaveValue('')
    expect(bodyOf(calls('POST', '/enrollments')[0]!)).toMatchObject({ fee_amount: '1000.50' })
  })

  it('holds Save until the phone is a mobile number, and says how many digits it has', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches') && m === 'GET') return json(200, [batch])
      if (u.endsWith('/roster')) return json(200, [seat('e1', 'Jannatul Ferdous')])
    })
    renderAdd()
    await userEvent.type(await screen.findByLabelText("Student's phone"), '0181920773')
    await userEvent.type(screen.getByLabelText('Student name'), 'jannatul ferdous')
    expect(screen.getByText(/This one has 10/)).toBeInTheDocument()
    expect(screen.getByText(/Jannatul Ferdous is already in this batch/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add student' })).toBeDisabled()
  })

  it('shows the server’s refusal in its own words', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches') && m === 'GET') return json(200, [batch])
      if (u.endsWith('/roster')) return json(200, [])
      if (u.endsWith('/enrollments'))
        return error(409, 'CONFLICT', 'enrollment.student_already_in_batch')
    })
    renderAdd()
    await userEvent.type(await screen.findByLabelText("Student's phone"), '01711845220')
    await userEvent.type(screen.getByLabelText('Student name'), 'Rafsan')
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This student is already in this batch.',
    )
  })
})

describe('Students tab', () => {
  const props = { batchId: 'b1', batch: mapBatch(batch), reloadBatch: () => undefined }

  it('says how many accepted, and offers removal only where the server allows it', async () => {
    api((_m, u) => {
      if (u.endsWith('/roster'))
        return json(200, [seat('e1', 'Tasnim'), seat('e2', 'Rafsan', { is_removable: false })])
      if (u.endsWith('/fees')) return json(200, noFees)
    })
    renderScreen(<StudentsTab {...props} />)
    expect(await screen.findByText('1 of 2 accepted.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Actions for Rafsan' }))
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Fee history' })).toHaveAttribute(
      'href',
      '/seats/e2/fees',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Actions for Tasnim' }))
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
  })

  it('offers marking inactive when a removal is refused because someone accepted', async () => {
    api((m, u) => {
      if (u.endsWith('/roster')) return json(200, [seat('e1', 'Tasnim')])
      if (u.endsWith('/fees')) return json(200, noFees)
      if (m === 'DELETE') return error(409, 'ENROLLMENT_CLAIMED', 'enrollment.remove.claimed')
      if (m === 'PATCH') return json(200, {})
    })
    renderScreen(<StudentsTab {...props} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Actions for Tasnim' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Remove' }),
    )
    const refused = await screen.findByRole('dialog', { name: "This place can't be removed" })
    await userEvent.click(within(refused).getByRole('button', { name: 'Mark inactive' }))
    await waitFor(() => expect(calls('PATCH', '/e1/inactive-from')).toHaveLength(1))
    expect(bodyOf(calls('PATCH', '/e1/inactive-from')[0]!)).toEqual({
      inactive_from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    })
  })

  it('does not offer Mark inactive again once the server recorded a date', async () => {
    // A seat nobody accepted stays `dormant` even when marked inactive.
    api((_m, u) => {
      if (u.endsWith('/roster'))
        return json(200, [
          seat('e1', 'Tasnim', {
            status: 'dormant',
            student_state: 'pending',
            inactive_from: '2026-11-05',
          }),
        ])
      if (u.endsWith('/fees')) return json(200, noFees)
    })
    renderScreen(<StudentsTab {...props} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Actions for Tasnim' }))
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark inactive' })).toBeNull()
  })

  it('still lists names when fee status failed, and hides the chips', async () => {
    api((_m, u) => {
      if (u.endsWith('/roster')) return json(200, [seat('e1', 'Tasnim')])
      if (u.endsWith('/fees'))
        return json(503, {
          error: { code: 'TRANSIENT', message_key: 'error.unexpected', retryable: true },
        })
    })
    renderScreen(<StudentsTab {...props} />)
    expect(await screen.findByText('Tasnim')).toBeInTheDocument()
    expect(screen.getByText("Fee status couldn't load")).toBeInTheDocument()
  })

  it('empty: offers the first student', async () => {
    api((_m, u) => (u.endsWith('/roster') ? json(200, []) : json(200, noFees)))
    renderScreen(<StudentsTab {...props} />)
    expect(await screen.findByRole('link', { name: 'Add first student' })).toHaveAttribute(
      'href',
      '/batches/b1/students/new',
    )
  })
})

describe('Notices tab', () => {
  const props = { batchId: 'b1', batch: null, reloadBatch: () => undefined }

  it('posts, edits and takes down a notice', async () => {
    let notices = [
      {
        announcement_id: 'n1',
        body: 'Bring the worksheet',
        created_at: new Date().toISOString(),
        edited: false,
      },
    ]
    api((m, u, body) => {
      if (u.endsWith('/announcements') && m === 'GET') return json(200, notices)
      if (u.endsWith('/announcements') && m === 'POST') {
        notices = [
          {
            announcement_id: 'n2',
            body: (body as { body: string }).body,
            created_at: new Date().toISOString(),
            edited: false,
          },
          ...notices,
        ]
        return json(201, notices[0])
      }
      if (m === 'PUT') return json(200, { ...notices[0], edited: true })
      if (m === 'DELETE') return new Response(null, { status: 204 })
    })
    renderScreen(<NoticesTab {...props} />)
    expect(await screen.findByText('Bring the worksheet')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Write a notice'), '  Test on Saturday  ')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(calls('POST', '/announcements')).toHaveLength(1))
    expect(bodyOf(calls('POST', '/announcements')[0]!)).toEqual({ body: 'Test on Saturday' })
    expect(await screen.findByText('Test on Saturday')).toBeInTheDocument()
    expect(screen.getByLabelText('Write a notice')).toHaveValue('')

    const first = screen.getAllByRole('article')[1]!
    await userEvent.click(within(first).getByRole('button', { name: 'Remove' }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Remove' }),
    )
    await waitFor(() => expect(calls('DELETE', '/v1/announcements/n1')).toHaveLength(1))
  })

  it('empty: says what a notice is for', async () => {
    api(() => json(200, []))
    renderScreen(<NoticesTab {...props} />)
    expect(await screen.findByText('No notices yet')).toBeInTheDocument()
  })
})

describe('Dues reminders', () => {
  const dues = {
    summary: {
      count: 2,
      remindable: 1,
      total: '9600.00',
      late_total: '6000.00',
      groups: [{ bucket: 'over_30', count: 2, share: 100, total: '9600.00' }],
    },
    rows: [
      {
        enrollment_id: 'e1',
        display_name: 'A',
        batch_id: 'b1',
        batch_name: 'B',
        bucket: 'over_30',
        days_late: 68,
        outstanding: '6000.00',
        remindable: true,
        last_reminded_at: null,
      },
      {
        enrollment_id: 'e2',
        display_name: 'C',
        batch_id: 'b1',
        batch_name: 'B',
        bucket: 'over_30',
        days_late: 40,
        outstanding: '3600.00',
        remindable: false,
        last_reminded_at: new Date().toISOString(),
      },
    ],
  }

  it('reminds the seats the server marked, whatever the filter shows', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/me/dues')) return json(200, dues)
      if (u.endsWith('/v1/reminders') && m === 'POST') return json(200, { sent: 1, skipped: 0 })
    })
    renderScreen(<Dues />)
    await userEvent.click(await screen.findByRole('button', { name: 'Not reminded' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remind 1 late students' }))
    const dialog = await screen.findByRole('dialog', { name: 'Remind 1 students?' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Send reminders' }))
    expect(await screen.findByText('Reminded 1 students')).toBeInTheDocument()
    expect(bodyOf(calls('POST', '/v1/reminders')[0]!)).toEqual({ enrollment_ids: ['e1'] })
  })

  it('holds the reminder back offline', async () => {
    api((_m, u) => (u.endsWith('/v1/me/dues') ? json(200, dues) : undefined))
    renderScreen(<Dues />)
    const button = await screen.findByRole('button', { name: 'Remind 1 late students' })
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    fetchMock.mockRejectedValue(new TypeError('offline'))
    await act(async () => {
      window.dispatchEvent(new Event('offline'))
    })
    await waitFor(() => expect(button).toBeDisabled())
    expect(screen.getByText('Reminders need a connection.')).toBeInTheDocument()
  })

  it('offers no reminder when the server marks nobody remindable', async () => {
    api(() => json(200, { ...dues, summary: { ...dues.summary, remindable: 0 } }))
    renderScreen(<Dues />)
    await screen.findByText('Owed to you')
    expect(screen.queryByRole('button', { name: /Remind/ })).toBeNull()
  })
})
