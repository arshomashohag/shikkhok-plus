/**
 * Help-centre responses → what the screens draw. Pure, and the test
 * target. A ticket's status and whether it has a new reply are the
 * server's to say; the client only chooses words and a chip for them.
 */
import type { Schemas } from '../../api/endpoints'

export type HelpStatus = 'open' | 'answered' | 'closed'

/** What the person who asked sees for each status. */
export const STATUS_KEY: Record<HelpStatus, string> = {
  open: 'help_status_open',
  answered: 'help_status_answered',
  closed: 'help_status_closed',
}

/** The chip style for each status: waiting, answered, done. */
export const STATUS_CHIP: Record<HelpStatus, string> = {
  open: 'chip-verifying',
  answered: 'chip-paid',
  closed: 'chip-neutral',
}

export interface HelpTicket {
  id: string
  subject: string
  status: HelpStatus
  createdAt: string
  updatedAt: string
  /** Support replied since the person last opened it. */
  newReply: boolean
  preview: string
}

export interface HelpMessage {
  id: string
  fromSupport: boolean
  body: string
  sentAt: string
}

export interface HelpList {
  tickets: HelpTicket[]
  newReplies: number
}

export interface HelpThread {
  ticket: HelpTicket
  messages: HelpMessage[]
}

export function mapTicket(t: Schemas['HelpTicketResponse']): HelpTicket {
  return {
    id: t.ticket_id,
    subject: t.subject,
    status: t.status,
    createdAt: t.created_at,
    updatedAt: t.updated_at,
    newReply: t.has_new_reply,
    preview: t.preview,
  }
}

export function mapMessage(m: Schemas['HelpMessageResponse']): HelpMessage {
  return {
    id: m.message_id,
    fromSupport: m.author === 'support',
    body: m.body,
    sentAt: m.created_at,
  }
}

export function mapList(r: Schemas['HelpTicketListResponse']): HelpList {
  return { tickets: r.tickets.map(mapTicket), newReplies: r.new_replies }
}

export function mapThread(r: Schemas['HelpTicketDetailResponse']): HelpThread {
  return { ticket: mapTicket(r.ticket), messages: r.messages.map(mapMessage) }
}

// ------------------------------------------------------------------ form

/** The server's limits, from the request schemas. */
export const SUBJECT_MAX = 120
export const BODY_MAX = 4000

/** Length as the server counts it: code points, after trimming. */
export function textLength(value: string): number {
  return [...value.trim()].length
}

/**
 * What is wrong with a field, if anything. Format only: the server
 * decides everything else, including how many questions may be asked.
 */
export function fieldProblem(value: string, max: number): 'required' | 'too_long' | null {
  const length = textLength(value)
  if (length === 0) return 'required'
  if (length > max) return 'too_long'
  return null
}

/** The request body for a new question, trimmed as the server stores it. */
export function newQuestion(subject: string, body: string): Schemas['HelpTicketRequest'] {
  return { subject: subject.trim(), body: body.trim() }
}
