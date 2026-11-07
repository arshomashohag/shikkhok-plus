/**
 * A teacher's students, apart from any batch [0018], against a fetch that
 * answers like the API. Written after the screens, from the approved
 * decisions: one student in many batches, batches optional on add [D3],
 * a refused number shown in the server's words [D2], removal only when
 * the server says so [D4], and filtering done by the server.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { studentsQuery } from './api'
import { mapStudent, otherBatches } from './mappers'
import { NewStudent } from './NewStudent'
import { PickStudents } from './PickStudents'
import { StudentDetail } from './StudentDetail'
import { StudentsList } from './StudentsList'

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
const calls = (method: string, part: string) =>
  fetchMock.mock.calls.filter(
    ([u, i]) => (i as RequestInit).method === method && (u as string).includes(part),
  )
const bodyOf = (call: unknown[]) => JSON.parse((call[1] as RequestInit).body as string) as unknown

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const batch = (id: string, name: string, fee: string | null = '1200.00') => ({
  id,
  name,
  active: true,
  enrollment_count: 0,
  accepted_count: 0,
  default_fee: fee,
  fee_due_day: 10,
  marksheet_visible: false,
  schedule: [],
  subject_options: [],
  subjects: ['Physics'],
  teacher_display_name: null,
})
const batches = [batch('b1', 'Physics A'), batch('b2', 'Chemistry B', '1000.00')]

const seat = (batchId: string, batchName: string, patch: Record<string, unknown> = {}) => ({
  enrollment_id: `e-${batchId}`,
  batch_id: batchId,
  batch_name: batchName,
  fee_amount: '1200.00',
  status: 'active',
  inactive_from: null,
  outstanding: '0.00',
  is_removable: false,
  ...patch,
})

const student = (
  id: string,
  name: string,
  seats: ReturnType<typeof seat>[],
  patch: Record<string, unknown> = {},
) => ({
  student_id: id,
  display_name: name,
  student_phone: '+8801812345678',
  guardian_phone: null,
  student_state: 'pending',
  guardian_state: 'absent',
  enrollments: seats,
  total_outstanding: '0.00',
  is_removable: false,
  ...patch,
})

describe('the server does the filtering', () => {
  it('builds each filter as a query, never filtering on the client', () => {
    expect(studentsQuery({ kind: 'all' }, '')).toBe('/v1/students')
    expect(studentsQuery({ kind: 'unassigned' }, '')).toBe('/v1/students?unassigned=true')
    expect(studentsQuery({ kind: 'in-batch', batchId: 'b1' }, ' raf ')).toBe(
      '/v1/students?batch_id=b1&q=raf',
    )
    expect(studentsQuery({ kind: 'not-in-batch', batchId: 'b1' }, '')).toBe(
      '/v1/students?exclude_batch_id=b1',
    )
  })

  it('refuses an amount sent as a JSON number', () => {
    expect(() => mapStudent({ ...student('s1', 'R', []), total_outstanding: 0 } as never)).toThrow()
  })

  it('offers only the batches the student is not in', () => {
    const s = mapStudent(student('s1', 'R', [seat('b1', 'Physics A')]))
    expect(otherBatches(s, [{ id: 'b1' }, { id: 'b2' }])).toEqual([{ id: 'b2' }])
  })
})

describe('Students tab', () => {
  it('lists a student once with every batch, and asks the server per chip', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.includes('/v1/students')) {
        return u.includes('unassigned=true')
          ? json(200, [student('s2', 'Mehedi', [])])
          : json(200, [
              student('s1', 'Rafiq', [seat('b2', 'Chemistry B'), seat('b1', 'Physics A')]),
            ])
      }
      return m === 'GET' ? undefined : undefined
    })
    renderScreen(<StudentsList />)
    expect(await screen.findByText('Chemistry B · Physics A')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Not in a batch' }))
    expect(await screen.findByText('Mehedi')).toBeInTheDocument()
    expect(calls('GET', 'unassigned=true')).toHaveLength(1)
  })

  it('searches once per pause in typing, not once per keystroke', async () => {
    api((_m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.includes('/v1/students')) return json(200, [student('s1', 'Rafiq', [])])
    })
    renderScreen(<StudentsList />)
    await screen.findByText('Rafiq')
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search name or phone' }), 'Rafiq')
    await waitFor(() => expect(calls('GET', 'q=Rafiq')).toHaveLength(1))
    // Only the settled text went to the server: no request for "R", "Ra"…
    expect(calls('GET', 'q=')).toHaveLength(1)
  })
})

describe('Add student', () => {
  function renderNew(path = '/students/new') {
    renderScreen(
      <Routes>
        <Route path="/students/new" element={<NewStudent />} />
      </Routes>,
      path,
    )
  }

  it('saves with no batch at all [D3]', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.endsWith('/v1/students') && m === 'GET') return json(200, [])
      if (u.endsWith('/v1/students') && m === 'POST') return json(201, student('s9', 'Mehedi', []))
    })
    renderNew()
    await userEvent.type(await screen.findByLabelText('Student name'), 'Mehedi')
    expect(screen.getByText(/Saved without a batch/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    await waitFor(() => expect(calls('POST', '/v1/students')).toHaveLength(1))
    expect(bodyOf(calls('POST', '/v1/students')[0]!)).toEqual({
      display_name: 'Mehedi',
      student_phone: null,
      guardian_phone: null,
      enrollments: [],
    })
  })

  it('sends each chosen batch with its own fee or null to inherit', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.endsWith('/v1/students') && m === 'GET') return json(200, [])
      if (u.endsWith('/v1/students') && m === 'POST') return json(201, student('s9', 'Rafiq', []))
    })
    renderNew('/students/new?batch=b1')
    await userEvent.type(await screen.findByLabelText('Student name'), 'Rafiq')
    // Opened from Physics A's roster, so Physics A starts chosen.
    expect(screen.getByLabelText('Fee in Physics A (optional)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Add to batches/ }))
    await userEvent.click(screen.getByRole('option', { name: /Chemistry B/ }))
    await userEvent.type(screen.getByLabelText('Fee in Chemistry B (optional)'), '900')
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    await waitFor(() => expect(calls('POST', '/v1/students')).toHaveLength(1))
    expect(bodyOf(calls('POST', '/v1/students')[0]!)).toMatchObject({
      enrollments: [
        { batch_id: 'b1', fee_amount: null },
        { batch_id: 'b2', fee_amount: '900.00' },
      ],
    })
  })

  it('shows a refused number in the server’s words [D2]', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.endsWith('/v1/students') && m === 'GET') return json(200, [])
      if (u.endsWith('/v1/students') && m === 'POST')
        return json(409, {
          error: {
            code: 'STUDENT_PHONE_TAKEN',
            message_key: 'student.phone_taken',
            retryable: false,
          },
        })
    })
    renderNew()
    await userEvent.type(await screen.findByLabelText('Student name'), 'Rafiq')
    await userEvent.type(screen.getByLabelText("Student's phone"), '01812345678')
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Another of your students already has this number.',
    )
  })
})

describe('Student detail', () => {
  function renderDetail(body: unknown) {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.endsWith('/v1/students/s1') && m === 'GET') return json(200, body)
      if (u.endsWith('/v1/students/s1/enrollments') && m === 'POST') return json(201, body)
    })
    renderScreen(
      <Routes>
        <Route path="/students/:studentId" element={<StudentDetail />} />
      </Routes>,
      '/students/s1',
    )
  }

  it('offers removal only when the server says it would succeed [D4]', async () => {
    renderDetail(student('s1', 'Rafiq', [seat('b1', 'Physics A')]))
    expect(await screen.findByText(/must leave every batch and owe nothing/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove student' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Leave batch' })).toBeInTheDocument()
  })

  it('adds the student to a batch they are not in', async () => {
    renderDetail(student('s1', 'Rafiq', [seat('b1', 'Physics A')]))
    const select = await screen.findByLabelText('Add to another batch')
    expect(screen.queryByRole('option', { name: /Physics A/ })).toBeNull()
    await userEvent.selectOptions(select, 'b2')
    await waitFor(() => expect(calls('POST', '/enrollments')).toHaveLength(1))
    expect(bodyOf(calls('POST', '/enrollments')[0]!)).toEqual({ batch_id: 'b2' })
  })
})

describe('Roster picker', () => {
  it('asks for students NOT in the batch and seats the chosen ones', async () => {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.includes('exclude_batch_id=b1'))
        return json(200, [
          student('s1', 'Tanvir', [seat('b2', 'Chemistry B')]),
          student('s2', 'Sadia', []),
        ])
      if (u.endsWith('/v1/batches/b1/students') && m === 'POST') return json(201, { added: 1 })
    })
    renderScreen(
      <Routes>
        <Route path="/batches/:batchId/students/pick" element={<PickStudents />} />
        <Route path="/batches/:batchId" element={<p>batch screen</p>} />
      </Routes>,
      '/batches/b1/students/pick',
    )
    await userEvent.click(await screen.findByRole('checkbox', { name: /Sadia/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Add 1' }))
    await screen.findByText('batch screen')
    expect(bodyOf(calls('POST', '/v1/batches/b1/students')[0]!)).toEqual({ student_ids: ['s2'] })
    expect(screen.queryByText('Tanvir')).toBeNull()
  })

  it('reads the batch list once while the teacher searches', async () => {
    api((_m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.includes('exclude_batch_id=b1')) return json(200, [student('s2', 'Sadia', [])])
    })
    renderScreen(
      <Routes>
        <Route path="/batches/:batchId/students/pick" element={<PickStudents />} />
      </Routes>,
      '/batches/b1/students/pick',
    )
    await screen.findByText('Sadia')
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search name or phone' }), 'Sad')
    await waitFor(() => expect(calls('GET', 'q=Sad')).toHaveLength(1))
    expect(calls('GET', 'q=')).toHaveLength(1)
    expect(
      fetchMock.mock.calls.filter(([u]) => (u as string).endsWith('/v1/batches')),
    ).toHaveLength(1)
  })
})
