import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { MoneyFormatError } from '../../../core/money'
import {
  formatAverage,
  identityFromChildren,
  identityFromMine,
  mapFamilyMonth,
  mapMarksheet,
  mapProgress,
  mapSummary,
  mapTeaching,
  monthKey,
  resultsByExam,
} from './mappers'

const teaching = (patch: Partial<Schemas['FamilyBatchViewResponse']> = {}) =>
  ({
    announcements: [
      {
        announcement_id: 'n1',
        body: 'Bring the worksheet',
        created_at: '2026-11-03T05:00:00Z',
        edited: true,
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
        title: 'Weekly 4',
        subject_name: 'Physics',
        date: '2026-10-12',
        state: 'done',
        topics: ['Heat'],
        total_marks: 50,
      },
      {
        exam_id: 'e2',
        title: 'Monthly',
        subject_name: 'Physics',
        date: '2026-11-30',
        state: 'upcoming',
        topics: [],
        total_marks: 100,
      },
    ],
    following_sessions: [],
    next_session: null,
    past_sessions: [],
    served_at: '2026-11-05T05:00:00Z',
    teacher: { display_name: 'মাহফুজুর রহমান', subjects: ['পদার্থবিজ্ঞান'] },
    ...patch,
  }) as Schemas['FamilyBatchViewResponse']

describe('seat identity', () => {
  it('names the student’s own seat without a child', () => {
    const id = identityFromMine(
      [
        {
          enrollment_id: 's1',
          batch_name: 'Batch A',
          teacher_display_name: 'T',
        } as Schemas['StudentBatchResponse'],
      ],
      's1',
    )
    expect(id).toEqual({ batchName: 'Batch A', teacherName: 'T', childName: null })
  })

  it('names the child for a guardian, and nothing for another seat', () => {
    const rows = [
      {
        enrollment_id: 'c1',
        display_name: 'তাসনিম',
        batch_name: 'Batch A',
        teacher_display_name: null,
      },
    ] as Schemas['GuardianChildResponse'][]
    expect(identityFromChildren(rows, 'c1')?.childName).toBe('তাসনিম')
    expect(identityFromChildren(rows, 'c2')).toBeNull()
  })
})

describe('mapTeaching', () => {
  it('splits exams by the server’s state and keeps its order', () => {
    const v = mapTeaching(teaching())
    expect(v.doneExams.map((e) => e.examId)).toEqual(['e1'])
    expect(v.upcomingExams.map((e) => e.examId)).toEqual(['e2'])
    expect(v.notices[0]).toMatchObject({ id: 'n1', edited: true })
  })

  it('offers payment only for a month the server says is owed and not being checked', () => {
    expect(mapTeaching(teaching()).fee?.payable).toBe(true)
    const verifying = teaching({
      current_fee: { ...teaching().current_fee!, verifying: true },
    })
    expect(mapTeaching(verifying).fee?.payable).toBe(false)
    expect(mapTeaching(verifying).fee?.chip.kind).toBe('verifying')
    const paid = teaching({ current_fee: { ...teaching().current_fee!, status: 'paid' } })
    expect(mapTeaching(paid).fee?.payable).toBe(false)
  })

  it('refuses a number where money belongs', () => {
    const broken = teaching({
      current_fee: { ...teaching().current_fee!, charged: 1200 as unknown as string },
    })
    expect(() => mapTeaching(broken)).toThrow(MoneyFormatError)
  })
})

describe('progress', () => {
  const rows = mapProgress([
    {
      exam_id: 'e1',
      title: 'W4',
      date: '2026-10-12',
      total_marks: 50,
      result_state: 'marked',
      marks: 44,
      rank: 5,
      ranked_out_of: 19,
      batch_average: 36.7,
      subject_name: null,
    },
    // An absence never carries a number, even if one were sent.
    {
      exam_id: 'e3',
      title: 'W3',
      date: '2026-10-05',
      total_marks: 50,
      result_state: 'absent',
      marks: 0,
      rank: null,
      ranked_out_of: null,
      batch_average: null,
      subject_name: null,
    },
  ] as Schemas['ProgressEntryResponse'][])

  it('keeps marks only for a marked result', () => {
    expect(rows[0]).toMatchObject({ marks: 44, rank: 5, rankedOutOf: 19 })
    expect(rows[1]).toMatchObject({ state: 'absent', marks: null })
    expect(resultsByExam(rows).get('e3')?.state).toBe('absent')
  })

  it('maps the guardian’s run, or nothing', () => {
    expect(mapSummary(null)).toBeNull()
    expect(
      mapSummary({
        direction: 'up',
        run: 4,
        first_marks: 31,
        last_marks: 44,
        total_marks: 50,
        above_average: true,
      }),
    ).toEqual({
      direction: 'up',
      run: 4,
      firstMarks: 31,
      lastMarks: 44,
      totalMarks: 50,
      aboveAverage: true,
    })
  })
})

describe('marksheet', () => {
  it('keeps a suppressed marksheet suppressed', () => {
    const m = mapMarksheet({
      exam_title: 'W4',
      total_marks: 50,
      reason: 'too_few_results',
      viewer_marks: 44,
      viewer_result_state: 'marked',
      published: false,
    })
    expect(m).toEqual({
      published: false,
      examTitle: 'W4',
      totalMarks: 50,
      ownState: 'marked',
      ownMarks: 44,
      reason: 'too_few_results',
    })
  })

  it('passes the published comparison through untouched', () => {
    const m = mapMarksheet({
      exam_title: 'W4',
      total_marks: 50,
      published: true,
      average: 36.666,
      highest: 48,
      marked_count: 19,
      viewer_marks: null,
      viewer_rank: null,
      viewer_result_state: 'absent',
      bands: [{ low: 40, high: 50, count: 6 }],
    })
    expect(m).toMatchObject({
      published: true,
      ownMarks: null,
      rank: null,
      markedCount: 19,
      highest: 48,
    })
    expect(formatAverage(36.666)).toBe('36.7')
  })
})

describe('month', () => {
  it('lists the month’s classes newest first, with attendance', () => {
    const m = mapFamilyMonth({
      year: 2026,
      month: 10,
      first_month: '2026-08',
      last_month: '2026-11',
      today: '2026-11-05',
      served_at: 'x',
      days: [
        {
          date: '2026-10-05',
          state: 'taken',
          classes: [
            {
              session_id: 'a',
              date: '2026-10-05',
              start_time: '16:00',
              end_time: '17:30',
              state: 'taken',
              topic: 'Heat',
              mark: 'present',
              notes: null,
              subject_name: 'Physics',
              plannable: false,
              recordable: false,
              topic_version: 1,
              attendance_version: 1,
            },
          ],
        },
        {
          date: '2026-10-07',
          state: 'taken',
          classes: [
            {
              session_id: 'b',
              date: '2026-10-07',
              start_time: '16:00',
              end_time: null,
              state: 'taken',
              topic: '  ',
              mark: null,
              notes: null,
              subject_name: null,
              plannable: false,
              recordable: false,
              topic_version: 0,
              attendance_version: 0,
            },
          ],
        },
      ],
    } as Schemas['MonthViewResponse'])
    expect(m.classes.map((c) => c.sessionId)).toEqual(['b', 'a'])
    expect(m.classes[0]).toMatchObject({ topic: null, mark: 'not_marked' })
    expect(m.classes[1]).toMatchObject({ topic: 'Heat', mark: 'present' })
    expect(m.first).toEqual({ year: 2026, month: 8 })
    expect(monthKey(m)).toBe('2026-10')
  })
})
