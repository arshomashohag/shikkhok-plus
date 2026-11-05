import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import {
  cleanTyped,
  groupExams,
  mapExam,
  mapHistory,
  mapResults,
  progressOf,
  rollLabel,
  topicsOf,
  topicsValid,
  typedMark,
  UnknownResultState,
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

  it('fails loudly on a result state it cannot name', () => {
    const bad = dto(true)
    bad.results[0] = { ...bad.results[0]!, result_state: 'exempt' as 'marked' }
    expect(() => mapResults(bad)).toThrow(UnknownResultState)
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
