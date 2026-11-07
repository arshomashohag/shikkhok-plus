/**
 * The API calls the students & notices area makes. Typed from the
 * committed OpenAPI schema, like api/endpoints.ts.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const enc = encodeURIComponent

export const addEnrollment = (batchId: string, body: Schemas['EnrollmentCreateRequest']) =>
  request<Schemas['RosterRowResponse']>('POST', `/v1/batches/${enc(batchId)}/enrollments`, {
    body,
  })

export const removeEnrollment = (enrollmentId: string) =>
  request<undefined>('DELETE', `/v1/enrollments/${enc(enrollmentId)}`)

export const setInactiveFrom = (enrollmentId: string, inactiveFrom: string) =>
  request<unknown>('PATCH', `/v1/enrollments/${enc(enrollmentId)}/inactive-from`, {
    body: { inactive_from: inactiveFrom },
  })

export const listAnnouncements = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['AnnouncementResponse'][]>('GET', `/v1/batches/${enc(batchId)}/announcements`, {
    signal,
  })

export const postAnnouncement = (batchId: string, body: string) =>
  request<Schemas['AnnouncementResponse']>('POST', `/v1/batches/${enc(batchId)}/announcements`, {
    body: { body },
  })

export const editAnnouncement = (announcementId: string, body: string) =>
  request<Schemas['AnnouncementResponse']>('PUT', `/v1/announcements/${enc(announcementId)}`, {
    body: { body },
  })

export const removeAnnouncement = (announcementId: string) =>
  request<undefined>('DELETE', `/v1/announcements/${enc(announcementId)}`)

export const sendReminders = (enrollmentIds: string[]) =>
  request<Schemas['ReminderResponse']>('POST', '/v1/reminders', {
    body: { enrollment_ids: enrollmentIds },
  })
