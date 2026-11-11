/**
 * The classes screens against a scripted API: the calendar tab, recording
 * a class (and both kinds of conflict), planning one that has started,
 * the schedule and the batch edit.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { ClassesTab } from './ClassesTab'
import { EditBatchScreen } from './EditBatchScreen'
import { ScheduleScreen } from './ScheduleScreen'
import { SessionScreen } from './SessionScreen'

type Handler = (body: unknown) => Response | Promise<Response>
const fetchMock = vi.fn()
let routes: Record<string, Handler> = {}

function serve(table: Record<string, Handler | unknown>) {
  routes = Object.fromEntries(
    Object.entries(table).map(([k, v]) => [
      k,
      typeof v === 'function' ? (v as Handler) : () => json(200, v),
    ]),
  )
}

function calls(method: string, path: string) {
  return fetchMock.mock.calls
    .filter(
      ([u, init]) =>
        (init?.method ?? 'GET') === method && new URL(u as string, 'http://x').pathname === path,
    )
    .map(([, init]) => JSON.parse((init?.body as string) ?? 'null') as Record<string, unknown>)
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${new URL(url, 'http://x').pathname}`
    const handler = routes[key]
    if (!handler)
      return json(404, {
        error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
      })
    return handler(init?.body ? JSON.parse(init.body as string) : undefined)
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const BATCH = {
  id: 'b1',
  name: 'Physics · Batch A',
  active: true,
  accepted_count: 2,
  enrollment_count: 2,
  default_fee: '1200.00',
  fee_due_day: 10,
  marksheet_visible: true,
  schedule: [{ weekday: 0, start_time: '16:00', end_time: '17:30' }],
  subject_options: [
    { id: 'sub1', name: '1st paper' },
    { id: 'sub2', name: '2nd paper' },
  ],
  subjects: ['1st paper', '2nd paper'],
  teacher_display_name: null,
}

const calClass = (patch: Record<string, unknown>) => ({
  session_id: 's1',
  date: '2026-11-05',
  start_time: '16:00:00',
  end_time: '17:30:00',
  subject_name: '1st paper',
  state: 'today',
  topic: null,
  notes: null,
  plannable: false,
  recordable: true,
  topic_version: 3,
  attendance_version: 7,
  mark: null,
  ...patch,
})

const month = (classes: Record<string, unknown>[]) => ({
  year: 2026,
  month: 11,
  first_month: '2026-11',
  last_month: '2026-12',
  served_at: '2026-11-05T10:00:00+06:00',
  today: '2026-11-05',
  days: classes.map((c) => ({ date: c.date, state: c.state, classes: [c] })),
})

const session = (patch: Record<string, unknown> = {}) => ({
  session_id: 's1',
  date: '2026-11-05',
  start_time: '16:00:00',
  end_time: '17:30:00',
  status: 'scheduled',
  origin: 'recurrence',
  subject_name: '1st paper',
  topic: null,
  topic_logged: false,
  topic_version: 3,
  attendance_version: 7,
  ...patch,
})

const ROSTER = {
  attendance_version: 7,
  writable: true,
  seats: [
    { enrollment_id: 'e1', display_name: 'Tasnim', present: null },
    { enrollment_id: 'e2', display_name: 'Rafsan', present: null },
  ],
}

function at(path: string, pattern: string, element: ReactElement) {
  return renderScreen(
    <Routes>
      <Route path={pattern} element={element} />
    </Routes>,
    path,
  )
}

describe('Classes tab', () => {
  it('draws the month, opens on today and links each class to its screen', async () => {
    serve({
      'GET /v1/batches/b1/calendar': month([
        calClass({}),
        calClass({ session_id: 's0', date: '2026-11-02', state: 'not_recorded' }),
      ]),
    })
    renderScreen(<ClassesTab batchId="b1" batch={null} reloadBatch={() => {}} />)
    const today = await screen.findByRole('button', { name: '5, today' })
    await waitFor(() => expect(today).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.getByRole('button', { name: '2, not recorded' })).toBeInTheDocument()
    // The first month the server allows: no going back further.
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeDisabled()
    expect(screen.getByRole('link', { name: /4:00 pm/ })).toHaveAttribute(
      'href',
      '/batches/b1/classes/s1',
    )
    await userEvent.click(screen.getByRole('button', { name: '2, not recorded' }))
    expect(screen.getByRole('link', { name: /not recorded/ })).toHaveAttribute(
      'href',
      '/batches/b1/classes/s0',
    )
  })

  it('adds a one-off class: a date and a start, as Android asks', async () => {
    serve({
      'GET /v1/batches/b1/calendar': month([calClass({})]),
      'POST /v1/batches/b1/sessions': () =>
        json(201, session({ session_id: 's9', date: '2026-11-20' })),
    })
    renderScreen(<ClassesTab batchId="b1" batch={null} reloadBatch={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Add class' }))
    const dialog = await screen.findByRole('dialog')
    const date = within(dialog).getByLabelText('Date')
    await userEvent.clear(date)
    await userEvent.type(date, '2026-11-20')
    const start = within(dialog).getByLabelText('Starts')
    await userEvent.clear(start)
    await userEvent.type(start, '18:00')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add class' }))
    expect(await screen.findByText('Class added.')).toBeInTheDocument()
    expect(calls('POST', '/v1/batches/b1/sessions')[0]).toEqual({
      date: '2026-11-20',
      start_time: '18:00',
      end_time: null,
      batch_subject_id: null,
    })
  })
})

describe('Record a class', () => {
  function base(extra: Record<string, Handler | unknown> = {}) {
    serve({
      'GET /v1/sessions/s1': session(),
      'GET /v1/batches/b1/calendar': month([calClass({})]),
      'GET /v1/batches': [BATCH],
      'GET /v1/sessions/s1/attendance': ROSTER,
      'GET /v1/batches/b1/sessions': [
        session({
          session_id: 's0',
          date: '2026-11-02',
          topic: 'Newton’s first law',
          topic_logged: true,
        }),
      ],
      'PUT /v1/sessions/s1/subject': session({ subject_name: '2nd paper' }),
      'PUT /v1/sessions/s1/topic': { topic_version: 4 },
      'POST /v1/sessions/s1/attendance': { attendance_version: 8, submission_id: 'x' },
      ...extra,
    })
    return at('/batches/b1/classes/s1', '/batches/:batchId/classes/:sessionId', <SessionScreen />)
  }

  it('saves subject, topic and attendance in one go, as Android does', async () => {
    base()
    expect(await screen.findByRole('heading', { name: 'Record class' })).toBeInTheDocument()
    // The continue suggestion fills the topic.
    await userEvent.click(screen.getByRole('button', { name: 'Continue: Newton’s first law' }))
    expect(screen.getByLabelText('What did you cover?')).toHaveValue('Newton’s first law')
    await userEvent.click(screen.getByRole('button', { name: '2nd paper' }))
    // One tap on the row marks the student absent [UX-1].
    await userEvent.click(screen.getByRole('button', { name: 'Rafsan Present' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save class' }))

    expect(await screen.findByText('Class saved.')).toBeInTheDocument()
    expect(calls('PUT', '/v1/sessions/s1/subject')[0]).toEqual({ batch_subject_id: 'sub2' })
    expect(calls('PUT', '/v1/sessions/s1/topic')[0]).toMatchObject({
      base_topic_version: 3,
      topic: 'Newton’s first law',
      notes: '',
      plan: false,
    })
    expect(calls('POST', '/v1/sessions/s1/attendance')[0]).toMatchObject({
      base_attendance_version: 7,
      seats: [
        { enrollment_id: 'e1', present: true },
        { enrollment_id: 'e2', present: false },
      ],
    })
  })

  it('makes each whole seat row one toggle named by the student [UX-1]', async () => {
    base()
    const tasnim = await screen.findByRole('button', { name: 'Tasnim Present' })
    // Unmarked seats start present, as on Android; pressed means present.
    expect(tasnim).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('button', { name: 'Absent' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Mark everyone present' })).toBeNull()

    await userEvent.click(tasnim)
    const absent = screen.getByRole('button', { name: 'Tasnim Absent' })
    expect(absent).toHaveAttribute('aria-pressed', 'false')
    // The running number is decoration, not part of the name.
    expect(absent).toHaveTextContent('01')
    expect(absent.querySelector('[aria-hidden="true"]')).toHaveTextContent('01')

    // A second tap undoes the first.
    await userEvent.click(absent)
    expect(screen.getByRole('button', { name: 'Tasnim Present' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    // "Mark everyone present" appears once someone is absent and clears it.
    await userEvent.click(screen.getByRole('button', { name: 'Rafsan Present' }))
    await userEvent.click(screen.getByRole('button', { name: 'Mark everyone present' }))
    expect(screen.getByRole('button', { name: 'Rafsan Present' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('replays the same write after a dropped connection', async () => {
    let attempts = 0
    base({
      'PUT /v1/sessions/s1/topic': () => {
        attempts++
        if (attempts === 1) throw new TypeError('Failed to fetch')
        return json(200, { topic_version: 4 })
      },
    })
    await userEvent.type(await screen.findByLabelText('What did you cover?'), 'Vectors')
    await userEvent.click(screen.getByRole('button', { name: 'Save class' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/connection/)
    expect(calls('POST', '/v1/sessions/s1/attendance')).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Save class' }))
    expect(await screen.findByText('Class saved.')).toBeInTheDocument()
    const [first, second] = calls('PUT', '/v1/sessions/s1/topic')
    expect(second?.client_mutation_id).toBe(first?.client_mutation_id)
  })

  it('shows a topic conflict and saves mine on the current version only when asked', async () => {
    let topicWrites = 0
    base({
      'PUT /v1/sessions/s1/topic': () =>
        ++topicWrites === 1
          ? json(409, {
              error: {
                code: 'TOPIC_VERSION_CONFLICT',
                message_key: 'error.topic_version_conflict',
                retryable: false,
                details: { expected_version: '3', current_version: '5' },
              },
            })
          : json(200, { topic_version: 6 }),
    })
    await userEvent.type(await screen.findByLabelText('What did you cover?'), 'Vectors')
    serve({ ...routes, 'GET /v1/sessions/s1': session({ topic: 'Scalars', topic_version: 5 }) })
    await userEvent.click(screen.getByRole('button', { name: 'Save class' }))
    const panel = await screen.findByRole('alert')
    expect(panel).toHaveTextContent('Scalars')
    expect(panel).toHaveTextContent('Vectors')
    expect(calls('POST', '/v1/sessions/s1/attendance')).toHaveLength(0)
    await userEvent.click(within(panel).getByRole('button', { name: 'Use what I recorded' }))
    expect(await screen.findByText('Class saved.')).toBeInTheDocument()
    expect(calls('PUT', '/v1/sessions/s1/topic')[1]).toMatchObject({
      base_topic_version: 5,
      topic: 'Vectors',
    })
  })

  it('shows an attendance conflict seat by seat and can keep the current record', async () => {
    base({
      'POST /v1/sessions/s1/attendance': () =>
        json(409, {
          error: {
            code: 'ATTENDANCE_VERSION_CONFLICT',
            message_key: 'error.attendance_version_conflict',
            retryable: false,
            details: {
              expected_version: '7',
              current_version: '9',
              current_state: 'e1:absent,e2:present',
            },
          },
        }),
    })
    await screen.findByRole('heading', { name: 'Record class' })
    await userEvent.click(screen.getByRole('button', { name: 'Save class' }))
    const panel = await screen.findByRole('alert')
    const tasnim = within(panel).getByRole('row', { name: /Tasnim/ })
    expect(
      within(tasnim)
        .getAllByRole('cell')
        .map((c) => c.textContent),
    ).toEqual(['Present', 'Absent'])
    await userEvent.click(within(panel).getByRole('button', { name: 'Keep the current record' }))
    expect(await screen.findByText('Nothing changed.')).toBeInTheDocument()
    expect(calls('POST', '/v1/sessions/s1/attendance')).toHaveLength(1)
  })
})

describe('Plan a class', () => {
  it('offers "Save as covered" when the class has started, and sends it as a record', async () => {
    let writes = 0
    serve({
      'GET /v1/sessions/s1': session(),
      'GET /v1/batches/b1/calendar': month([
        calClass({ recordable: false, plannable: true, state: 'upcoming' }),
      ]),
      'GET /v1/batches': [{ ...BATCH, subject_options: [{ id: 'sub1', name: '1st paper' }] }],
      'PUT /v1/sessions/s1/topic': () =>
        ++writes === 1
          ? json(409, {
              error: {
                code: 'CLASS_STARTED',
                message_key: 'teaching.topic.class_started',
                retryable: false,
              },
            })
          : json(200, { topic_version: 4 }),
    })
    at('/batches/b1/classes/s1', '/batches/:batchId/classes/:sessionId', <SessionScreen />)
    await userEvent.type(await screen.findByLabelText('Planned topics'), 'Chapter 4')
    // A single subject is stated, not offered.
    expect(screen.getByText('Subject: 1st paper')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save plan' }))
    expect(await screen.findByText('This class has started')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save as covered' }))
    expect(await screen.findByText('Class saved.')).toBeInTheDocument()
    const [plan, covered] = calls('PUT', '/v1/sessions/s1/topic')
    expect(plan).toMatchObject({ plan: true, topic: 'Chapter 4' })
    expect(covered).toMatchObject({ plan: false, topic: 'Chapter 4', base_topic_version: 3 })
    expect(covered?.client_mutation_id).not.toBe(plan?.client_mutation_id)
  })

  it('moves and cancels a scheduled class', async () => {
    serve({
      'GET /v1/sessions/s1': session(),
      'GET /v1/batches/b1/calendar': month([
        calClass({ recordable: false, plannable: true, state: 'upcoming' }),
      ]),
      'GET /v1/batches': [BATCH],
      'POST /v1/sessions/s1/cancellation': session({ status: 'cancelled' }),
    })
    at('/batches/b1/classes/s1', '/batches/:batchId/classes/:sessionId', <SessionScreen />)
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel this class' }))
    const dialog = await screen.findByRole('dialog')
    serve({ ...routes, 'GET /v1/sessions/s1': session({ status: 'cancelled' }) })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel class' }))
    expect(await screen.findByText('Class cancelled.')).toBeInTheDocument()
    expect(calls('POST', '/v1/sessions/s1/cancellation')).toHaveLength(1)
  })
})

describe('Schedule and batch edit', () => {
  it('saves the days with one time range', async () => {
    serve({
      'GET /v1/batches/b1/schedule': [{ weekday: 0, start_time: '16:00', end_time: '17:30' }],
      'PUT /v1/batches/b1/schedule': (body: unknown) =>
        json(200, (body as { slots: unknown }).slots),
    })
    at('/batches/b1/schedule', '/batches/:batchId/schedule', <ScheduleScreen />)
    await userEvent.click(await screen.findByRole('button', { name: 'Sat' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save schedule' }))
    await waitFor(() => expect(calls('PUT', '/v1/batches/b1/schedule')).toHaveLength(1))
    expect(calls('PUT', '/v1/batches/b1/schedule')[0]).toEqual({
      slots: [
        { weekday: 0, start_time: '16:00', end_time: '17:30' },
        { weekday: 5, start_time: '16:00', end_time: '17:30' },
      ],
    })
  })

  it('refuses an end before the start without calling the server', async () => {
    serve({
      'GET /v1/batches/b1/schedule': [{ weekday: 0, start_time: '16:00', end_time: '17:30' }],
    })
    at('/batches/b1/schedule', '/batches/:batchId/schedule', <ScheduleScreen />)
    const end = await screen.findByLabelText(/Ends/)
    await userEvent.clear(end)
    await userEvent.type(end, '15:00')
    await userEvent.click(screen.getByRole('button', { name: 'Save schedule' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A class must end after it starts.')
    expect(calls('PUT', '/v1/batches/b1/schedule')).toHaveLength(0)
  })

  it('sends only the fields that changed, and shows the server’s refusal', async () => {
    serve({
      'GET /v1/batches': [BATCH],
      'PATCH /v1/batches/b1': () =>
        json(409, {
          error: { code: 'CONFLICT', message_key: 'batch.subject_in_use', retryable: false },
        }),
    })
    at('/batches/b1/edit', '/batches/:batchId/edit', <EditBatchScreen />)
    const fee = await screen.findByLabelText('Monthly fee (optional)')
    expect(fee).toHaveValue('1,200')
    const subjects = screen.getByLabelText('Subjects, separated by commas (required)')
    await userEvent.clear(subjects)
    await userEvent.type(subjects, '1st paper')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(calls('PATCH', '/v1/batches/b1')[0]).toEqual({ subjects: ['1st paper'] })
  })
})
