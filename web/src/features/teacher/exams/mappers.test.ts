import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import {
  canCancel,
  cleanTyped,
  groupExams,
  mapExam,
  mapHistory,
  mapResults,
  progressOf,
  rollLabel,
  STATE_KEYS,
  topicsOf,
  topicsValid,
  typedMark,
} from './mappers'

function exam(
  patch: Partial<Schemas['ExamListItemResponse']> = {},
): Schemas['ExamListItemResponse'] {
  return {
    exam_id: 'x1',
    title: 'Class test 2',
    subject_name: 'রসায়ন',
    date: '2026-10-17',
    total_marks: 25,
    entered_count: 2,
    expected_count: 4,
    state: 'needs_marks',
    published: false,
    cancelled: false,
    topics: [],
    ...patch,
  }
}

describe('groupExams — ExamsTab.kt grouping', () => {
  it('needs marks, then coming up, then marked newest first; empty groups dropped', () => {
    const groups = groupExams(
      [
        exam({ exam_id: 'a', state: 'complete' }),
        exam({ exam_id: 'b', state: 'needs_marks' }),
        exam({ exam_id: 'c', state: 'complete' }),
      ].map(mapExam),
    )
    expect(groups.map((g) => g.titleKey)).toEqual(['batch_exams_needs_marks', 'batch_exams_done'])
    expect(groups[1]?.exams.map((e) => e.examId)).toEqual(['c', 'a'])
  })

  it('reads a missing published flag as not published', () => {
    const dto: Partial<Schemas['ExamListItemResponse']> = exam()
    delete dto.published
    expect(mapExam(dto as Schemas['ExamListItemResponse']).published).toBe(false)
  })
})

describe('mapResults', () => {
  const dto = (writable: boolean): Schemas['ExamResultsResponse'] => ({
    exam: exam({ entered_count: 2, expected_count: 3 }),
    writable,
    results: [
      { enrollment_id: 'e1', display_name: 'A', result_state: 'marked', marks: 22 },
      { enrollment_id: 'e2', display_name: 'B', result_state: 'absent', marks: null },
      { enrollment_id: 'e3', display_name: 'C', result_state: 'not_entered', marks: null },
      { enrollment_id: 'e4', display_name: 'D', result_state: 'joined_after', marks: null },
    ],
  })

  it('takes writability from the server and locks seats that joined after', () => {
    const r = mapResults(dto(true))
    expect(r.rows.map((x) => x.editable)).toEqual([true, true, true, false])
    expect(r.rows.map((x) => x.hasHistory)).toEqual([true, true, false, false])
    expect(r.toEnter).toBe(1)
    expect(progressOf(r.rows)).toEqual({ done: 2, of: 3 })
  })

  it('locks every seat when the server says the exam is not writable', () => {
    expect(mapResults(dto(false)).rows.every((x) => !x.editable)).toBe(true)
  })

  it('names a result state it does not know as unknown, on that row only, and locks it', () => {
    const newer = dto(true)
    newer.results[0] = { ...newer.results[0]!, result_state: 'exempt' as 'marked' }
    const r = mapResults(newer)
    expect(r.rows[0]).toMatchObject({ state: 'unknown', editable: false, hasHistory: false })
    expect(STATE_KEYS[r.rows[0]!.state]).toBe('web_status_unknown')
    // The other seats are drawn and editable as before.
    expect(r.rows.slice(1).map((x) => x.editable)).toEqual([true, true, false])
    expect(progressOf(r.rows)).toEqual({ done: 1, of: 2 })
  })

  it('names an unknown state in a mark history rather than failing it', () => {
    expect(
      mapHistory([
        {
          mark_id: 'm1',
          result_state: 'exempt' as 'marked',
          marks: null,
          recorded_at: '2026-11-01T00:00:00Z',
          superseded: false,
        },
      ])[0]?.state,
    ).toBe('unknown')
  })

  it('never reports a negative number still to enter', () => {
    expect(
      mapResults({ ...dto(true), exam: exam({ entered_count: 5, expected_count: 3 }) }).toEnter,
    ).toBe(0)
  })
})

describe('typing a mark (format only)', () => {
  it.each([
    ['22', '22'],
    ['19.5', '19.5'],
    ['১৯.৫', '19.5'],
    ['12345', '123'],
    ['7.255', '7.25'],
    ['.5', '0.5'],
    ['1..2', '1.2'],
    ['2a4', '24'],
    ['-3', '3'],
  ])('%p → %p', (raw, cleaned) => {
    expect(cleanTyped(raw)).toBe(cleaned)
  })

  it.each([
    ['22', 22],
    ['19.5', 19.5],
    ['20.', 20],
    ['', null],
    ['.', null],
  ])('%p reads as %p', (typed, mark) => {
    expect(typedMark(typed)).toBe(mark)
  })
})

it('maps history oldest first, keeping what was replaced', () => {
  expect(
    mapHistory([
      {
        mark_id: 'm1',
        result_state: 'marked',
        marks: 22,
        recorded_at: '2026-11-05T04:00:00Z',
        superseded: true,
      },
      {
        mark_id: 'm2',
        result_state: 'marked',
        marks: 23,
        recorded_at: '2026-11-05T04:05:00Z',
        superseded: false,
      },
    ]).map((h) => [h.marks, h.superseded]),
  ).toEqual([
    [22, true],
    [23, false],
  ])
})

it('rolls, topics and their limits', () => {
  expect(rollLabel(3)).toBe('04')
  expect(topicsOf(' Chapter 4 \n\n Chapter 5\n')).toEqual(['Chapter 4', 'Chapter 5'])
  expect(topicsValid(Array.from({ length: 20 }, () => 'x'))).toBe(true)
  expect(topicsValid(Array.from({ length: 21 }, () => 'x'))).toBe(false)
  expect(topicsValid(['x'.repeat(121)])).toBe(false)
})

describe('cancelled exams', () => {
  it('reads a missing flag from an older server as not cancelled', () => {
    const older: Partial<Schemas['ExamListItemResponse']> = { ...exam() }
    delete older.cancelled
    expect(mapExam(older as Schemas['ExamListItemResponse']).cancelled).toBe(false)
  })

  it('moves a cancelled exam out of the working groups into its own, last', () => {
    const groups = groupExams(
      [
        exam({ exam_id: 'a' }),
        exam({ exam_id: 'b', cancelled: true, cancellation_reason: 'Hartal' }),
        exam({ exam_id: 'c', state: 'upcoming', cancelled: true }),
      ].map(mapExam),
    )
    expect(groups.map((g) => [g.titleKey, g.exams.map((e) => e.examId)])).toEqual([
      ['batch_exams_needs_marks', ['a']],
      ['exam_cancelled_chip', ['b', 'c']],
    ])
    expect(groups[1]?.exams[0]?.cancellationReason).toBe('Hartal')
  })

  it('offers cancelling only an exam still on whose results are not out', () => {
    expect(canCancel(mapExam(exam()))).toBe(true)
    expect(canCancel(mapExam(exam({ published: true })))).toBe(false)
    expect(canCancel(mapExam(exam({ cancelled: true })))).toBe(false)
  })
})
