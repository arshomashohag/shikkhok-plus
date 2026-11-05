import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { json, renderScreen } from '../../../test/render'
import { CreateExam } from './ExamForm'
import { ExamResults } from './ExamResults'
import { ExamsTab } from './ExamsTab'
import { MarkEntry } from './MarkEntry'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const exam = (patch: Record<string, unknown> = {}) => ({
  exam_id: 'x1',
  title: 'Class test 2',
  subject_name: 'Chemistry',
  date: '2026-10-17',
  total_marks: 25,
  entered_count: 1,
  expected_count: 3,
  state: 'needs_marks',
  published: false,
  topics: [],
  ...patch,
})

const results = (patch: Record<string, unknown> = {}, examPatch: Record<string, unknown> = {}) => ({
  exam: exam(examPatch),
  writable: true,
  results: [
    { enrollment_id: 'e1', display_name: 'Shahriar', result_state: 'marked', marks: 22 },
    { enrollment_id: 'e2', display_name: 'Soumitra', result_state: 'not_entered', marks: null },
    { enrollment_id: 'e3', display_name: 'Nafisa', result_state: 'not_entered', marks: null },
    { enrollment_id: 'e4', display_name: 'Ritu', result_state: 'joined_after', marks: null },
  ],
  ...patch,
})

const calls = (suffix: string) =>
  fetchMock.mock.calls.filter(
    ([u, init]) => (u as string).endsWith(suffix) && init?.method === 'POST',
  )
const body = (call: unknown[]) => JSON.parse((call[1] as RequestInit).body as string) as unknown

const tab = { batchId: 'b1', batch: null, reloadBatch: () => undefined }

describe('ExamsTab', () => {
  it('groups exams and opens marked ones as results, the rest as mark entry', async () => {
    fetchMock.mockResolvedValue(
      json(200, [
        exam({ exam_id: 'n1', title: 'Weekly test 5' }),
        exam({ exam_id: 'u1', title: 'Monthly test', state: 'upcoming' }),
        exam({ exam_id: 'c1', title: 'Weekly test 4', state: 'complete', published: false }),
      ]),
    )
    renderScreen(<ExamsTab {...tab} />)
    expect(await screen.findByText('Needs marks')).toBeInTheDocument()
    expect(screen.getByText('Coming up')).toBeInTheDocument()
    expect(screen.getByText('Draft · not published')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Weekly test 5/ })).toHaveAttribute(
      'href',
      '/exams/n1/marks',
    )
    expect(screen.getByRole('link', { name: /Weekly test 4/ })).toHaveAttribute(
      'href',
      '/exams/c1/results',
    )
    expect(screen.getByRole('link', { name: /New exam/ })).toHaveAttribute(
      'href',
      '/batches/b1/exams/new',
    )
  })

  it('offers the first exam when there is none', async () => {
    fetchMock.mockResolvedValue(json(200, []))
    renderScreen(<ExamsTab {...tab} />)
    expect(await screen.findByText('No exams yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add an exam' })).toBeInTheDocument()
  })
})

describe('CreateExam', () => {
  const batch = {
    id: 'b1',
    name: 'Chemistry · Batch C',
    subject_options: [{ id: 's1', name: 'Chemistry' }],
  }

  it('creates with the only subject chosen, then returns to the Exams tab', async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? json(201, { exam_id: 'x9' }) : json(200, [batch]),
    )
    renderScreen(
      <Routes>
        <Route path="/batches/:batchId/exams/new" element={<CreateExam />} />
        <Route path="/batches/:batchId" element={<p>batch screen</p>} />
      </Routes>,
      '/batches/b1/exams/new',
    )
    await userEvent.type(await screen.findByLabelText('Exam title'), 'Class test 2')
    await userEvent.type(screen.getByLabelText('Total marks'), '25')
    await userEvent.type(screen.getByLabelText('Topics (one per line)'), 'Acids{enter}Bases')
    await userEvent.click(screen.getByRole('button', { name: 'Create exam' }))
    expect(await screen.findByText('batch screen')).toBeInTheDocument()
    const call = calls('/v1/batches/b1/exams')[0]!
    expect(body(call)).toMatchObject({
      title: 'Class test 2',
      total_marks: 25,
      batch_subject_id: 's1',
      topics: ['Acids', 'Bases'],
    })
  })

  it('refuses a missing title and a zero total without calling the server', async () => {
    fetchMock.mockResolvedValue(json(200, [batch]))
    renderScreen(
      <Routes>
        <Route path="/batches/:batchId/exams/new" element={<CreateExam />} />
      </Routes>,
      '/batches/b1/exams/new',
    )
    await userEvent.type(await screen.findByLabelText('Total marks'), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Create exam' }))
    expect(screen.getByText('An exam must be out of at least one mark.')).toBeInTheDocument()
    expect(calls('/exams')).toHaveLength(0)
  })
})

function renderEntry(path = '/exams/x1/marks') {
  return renderScreen(
    <Routes>
      <Route path="/exams/:examId/marks" element={<MarkEntry />} />
    </Routes>,
    path,
  )
}

describe('MarkEntry', () => {
  it('starts at the first student without a result, saves on Enter and moves on', async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? new Response(null, { status: 204 }) : json(200, results()),
    )
    renderEntry()
    const soumitra = await screen.findByLabelText('Soumitra')
    await waitFor(() => expect(soumitra).toHaveFocus())
    // The student who joined after the exam has no box.
    expect(screen.queryByLabelText('Ritu')).toBeNull()
    expect(screen.getByText('This student joined after the exam.')).toBeInTheDocument()

    await userEvent.type(soumitra, '১৯.৫{Enter}')
    await waitFor(() => expect(calls('/v1/exams/x1/marks')).toHaveLength(1))
    expect(body(calls('/v1/exams/x1/marks')[0]!)).toEqual({
      enrollment_id: 'e2',
      result_state: 'marked',
      marks: 19.5,
    })
    await waitFor(() => expect(screen.getByLabelText('Nafisa')).toHaveFocus())
  })

  it('keeps a refused mark in its box with the server’s message', async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? json(422, {
            error: { code: 'VALIDATION', message_key: 'marks.out_of_range', retryable: false },
          })
        : json(200, results()),
    )
    renderEntry()
    const box = await screen.findByLabelText('Soumitra')
    await userEvent.type(box, '27{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('outside the exam')
    expect(box).toHaveValue('27')
    expect(box).toHaveAttribute('aria-invalid', 'true')
  })

  it('marks Absent from the dock without also saving what was typed', async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? new Response(null, { status: 204 }) : json(200, results()),
    )
    renderEntry()
    const box = await screen.findByLabelText('Soumitra')
    await userEvent.type(box, '5')
    await userEvent.click(screen.getByRole('button', { name: 'Absent' }))
    await waitFor(() => expect(calls('/marks').length).toBeGreaterThan(0))
    const sent = calls('/marks').map(body)
    expect(sent).toEqual([{ enrollment_id: 'e2', result_state: 'absent', marks: null }])
  })

  it('offers Publish only when the server counts nobody left, and publishes', async () => {
    let published = false
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/publish')) {
        published = true
        return new Response(null, { status: 204 })
      }
      return json(200, results({}, { entered_count: 3, expected_count: 3, published }))
    })
    renderEntry()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Publish to students & guardians' }),
    )
    expect(await screen.findByText(/Published to students and guardians/)).toBeInTheDocument()
    expect(calls('/v1/exams/x1/publish')).toHaveLength(1)
  })

  it('says how many are left instead of offering Publish', async () => {
    fetchMock.mockResolvedValue(json(200, results()))
    renderEntry()
    expect(await screen.findByText('2 still to enter before publishing')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Publish/ })).toBeNull()
  })

  it('shows a read-only exam without boxes when the server says so', async () => {
    fetchMock.mockResolvedValue(json(200, results({ writable: false })))
    renderEntry()
    expect(await screen.findByText('Marks cannot be changed for this exam.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Absent' })).toBeNull()
  })
})

describe('ExamResults', () => {
  it('shows each result and its history, and links each correction', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/history')
        ? json(200, [
            {
              mark_id: 'm1',
              result_state: 'marked',
              marks: 20,
              recorded_at: new Date().toISOString(),
              superseded: true,
            },
            {
              mark_id: 'm2',
              result_state: 'marked',
              marks: 22,
              recorded_at: new Date().toISOString(),
              superseded: false,
            },
          ])
        : json(
            200,
            results(
              {},
              { state: 'complete', published: true, entered_count: 3, expected_count: 3 },
            ),
          ),
    )
    renderScreen(
      <Routes>
        <Route path="/exams/:examId/results" element={<ExamResults />} />
      </Routes>,
      '/exams/x1/results',
    )
    expect(await screen.findByText(/Published to students and guardians/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Correct · Soumitra' })).toHaveAttribute(
      'href',
      '/exams/x1/marks?seat=e2',
    )
    await userEvent.click(screen.getByRole('button', { name: 'History · Shahriar' }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText(/Replaced/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Current/)).toBeInTheDocument()
  })
})
