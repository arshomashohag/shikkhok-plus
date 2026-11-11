/**
 * The classes area's API calls: the month calendar, one class, its
 * attendance and topic, cancelling and moving it, the weekly schedule and
 * the batch's own fields.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const enc = encodeURIComponent

export const readCalendar = (batchId: string, year: number, month: number, signal?: AbortSignal) =>
  request<Schemas['MonthViewResponse']>('GET', `/v1/batches/${enc(batchId)}/calendar`, {
    signal,
    query: { year, month },
  })

export const readBatchSessions = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['SessionResponse'][]>('GET', `/v1/batches/${enc(batchId)}/sessions`, { signal })

export const createSession = (batchId: string, body: Schemas['SessionCreateRequest']) =>
  request<Schemas['SessionResponse']>('POST', `/v1/batches/${enc(batchId)}/sessions`, { body })

export const readSession = (sessionId: string, signal?: AbortSignal) =>
  request<Schemas['SessionResponse']>('GET', `/v1/sessions/${enc(sessionId)}`, { signal })

export const readAttendance = (sessionId: string, signal?: AbortSignal) =>
  request<Schemas['SessionRosterResponse']>('GET', `/v1/sessions/${enc(sessionId)}/attendance`, {
    signal,
  })

export const submitAttendance = (sessionId: string, body: Schemas['AttendanceSubmitRequest']) =>
  request<Schemas['AttendanceSubmitResponse']>(
    'POST',
    `/v1/sessions/${enc(sessionId)}/attendance`,
    { body },
  )

export const writeTopic = (sessionId: string, body: Schemas['TopicWriteRequest']) =>
  request<Schemas['TopicWriteResponse']>('PUT', `/v1/sessions/${enc(sessionId)}/topic`, { body })

export const setSessionSubject = (sessionId: string, batchSubjectId: string | null) =>
  request<Schemas['SessionResponse']>('PUT', `/v1/sessions/${enc(sessionId)}/subject`, {
    body: { batch_subject_id: batchSubjectId },
  })

export const cancelSession = (sessionId: string) =>
  request<Schemas['SessionResponse']>('POST', `/v1/sessions/${enc(sessionId)}/cancellation`)

export const rescheduleSession = (sessionId: string, body: Schemas['SessionRescheduleRequest']) =>
  request<Schemas['SessionResponse']>('PUT', `/v1/sessions/${enc(sessionId)}/schedule`, { body })

export const readSchedule = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['ScheduleSlotWire'][]>('GET', `/v1/batches/${enc(batchId)}/schedule`, { signal })

export const writeSchedule = (batchId: string, slots: Schemas['ScheduleSlotWire'][]) =>
  request<Schemas['ScheduleSlotWire'][]>('PUT', `/v1/batches/${enc(batchId)}/schedule`, {
    body: { slots },
  })

export const updateBatch = (batchId: string, body: Schemas['BatchUpdateRequest']) =>
  request<Schemas['BatchResponse']>('PATCH', `/v1/batches/${enc(batchId)}`, { body })

/**
 * Whether families see this batch's marksheets [BR5.4]. The one route
 * that writes it; the answer is the value now in force.
 */
export const setMarksheetVisibility = (batchId: string, visible: boolean) =>
  request<Schemas['MarksheetToggleRequest']>(
    'PUT',
    `/v1/batches/${enc(batchId)}/marksheet-visibility`,
    { body: { visible } },
  )

/** A fresh id for one write. A retry of the same write reuses it, so the server replays. */
export function mutationId(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c?.randomUUID) return c.randomUUID()
  // RFC 4122 v4 from getRandomValues, for engines without randomUUID.
  const b = new Uint8Array(16)
  c?.getRandomValues(b)
  b[6] = ((b[6] ?? 0) & 0x0f) | 0x40
  b[8] = ((b[8] ?? 0) & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
