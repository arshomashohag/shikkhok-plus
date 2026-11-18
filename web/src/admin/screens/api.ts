/**
 * The platform administrators' API calls, on the admin host with the
 * admin token (`../client.ts`). The server answers them only for an
 * admin session, from an allowlisted number with a confirmed
 * authenticator, and refuses everyone else; it also decides what an
 * administrator may see, so students and guardians arrive as counts or
 * as a role and an opaque reference, never by name or number [TC-14] [D-6].
 */
import { adminRequest as request } from '../client'
import type { Schemas } from '../../api/endpoints'
import type { HelpStatus } from '../../features/help/mappers'

const enc = encodeURIComponent

export const readOverview = () =>
  request<Schemas['AdminOverviewResponse']>('GET', '/v1/admin/overview')

export const readWorkspaces = () =>
  request<Schemas['AdminWorkspacesResponse']>('GET', '/v1/admin/teachers')

export const readRequesters = () =>
  request<Schemas['AdminRequestersResponse']>('GET', '/v1/admin/help/requesters')

/** Filtered by the server: a status, one person's reference, or both. */
export const readTickets = (filter: { status?: HelpStatus; ref?: string }) =>
  request<Schemas['AdminTicketListResponse']>('GET', '/v1/admin/help/tickets', {
    query: { status: filter.status, ref: filter.ref },
  })

export const readAdminTicket = (ticketId: string) =>
  request<Schemas['AdminTicketDetailResponse']>('GET', `/v1/admin/help/tickets/${enc(ticketId)}`)

/** A support reply; the ticket becomes answered. */
export const replyAsSupport = (ticketId: string, body: string) =>
  request<Schemas['AdminTicketDetailResponse']>(
    'POST',
    `/v1/admin/help/tickets/${enc(ticketId)}/messages`,
    { body: { body } },
  )

export const setTicketStatus = (ticketId: string, status: 'open' | 'closed') =>
  request<Schemas['AdminTicketDetailResponse']>(
    'PUT',
    `/v1/admin/help/tickets/${enc(ticketId)}/status`,
    { body: { status } },
  )

/** The moderation queue, oldest first: open reports, suspended listings, or photos. */
export const readHubQueue = (kind: Schemas['AdminHubQueueResponse']['kind']) =>
  request<Schemas['AdminHubQueueResponse']>('GET', '/v1/admin/hub/queue', { query: { kind } })

export const decideHubReport = (reportId: string, decision: 'upheld' | 'dismissed') =>
  request<Schemas['AdminHubReportDecided']>(
    'POST',
    `/v1/admin/hub/reports/${enc(reportId)}/decision`,
    { body: { decision } },
  )

export const setHubSuspension = (ownerId: string, body: Schemas['AdminHubSuspensionRequest']) =>
  request<Schemas['AdminHubSuspensionState']>(
    'PUT',
    `/v1/admin/hub/owners/${enc(ownerId)}/suspension`,
    { body },
  )

/** One photo to review, with five-minute signed previews of its variants. */
export const readHubMedia = (mediaId: string) =>
  request<Schemas['AdminHubMediaDetail']>('GET', `/v1/admin/hub/media/${enc(mediaId)}`)

export const decideHubMedia = (mediaId: string, body: Schemas['AdminHubMediaDecisionRequest']) =>
  request<Schemas['AdminHubMediaDecided']>('POST', `/v1/admin/hub/media/${enc(mediaId)}/decision`, {
    body,
  })
