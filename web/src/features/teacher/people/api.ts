/**
 * The API calls for a teacher's students, apart from any batch [0018].
 * Typed from the committed OpenAPI schema, like api/endpoints.ts.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const enc = encodeURIComponent

/** Which students to list. The SERVER filters; the client only asks. */
export type StudentFilter =
  | { kind: 'all' }
  | { kind: 'unassigned' }
  | { kind: 'in-batch'; batchId: string }
  | { kind: 'not-in-batch'; batchId: string }

export function studentsQuery(filter: StudentFilter, query: string): string {
  const q = new URLSearchParams()
  if (filter.kind === 'unassigned') q.set('unassigned', 'true')
  if (filter.kind === 'in-batch') q.set('batch_id', filter.batchId)
  if (filter.kind === 'not-in-batch') q.set('exclude_batch_id', filter.batchId)
  if (query.trim()) q.set('q', query.trim())
  const s = q.toString()
  return s ? `/v1/students?${s}` : '/v1/students'
}

export const listStudents = (filter: StudentFilter, query = '') =>
  request<Schemas['StudentResponse'][]>('GET', studentsQuery(filter, query))

export const readStudent = (studentId: string) =>
  request<Schemas['StudentResponse']>('GET', `/v1/students/${enc(studentId)}`)

export const createStudent = (body: Schemas['StudentCreateRequest']) =>
  request<Schemas['StudentResponse']>('POST', '/v1/students', { body })

export const updateStudent = (studentId: string, body: Schemas['StudentUpdateRequest']) =>
  request<Schemas['StudentResponse']>('PATCH', `/v1/students/${enc(studentId)}`, { body })

export const removeStudent = (studentId: string) =>
  request<undefined>('DELETE', `/v1/students/${enc(studentId)}`)

export const enrollStudent = (studentId: string, batchId: string) =>
  request<Schemas['StudentResponse']>('POST', `/v1/students/${enc(studentId)}/enrollments`, {
    body: { batch_id: batchId },
  })

export const addStudentsToBatch = (batchId: string, studentIds: string[]) =>
  request<Schemas['AddStudentsResponse']>('POST', `/v1/batches/${enc(batchId)}/students`, {
    body: { student_ids: studentIds },
  })
