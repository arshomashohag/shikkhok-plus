/**
 * The family read calls, one function per screen need, each choosing the
 * student (`/v1/me/...`) or guardian (`/v1/children/...`) endpoint by
 * reader. The reader picks a URL; the server checks the lens.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import type { Reader } from '../reader'

const enc = encodeURIComponent

export const listMySeats = (signal?: AbortSignal) =>
  request<Schemas['StudentBatchResponse'][]>('GET', '/v1/me/enrollments', { signal })

export const listChildSeats = (signal?: AbortSignal) =>
  request<Schemas['GuardianChildResponse'][]>('GET', '/v1/guardian/children', { signal })

export const readTeaching = (reader: Reader, seat: string, signal?: AbortSignal) =>
  request<Schemas['FamilyBatchViewResponse']>(
    'GET',
    reader === 'me' ? `/v1/me/batches/${enc(seat)}/teaching` : `/v1/children/${enc(seat)}/teaching`,
    { signal },
  )

export const readProgress = (reader: Reader, seat: string, signal?: AbortSignal) =>
  request<Schemas['ProgressEntryResponse'][]>(
    'GET',
    reader === 'me'
      ? `/v1/me/enrollments/${enc(seat)}/progress`
      : `/v1/children/${enc(seat)}/progress`,
    { signal },
  )

/** The guardian's "latest run" sentence. There is no student endpoint for it. */
export const readProgressSummary = (seat: string, signal?: AbortSignal) =>
  request<Schemas['ProgressSummaryResponse'] | null>(
    'GET',
    `/v1/children/${enc(seat)}/progress/summary`,
    { signal },
  )

export const readFamilyCalendar = (
  reader: Reader,
  seat: string,
  year: number,
  month: number,
  signal?: AbortSignal,
) =>
  request<Schemas['MonthViewResponse']>(
    'GET',
    reader === 'me'
      ? `/v1/me/enrollments/${enc(seat)}/calendar`
      : `/v1/children/${enc(seat)}/calendar`,
    { signal, query: { year, month } },
  )

export const readFamilyExam = (
  reader: Reader,
  seat: string,
  examId: string,
  signal?: AbortSignal,
) =>
  request<Schemas['FamilyExamResponse']>(
    'GET',
    reader === 'me'
      ? `/v1/me/enrollments/${enc(seat)}/exams/${enc(examId)}`
      : `/v1/children/${enc(seat)}/exams/${enc(examId)}`,
    { signal },
  )

export const readMarksheet = (reader: Reader, seat: string, examId: string, signal?: AbortSignal) =>
  request<Schemas['PublishedMarksheetResponse'] | Schemas['SuppressedMarksheetResponse']>(
    'GET',
    reader === 'me'
      ? `/v1/me/enrollments/${enc(seat)}/exams/${enc(examId)}/marksheet`
      : `/v1/children/${enc(seat)}/exams/${enc(examId)}/marksheet`,
    { signal },
  )
