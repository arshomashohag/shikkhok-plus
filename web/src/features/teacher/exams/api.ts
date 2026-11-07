/**
 * The exam and marks calls (teacher lens). Typed from openapi.json.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const id = encodeURIComponent

export const listExams = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['ExamListItemResponse'][]>('GET', `/v1/batches/${id(batchId)}/exams`, { signal })

/** The batch row, for its subject options: there is no single-batch read. */
export const readBatch = async (batchId: string, signal?: AbortSignal) =>
  (await request<Schemas['BatchResponse'][]>('GET', '/v1/batches', { signal })).find(
    (b) => b.id === batchId,
  ) ?? null

export const createExam = (batchId: string, body: Schemas['ExamCreateRequest']) =>
  request<Schemas['ExamResponse']>('POST', `/v1/batches/${id(batchId)}/exams`, { body })

export const updateExam = (examId: string, body: Schemas['ExamUpdateRequest']) =>
  request<Schemas['ExamResponse']>('PUT', `/v1/exams/${id(examId)}`, { body })

/** Cancel an exam whose results are not published; every family is told. */
export const cancelExam = (examId: string, body: Schemas['ExamCancelRequest']) =>
  request<Schemas['ExamResponse']>('POST', `/v1/exams/${id(examId)}/cancel`, { body })

export const readResults = (examId: string, signal?: AbortSignal) =>
  request<Schemas['ExamResultsResponse']>('GET', `/v1/exams/${id(examId)}/results`, { signal })

export const writeMark = (examId: string, body: Schemas['MarkWriteRequest']) =>
  request<undefined>('POST', `/v1/exams/${id(examId)}/marks`, { body })

export const publishExam = (examId: string) =>
  request<undefined>('POST', `/v1/exams/${id(examId)}/publish`)

export const readMarkHistory = (examId: string, enrollmentId: string, signal?: AbortSignal) =>
  request<Schemas['CorrectionEntryResponse'][]>(
    'GET',
    `/v1/exams/${id(examId)}/marks/${id(enrollmentId)}/history`,
    { signal },
  )

export const readExam = (examId: string, signal?: AbortSignal) =>
  request<Schemas['ExamResponse']>('GET', `/v1/exams/${id(examId)}`, { signal })

/** Name, change or clear the centre member who marks this exam. */
export const setExaminer = (examId: string, examinerMemberId: string | null) =>
  request<Schemas['ExamResponse']>('PUT', `/v1/exams/${id(examId)}/examiner`, {
    body: { examiner_member_id: examinerMemberId },
  })
