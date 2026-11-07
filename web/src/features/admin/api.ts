/**
 * The platform administrators' API calls. The server answers them only
 * for an account on its administrator allowlist and refuses everyone
 * else with a 403; it also decides what an administrator may see, so
 * students and guardians arrive as counts or as a role and an opaque
 * reference, never by name or number [TC-14] [D-6].
 */
import { request } from '../../api/client'
import type { Schemas } from '../../api/endpoints'
import type { HelpStatus } from '../help/mappers'

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
