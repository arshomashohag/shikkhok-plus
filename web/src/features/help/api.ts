/**
 * The help centre's API calls, for any signed-in account. Typed from the
 * committed OpenAPI schema.
 */
import { request } from '../../api/client'
import type { Schemas } from '../../api/endpoints'

const enc = encodeURIComponent

export const listTickets = () =>
  request<Schemas['HelpTicketListResponse']>('GET', '/v1/me/help/tickets')

export const askQuestion = (body: Schemas['HelpTicketRequest']) =>
  request<Schemas['HelpTicketDetailResponse']>('POST', '/v1/me/help/tickets', { body })

/** Reading a ticket also marks support's replies on it seen. */
export const readTicket = (ticketId: string) =>
  request<Schemas['HelpTicketDetailResponse']>('GET', `/v1/me/help/tickets/${enc(ticketId)}`)

/** Replying reopens a closed ticket. */
export const replyToTicket = (ticketId: string, body: string) =>
  request<Schemas['HelpTicketDetailResponse']>(
    'POST',
    `/v1/me/help/tickets/${enc(ticketId)}/messages`,
    { body: { body } },
  )
