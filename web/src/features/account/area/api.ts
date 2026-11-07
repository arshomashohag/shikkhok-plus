/**
 * The account area's API calls: inbox, profile, deletion, children.
 * Typed from the committed OpenAPI schema.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const enc = encodeURIComponent

export const readInbox = (signal?: AbortSignal) =>
  request<Schemas['InboxResponse']>('GET', '/v1/me/notifications', { signal })

export const readInboxItem = (notificationId: string, signal?: AbortSignal) =>
  request<Schemas['NotificationDetailResponse']>(
    'GET',
    `/v1/me/notifications/${enc(notificationId)}`,
    { signal },
  )

export const markRead = (notificationId: string) =>
  request<unknown>('POST', `/v1/me/notifications/${enc(notificationId)}/read`)

export const markAllRead = () => request<unknown>('POST', '/v1/me/notifications/read')

export const readProfile = (signal?: AbortSignal) =>
  request<Schemas['MeResponse']>('GET', '/v1/me', { signal })

export const saveProfile = (body: Schemas['ProfileUpdateRequest']) =>
  request<Schemas['MeResponse']>('PATCH', '/v1/me', { body })

export const readDeletionSummary = (signal?: AbortSignal) =>
  request<Schemas['DeletionSummaryResponse']>('GET', '/v1/me/deletion-summary', { signal })

export const deleteMyAccount = () => request<Schemas['DeletionResponse']>('DELETE', '/v1/me')

export const readGuardianHome = (signal?: AbortSignal) =>
  request<Schemas['GuardianHomeResponse']>('GET', '/v1/guardian/home', { signal })
