/**
 * A teacher's students, apart from any batch [0018], against a fetch that
 * answers like the API. Written after the screens, from the approved
 * decisions: one student in many batches, batches optional on add [D3],
 * a refused number shown in the server's words [D2], removal only when
 * the server says so [D4], and filtering done by the server.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate, translateMessage } from '../../../i18n/i18n'
import { json, renderScreen } from '../../../test/render'
import { studentsQuery } from './api'
import {
  editProblems,
  guardianCellLine,
  guardianContactLine,
  mapStudent,
  otherBatches,
  studentContactLine,
  studentEdit,
  type Student,
  type StudentFields,
} from './mappers'
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
  student_email: null as string | null,
  guardian_email: null as string | null,
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
      client_mutation_id: expect.any(String),
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

  describe('removing a place asks first, as the Students tab does [UX-8]', () => {
    function renderRemovable() {
      api((m, u) => {
        if (u.endsWith('/v1/batches')) return json(200, batches)
        if (u.endsWith('/v1/students/s1') && m === 'GET')
          return json(
            200,
            student('s1', 'Rafiq', [
              seat('b1', 'Physics A', { is_removable: true }),
              seat('b2', 'Chemistry B', { is_removable: true }),
            ]),
          )
        if (u.endsWith('/v1/enrollments/e-b1') && m === 'DELETE')
          return new Response(null, { status: 204 })
      })
      renderScreen(
        <Routes>
          <Route path="/students/:studentId" element={<StudentDetail />} />
        </Routes>,
        '/students/s1',
      )
    }

    it('names the batch on each row’s Remove button', async () => {
      renderRemovable()
      expect(
        await screen.findByRole('button', { name: 'Remove from batch: Chemistry B' }),
      ).toBeInTheDocument()
      // The visible words stay part of the name, for voice control.
      expect(
        screen.getByRole('button', { name: 'Remove from batch: Physics A' }),
      ).toHaveTextContent('Remove from batch')
    })

    it('sends nothing on the tap, and removes only once confirmed', async () => {
      renderRemovable()
      await userEvent.click(
        await screen.findByRole('button', { name: 'Remove from batch: Physics A' }),
      )
      const dialog = screen.getByRole('dialog', { name: 'Remove this place?' })
      // The screen lists two batches; the confirmation names the one meant.
      expect(dialog).toHaveTextContent('Rafiq will be removed from “Physics A”')
      // A destructive confirmation opens on the safe choice.
      expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
      expect(calls('DELETE', '/enrollments/')).toHaveLength(0)
      await userEvent.click(within(dialog).getByRole('button', { name: 'Remove' }))
      await waitFor(() => expect(calls('DELETE', '/v1/enrollments/e-b1')).toHaveLength(1))
    })

    it('sends nothing when cancelled, by button or by Escape', async () => {
      renderRemovable()
      await userEvent.click(
        await screen.findByRole('button', { name: 'Remove from batch: Physics A' }),
      )
      await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(screen.queryByRole('dialog')).toBeNull()
      await userEvent.click(screen.getByRole('button', { name: 'Remove from batch: Physics A' }))
      await userEvent.keyboard('{Escape}')
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(calls('DELETE', '/enrollments/')).toHaveLength(0)
    })
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

// ------------------------------------------- emails [FR6.1–6.3] W7, Q4

const en = (key: string, ...args: string[]) => translate('en', key, ...args)

describe('studentEdit — the Edit sheet’s patch [review R-04]', () => {
  const original: StudentFields = {
    name: 'Rafiq',
    studentPhone: '01812-345678',
    guardianPhone: '',
    studentEmail: 'rafiq@example.com',
    guardianEmail: 'mother@example.com',
  }

  it('an unchanged form gives null: nothing is sent', () => {
    expect(studentEdit(original, { ...original })).toBeNull()
    // Re-typed the same, in another shape, is still unchanged.
    expect(
      studentEdit(original, {
        ...original,
        studentPhone: '+880 1812 345678',
        studentEmail: ' Rafiq@Example.com ',
      }),
    ).toBeNull()
  })

  it('an emptied email is null in the body, which clears it', () => {
    expect(studentEdit(original, { ...original, guardianEmail: '  ' })).toEqual({
      guardian_email: null,
    })
  })

  it('an emptied phone is null in the body too', () => {
    expect(studentEdit(original, { ...original, studentPhone: '' })).toEqual({
      student_phone: null,
    })
  })

  it('a changed value is sent, and only it', () => {
    expect(
      studentEdit(original, {
        ...original,
        name: ' Rafiq Hasan ',
        guardianPhone: '01911-000003',
        studentEmail: 'New@Example.com',
      }),
    ).toEqual({
      display_name: 'Rafiq Hasan',
      guardian_phone: '01911000003',
      student_email: 'new@example.com',
    })
  })

  it('editProblems names malformed contacts only; blank is never malformed', () => {
    expect(editProblems({ ...original, guardianPhone: '', guardianEmail: '' })).toEqual({})
    expect(editProblems({ ...original, studentPhone: '123', guardianEmail: 'nope' })).toEqual({
      studentPhone: true,
      guardianEmail: true,
    })
  })
})

describe('contact lines — phone, then email [W7 step 7]', () => {
  const s = (patch: Partial<Student>) => ({
    studentPhone: null,
    studentEmail: null,
    guardianPhone: null,
    guardianEmail: null,
    ...patch,
  })

  it('the student line prefers the phone, then the email, else null', () => {
    expect(studentContactLine(s({ studentPhone: '+8801812345678', studentEmail: 'a@b.cd' }))).toBe(
      '01812-345678',
    )
    expect(studentContactLine(s({ studentEmail: 'a@b.cd' }))).toBe('a@b.cd')
    expect(studentContactLine(s({}))).toBeNull()
  })

  it('the guardian line shows both when both are recorded, phone first', () => {
    expect(
      guardianContactLine(s({ guardianPhone: '+8801911000003', guardianEmail: 'm@example.com' })),
    ).toBe('01911-000003 · m@example.com')
    expect(guardianContactLine(s({ guardianEmail: 'm@example.com' }))).toBe('m@example.com')
    expect(guardianCellLine(s({ guardianPhone: '+8801911000003', guardianEmail: 'm@x.cd' }))).toBe(
      '01911-000003',
    )
  })

  it('a response carrying a field this client does not know still decodes [NFR6.1]', () => {
    const mapped = mapStudent({
      ...student('s1', 'Rafiq', [], { student_email: 'rafiq@example.com' }),
      nickname: 'R',
    } as never)
    expect(mapped.studentEmail).toBe('rafiq@example.com')
  })
})

describe('New student — emails', () => {
  function renderNew() {
    renderScreen(
      <Routes>
        <Route path="/students/new" element={<NewStudent />} />
      </Routes>,
      '/students/new',
    )
  }

  function serveNew(post: () => Response) {
    api((m, u) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.endsWith('/v1/students') && m === 'GET') return json(200, [])
      if (u.endsWith('/v1/students') && m === 'POST') return post()
    })
  }

  it('sends both emails trimmed, and omits a blank one', async () => {
    serveNew(() => json(201, student('s9', 'Mehedi', [])))
    renderNew()
    await userEvent.type(await screen.findByLabelText('Student name'), 'Mehedi')
    await userEvent.type(
      screen.getByLabelText(en('student_add_student_email')),
      ' mehedi@example.com ',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    await waitFor(() => expect(calls('POST', '/v1/students')).toHaveLength(1))
    const body = bodyOf(calls('POST', '/v1/students')[0]!) as Record<string, unknown>
    expect(body.student_email).toBe('mehedi@example.com')
    expect(body).not.toHaveProperty('guardian_email')
  })

  it('a malformed email is named under its field and Save is disabled', async () => {
    serveNew(() => json(201, student('s9', 'Mehedi', [])))
    renderNew()
    await userEvent.type(await screen.findByLabelText('Student name'), 'Mehedi')
    await userEvent.type(screen.getByLabelText(en('student_add_guardian_email')), 'mother@example')
    expect(screen.getByText(en('web_auth_email_invalid'))).toHaveAttribute('role', 'alert')
    expect(screen.getByRole('button', { name: 'Add student' })).toBeDisabled()
  })

  it('student.email.taken lands under the student email', async () => {
    serveNew(() =>
      json(409, {
        error: { code: 'CONFLICT', message_key: 'student.email.taken', retryable: false },
      }),
    )
    renderNew()
    await userEvent.type(await screen.findByLabelText('Student name'), 'Mehedi')
    const email = screen.getByLabelText(en('student_add_student_email'))
    await userEvent.type(email, 'mehedi@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Add student' }))
    const error = await screen.findByText(translateMessage('en', 'student.email.taken'))
    expect(email).toHaveAttribute('aria-describedby', error.id)
    expect(document.querySelector('.banner.error')).toBeNull()
  })

  it('both email fields refuse autofill: someone else’s address [NFR3.8]', async () => {
    serveNew(() => json(201, student('s9', 'Mehedi', [])))
    renderNew()
    for (const key of ['student_add_student_email', 'student_add_guardian_email']) {
      const field = await screen.findByLabelText(en(key))
      expect(field).toHaveAttribute('autocomplete', 'off')
      expect(field).toHaveAttribute('type', 'email')
    }
  })
})

describe('Student detail — contacts and the Edit sheet', () => {
  let current: ReturnType<typeof student>
  let patch: (body: unknown) => Response

  function renderDetail(body: ReturnType<typeof student>) {
    current = body
    api((m, u, b) => {
      if (u.endsWith('/v1/batches')) return json(200, batches)
      if (u.endsWith('/v1/students/s1') && m === 'GET') return json(200, current)
      if (u.endsWith('/v1/students/s1') && m === 'PATCH') return patch(b)
    })
    renderScreen(
      <Routes>
        <Route path="/students/:studentId" element={<StudentDetail />} />
      </Routes>,
      '/students/s1',
    )
  }

  const recorded = () =>
    student('s1', 'Rafiq', [], {
      student_phone: null,
      student_email: 'rafiq@example.com',
      guardian_phone: '+8801911000003',
      guardian_email: 'mother@example.com',
    })

  async function openEdit() {
    await userEvent.click(await screen.findByRole('button', { name: en('web_student_edit_title') }))
    return screen.findByTestId('edit-student-sheet')
  }

  beforeEach(() => {
    patch = () => json(200, current)
  })

  it('shows the student email in place of a missing phone, and both guardian contacts', async () => {
    renderDetail(recorded())
    expect(await screen.findByText('rafiq@example.com')).toBeInTheDocument()
    expect(
      screen.getByText(`${en('student_detail_guardian_link')} · 01911-000003 · mother@example.com`),
    ).toBeInTheDocument()
  })

  it('opens pre-filled, with focus on the first field and autofill off on both emails', async () => {
    renderDetail(recorded())
    const sheet = await openEdit()
    const name = within(sheet).getByLabelText('Student name')
    expect(document.activeElement).toBe(name)
    expect(name).toHaveValue('Rafiq')
    expect(within(sheet).getByLabelText(en('student_add_student_email'))).toHaveValue(
      'rafiq@example.com',
    )
    for (const key of ['student_add_student_email', 'student_add_guardian_email'])
      expect(within(sheet).getByLabelText(en(key))).toHaveAttribute('autocomplete', 'off')
  })

  it('saving with nothing changed sends nothing and closes', async () => {
    renderDetail(recorded())
    const sheet = await openEdit()
    await userEvent.click(within(sheet).getByRole('button', { name: en('web_student_edit_save') }))
    await waitFor(() => expect(screen.queryByTestId('edit-student-sheet')).toBeNull())
    expect(calls('PATCH', '/v1/students/s1')).toHaveLength(0)
  })

  it('an emptied email is sent as null, and the detail re-reads', async () => {
    renderDetail(recorded())
    const sheet = await openEdit()
    await userEvent.clear(within(sheet).getByLabelText(en('student_add_guardian_email')))
    const reads = calls('GET', '/v1/students/s1').length
    await userEvent.click(within(sheet).getByRole('button', { name: en('web_student_edit_save') }))
    await waitFor(() => expect(calls('PATCH', '/v1/students/s1')).toHaveLength(1))
    expect(bodyOf(calls('PATCH', '/v1/students/s1')[0]!)).toEqual({ guardian_email: null })
    await waitFor(() => expect(calls('GET', '/v1/students/s1').length).toBeGreaterThan(reads))
    expect(await screen.findByText(en('web_student_edit_saved'))).toBeInTheDocument()
  })

  it('a 409 student.number_accepted on clearing a phone shows in the sheet banner', async () => {
    patch = () =>
      json(409, {
        error: { code: 'CONFLICT', message_key: 'student.number_accepted', retryable: false },
      })
    renderDetail(recorded())
    const sheet = await openEdit()
    await userEvent.clear(within(sheet).getByLabelText(en('student_add_guardian')))
    await userEvent.click(within(sheet).getByRole('button', { name: en('web_student_edit_save') }))
    const banner = await within(sheet).findByRole('alert')
    expect(banner).toHaveTextContent(translateMessage('en', 'student.number_accepted'))
    expect(bodyOf(calls('PATCH', '/v1/students/s1')[0]!)).toEqual({ guardian_phone: null })
  })

  it('student.email.taken lands under the student email', async () => {
    patch = () =>
      json(409, {
        error: { code: 'CONFLICT', message_key: 'student.email.taken', retryable: false },
      })
    renderDetail(recorded())
    const sheet = await openEdit()
    const email = within(sheet).getByLabelText(en('student_add_student_email'))
    await userEvent.clear(email)
    await userEvent.type(email, 'other@example.com')
    await userEvent.click(within(sheet).getByRole('button', { name: en('web_student_edit_save') }))
    const error = await within(sheet).findByText(translateMessage('en', 'student.email.taken'))
    expect(email).toHaveAttribute('aria-describedby', error.id)
  })

  it('no connection offers Retry, which resends the same patch', async () => {
    let first = true
    patch = () => {
      if (first) {
        first = false
        throw new TypeError('Failed to fetch')
      }
      return json(200, current)
    }
    renderDetail(recorded())
    const sheet = await openEdit()
    await userEvent.clear(within(sheet).getByLabelText(en('student_add_guardian_email')))
    await userEvent.click(within(sheet).getByRole('button', { name: en('web_student_edit_save') }))
    await userEvent.click(await within(sheet).findByRole('button', { name: en('auth_retry') }))
    await waitFor(() => expect(calls('PATCH', '/v1/students/s1')).toHaveLength(2))
    expect(bodyOf(calls('PATCH', '/v1/students/s1')[1]!)).toEqual(
      bodyOf(calls('PATCH', '/v1/students/s1')[0]!),
    )
  })
})
