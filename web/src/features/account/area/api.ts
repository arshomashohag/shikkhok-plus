/**
 * The account area's API calls: inbox, profile, deletion, children.
 * Typed from the committed OpenAPI schema.
 */
import { request } from '../../../api/client'
import type { Me, Schemas } from '../../../api/endpoints'
import { INBOX_KINDS } from './mappers'

const enc = encodeURIComponent

/**
 * `kind=…&kind=…`: the kinds this client can draw. The server reads the
 * items and counts `unread` over these only (PO-10), so the badge never
 * counts a message this screen would drop.
 */
export const KINDS_QUERY = INBOX_KINDS.map((k) => `kind=${enc(k)}`).join('&')

export const readInbox = (signal?: AbortSignal) =>
  request<Schemas['InboxResponse']>('GET', `/v1/me/notifications?${KINDS_QUERY}`, { signal })

export const readInboxItem = (notificationId: string, signal?: AbortSignal) =>
  request<Schemas['NotificationDetailResponse']>(
    'GET',
    `/v1/me/notifications/${enc(notificationId)}`,
    { signal },
  )

export const markRead = (notificationId: string) =>
  request<unknown>('POST', `/v1/me/notifications/${enc(notificationId)}/read`)

export const markAllRead = () =>
  request<unknown>('POST', `/v1/me/notifications/read?${KINDS_QUERY}`)

export const readProfile = (signal?: AbortSignal) => request<Me>('GET', '/v1/me', { signal })

export const saveProfile = (body: Schemas['ProfileUpdateRequest']) =>
  request<Me>('PATCH', '/v1/me', { body })

export const readDeletionSummary = (signal?: AbortSignal) =>
  request<Schemas['DeletionSummaryResponse']>('GET', '/v1/me/deletion-summary', { signal })

export const deleteMyAccount = () => request<Schemas['DeletionResponse']>('DELETE', '/v1/me')

export const readGuardianHome = (signal?: AbortSignal) =>
  request<Schemas['GuardianHomeResponse']>('GET', '/v1/guardian/home', { signal })
