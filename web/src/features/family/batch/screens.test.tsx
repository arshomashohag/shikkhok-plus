import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { seatPattern, type Reader } from '../reader'
import { batchRoutes } from './index'
import { summaryText } from './Progress'

/** The routes exactly as the app mounts them for one reader. */
function mount(reader: Reader, path: string) {
  return renderScreen(
    <Routes>
      {batchRoutes.map((r) => {
        const p = r.path ? `${seatPattern(reader)}/${r.path}` : seatPattern(reader)
        return <Route key={p} path={p} element={r.element(reader)} />
      })}
    </Routes>,
    path,
  )
}

const teaching = {
  announcements: [
    {
      announcement_id: 'n1',
      body: 'Bring the solved worksheet',
      created_at: '2026-11-03T05:00:00Z',
      edited: false,
    },
  ],
  current_fee: {
    period: '2026-11',
    charged: '1200.00',
    outstanding: '1200.00',
    due_date: '2026-11-10',
    paid_on: null,
    status: 'unpaid',
    verifying: false,
  },
  exams: [
    {
      exam_id: 'e1',
      title: 'Weekly test 4',
      subject_name: 'Physics',
      date: '2026-10-12',
      state: 'done',
      topics: [],
      total_marks: 50,
    },
    {
      exam_id: 'e2',
      title: 'Monthly test',
      subject_name: 'Physics',
      date: '2026-11-30',
      state: 'upcoming',
      topics: ['Chapters 4–6'],
      total_marks: 100,
    },
  ],
  following_sessions: [
    {
      date: '2026-11-09',
      start_time: '16:00',
      end_time: '17:30',
      moved: false,
      starts_in_minutes: null,
      subject_name: null,
    },
  ],
  next_session: {
    date: '2026-11-05',
    start_time: '16:00',
    end_time: '17:30',
    moved: false,
    starts_in_minutes: 35,
    subject_name: 'Physics',
  },
  past_sessions: [],
  served_at: '2026-11-05T05:00:00Z',
  teacher: { display_name: 'Mahfuz Rahman', subjects: ['Physics'] },
}

const progress = [
  {
    exam_id: 'e1',
    title: 'Weekly test 4',
    date: '2026-10-12',
    total_marks: 50,
    result_state: 'marked',
    marks: 44,
    rank: 5,
    ranked_out_of: 19,
    batch_average: 36.7,
    subject_name: 'Physics',
  },
]

const calendar = {
  year: 2026,
  month: 11,
  first_month: '2026-08',
  last_month: '2026-11',
  today: '2026-11-05',
  served_at: 'x',
  days: [
    {
      date: '2026-11-03',
      state: 'taken',
      classes: [
        {
          session_id: 's1',
          date: '2026-11-03',
          start_time: '16:00',
          end_time: '17:30',
          state: 'taken',
          topic: 'Laws of motion',
          mark: 'absent',
          notes: 'Read ch. 3',
          subject_name: 'Physics',
          plannable: false,
          recordable: false,
          topic_version: 1,
          attendance_version: 1,
        },
      ],
    },
    ...['2026-11-09', '2026-11-07'].map((date, i) => ({
      date,
      state: 'upcoming',
      classes: [
        {
          session_id: `u${i}`,
          date,
          start_time: '16:00',
          end_time: '17:30',
          state: 'upcoming',
          topic: null,
          mark: null,
          notes: null,
          subject_name: 'Physics',
          plannable: true,
          recordable: false,
          topic_version: 0,
          attendance_version: 0,
        },
      ],
    })),
  ],
}

const fetchMock = vi.fn()
const urls = () => fetchMock.mock.calls.map(([u]) => String(u))

function api(overrides: Record<string, () => Response> = {}) {
  fetchMock.mockImplementation(async (url: string) => {
    for (const [part, respond] of Object.entries(overrides))
      if (url.includes(part)) return respond()
    if (url.includes('/teaching')) return json(200, teaching)
    if (url.includes('/progress/summary'))
      return json(200, {
        direction: 'up',
        run: 4,
        first_marks: 31,
        last_marks: 44,
        total_marks: 50,
        above_average: true,
      })
    if (url.includes('/progress')) return json(200, progress)
    if (url.includes('/calendar')) return json(200, calendar)
    if (url.includes('/marksheet'))
      return json(200, {
        exam_title: 'Weekly test 4',
        total_marks: 50,
        published: true,
        average: 36.666,
        highest: 48,
        marked_count: 19,
        viewer_marks: 44,
        viewer_rank: 5,
        viewer_result_state: 'marked',
        bands: [{ low: 40, high: 50, count: 6 }],
      })
    if (url.includes('/exams/')) return json(200, teaching.exams[1])
    if (url.endsWith('/v1/me/enrollments'))
      return json(200, [
        {
          enrollment_id: 'seat1',
          batch_name: 'Physics · Batch A',
          teacher_display_name: 'Mahfuz Rahman',
        },
      ])
    if (url.endsWith('/v1/guardian/children'))
      return json(200, [
        {
          enrollment_id: 'seat1',
          display_name: 'Tasnim',
          batch_name: 'Physics · Batch A',
          teacher_display_name: 'Mahfuz Rahman',
        },
      ])
    return json(404, {
      error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
    })
  })
}

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

describe('seat batch', () => {
  it('a student sees their own next class, fee with Send money, and the month’s classes', async () => {
    api()
    mount('me', '/my/seat1')
    expect(await screen.findByRole('heading', { name: 'Physics · Batch A' })).toBeInTheDocument()
    expect(screen.getByText('Today, 4:00–5:30 pm')).toBeInTheDocument()
    expect(screen.getByText('Next class · in 35 min')).toBeInTheDocument()
    expect(screen.getByText('November fee · ৳1,200')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Send money' })).toHaveAttribute(
      'href',
      '/my/seat1/pay',
    )
    expect(await screen.findByText('Laws of motion')).toBeInTheDocument()
    expect(screen.getByText(/Absent/)).toBeInTheDocument()
    expect(urls().some((u) => u.includes('/v1/me/batches/seat1/teaching'))).toBe(true)
    expect(urls().some((u) => u.includes('/v1/children/'))).toBe(false)

    // Covered first (newest first), then coming up (soonest first).
    const covered = screen.getByRole('region', { name: 'Topics covered' })
    expect(within(covered).getByRole('link', { name: /Laws of motion/ })).toHaveAttribute(
      'href',
      '/my/seat1/classes/s1?month=2026-11',
    )
    const comingUp = screen.getByRole('region', { name: 'Coming up' })
    const dates = within(comingUp)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
    expect(dates).toEqual([
      '/my/seat1/classes/u1?month=2026-11',
      '/my/seat1/classes/u0?month=2026-11',
    ])
  })

  it('a guardian reads the child’s endpoints, with the child’s name on every heading', async () => {
    api()
    mount('child', '/child/seat1?tab=exams')
    expect(await screen.findByText("Tasnim's results")).toBeInTheDocument()
    expect(screen.getByText("Tasnim's next class")).toBeInTheDocument()
    expect(screen.getByText("Tasnim's fee")).toBeInTheDocument()
    expect(screen.getByText('Coming up for Tasnim')).toBeInTheDocument()
    const result = screen.getByRole('link', { name: /Weekly test 4/ })
    expect(result).toHaveAttribute('href', '/child/seat1/exams/e1/marksheet')
    expect(within(result).getByText('44')).toBeInTheDocument()
    expect(within(result).getByText(/5 of 19/)).toBeInTheDocument()
    expect(urls().every((u) => !u.includes('/v1/me/'))).toBe(true)
  })

  it('hides the payment status when the page could not refresh', async () => {
    api()
    mount('me', '/my/seat1')
    await screen.findByText('November fee · ৳1,200')
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    window.dispatchEvent(new Event('online'))
    expect(await screen.findByText('Fee status unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Send money' })).toBeNull()
  })

  it('opens notices and the teacher tab', async () => {
    api()
    mount('me', '/my/seat1?tab=notices')
    const notice = await screen.findByRole('link', { name: /Bring the solved worksheet/ })
    expect(notice).toHaveAttribute('href', '/my/seat1/notices/n1')
    await userEvent.click(screen.getByRole('tab', { name: 'Teacher' }))
    expect(screen.getByText('Mahfuz Rahman', { selector: '.title' })).toBeInTheDocument()
  })

  it('shows the server’s refusal and a retry', async () => {
    api({
      '/teaching': () =>
        json(403, {
          error: { code: 'FORBIDDEN', message_key: 'authz.lens.not_available', retryable: false },
        }),
    })
    mount('me', '/my/seat1')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})

describe('details', () => {
  it('a class shows its topic, notes and attendance', async () => {
    api()
    mount('child', '/child/seat1/classes/s1?month=2026-11')
    expect(await screen.findByText('Laws of motion')).toBeInTheDocument()
    expect(screen.getByText('Read ch. 3')).toBeInTheDocument()
    expect(screen.getByText('Absent')).toBeInTheDocument()
    expect(urls().some((u) => u.includes('/v1/children/seat1/calendar?year=2026&month=11'))).toBe(
      true,
    )
  })

  it('a class that has gone says so', async () => {
    api()
    mount('me', '/my/seat1/classes/gone?month=2026-11')
    expect(await screen.findByText('This is no longer available.')).toBeInTheDocument()
  })

  it('an upcoming exam lists its topics', async () => {
    api()
    mount('me', '/my/seat1/exams/e2')
    expect(await screen.findByText('Monthly test')).toBeInTheDocument()
    expect(screen.getByText('Chapters 4–6')).toBeInTheDocument()
  })

  it('a notice shows its whole text', async () => {
    api()
    mount('me', '/my/seat1/notices/n1')
    expect(await screen.findByText('Bring the solved worksheet')).toBeInTheDocument()
  })

  it('a marksheet shows the server’s rank, average and highest', async () => {
    api()
    mount('child', '/child/seat1/exams/e1/marksheet')
    expect(await screen.findByText('Rank 5 of 19')).toBeInTheDocument()
    expect(screen.getByText('Class average: 36.7')).toBeInTheDocument()
    expect(screen.getByText('Highest: 48')).toBeInTheDocument()
    expect(screen.getByText('6 students')).toBeInTheDocument()
  })

  it('a suppressed marksheet shows only the student’s own mark', async () => {
    api({
      '/marksheet': () =>
        json(200, {
          exam_title: 'Weekly test 4',
          total_marks: 50,
          published: false,
          reason: 'too_few_results',
          viewer_marks: 44,
          viewer_result_state: 'marked',
        }),
    })
    mount('me', '/my/seat1/exams/e1/marksheet')
    expect(await screen.findByText('Your mark is shown on its own for now.')).toBeInTheDocument()
    expect(screen.queryByText(/Rank/)).toBeNull()
  })
})

describe('progress', () => {
  it('a guardian gets the server’s run, then each exam', async () => {
    api()
    mount('child', '/child/seat1/progress')
    expect(
      await screen.findByText(
        'Marks went up in each of the last 4 tests, from 31 to 44 out of 50. Now above the batch average.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "Tasnim's progress" })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Weekly test 4' })).toHaveAttribute(
      'href',
      '/child/seat1/exams/e1/marksheet',
    )
    expect(screen.getByText('5 of 19')).toBeInTheDocument()
  })

  it('a student has no summary endpoint and reads only their own', async () => {
    api()
    mount('me', '/my/seat1/progress')
    await screen.findByRole('link', { name: 'Weekly test 4' })
    expect(urls().some((u) => u.includes('/summary'))).toBe(false)
    expect(screen.getByRole('heading', { name: 'Progress' })).toBeInTheDocument()
  })

  it('words a run that held', () => {
    const t = (k: string, ...a: (string | number)[]) => `${k}(${a.join(',')})`
    expect(
      summaryText(
        {
          direction: 'same',
          run: 3,
          firstMarks: 40,
          lastMarks: 40,
          totalMarks: 50,
          aboveAverage: null,
        },
        t,
      ),
    ).toBe('web_fb_summary_same(3,40,40,50)')
  })
})
