/**
 * Join requests [H5]: the calls on both sides, and the words each server
 * value is said in.
 *
 * - **The guardian's calls** act as the signed-in account alone, whatever
 *   the lens: the form's target read and its send, the caller's own list,
 *   and the withdrawal. The list and the withdrawal are never switched off,
 *   so a request sent before the switch went off can still be withdrawn.
 * - **The owner's calls** resolve the teacher lens of the current
 *   workspace: the inbox, one request, and its answer.
 *
 * **Nothing here decides anything the server owns.** Who may ask is the
 * target read's answer; which answers the owner may give is
 * `outcomes_allowed`; whether the guardian's contact is shown is whether
 * the server sent one. These tables only name the string for each value.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'

export type EnquiryTarget = Schemas['EnquiryTargetResponse']
export type EnquiryWrite = Schemas['EnquiryWrite']
export type MyEnquiry = Schemas['MyEnquiryWire']
export type OwnerEnquiry = Schemas['OwnerEnquiryWire']
export type Outcome = OwnerEnquiry['outcomes_allowed'][number]
export type InterestTarget = Schemas['InterestTargetResponse']
export type MyInterest = Schemas['MyInterestWire']
export type OwnerInterest = Schemas['OwnerInterestWire']

/** The server's limits, once stripped (`EnquiryWrite`). */
export const MAX_STUDENT_NAME = 80
export const MAX_MESSAGE = 300

const enc = encodeURIComponent
const owner = (slug: string) => `/v1/hub/owners/${enc(slug)}`
const MINE = '/v1/me/hub/enquiries'
const INBOX = '/v1/hub/enquiries'
const batchOf = (slug: string, batchId: string) => `${owner(slug)}/batches/${enc(batchId)}`
const MY_INTERESTS = '/v1/me/hub/interests'
const INTERESTS = '/v1/hub/interests'

// ------------------------------------------------------------- guardian

/** Who a request would reach, and what "share" would share. */
export const readEnquiryTarget = (slug: string, batchId: string | null, signal?: AbortSignal) =>
  request<EnquiryTarget>('GET', `${owner(slug)}/enquiry-target`, {
    query: { batch_id: batchId ?? undefined },
    signal,
  })

/** Send a request; the declaration is checked by the server and not stored. */
export const sendEnquiry = (slug: string, body: EnquiryWrite) =>
  request<MyEnquiry>('POST', `${owner(slug)}/enquiries`, { body })

/** The caller's own requests, newest first. */
export const listMyEnquiries = (signal?: AbortSignal) =>
  request<MyEnquiry[]>('GET', MINE, { signal })

/** Withdraw one of the caller's requests: it is deleted completely. */
export const withdrawEnquiry = (enquiryId: string) =>
  request<undefined>('DELETE', `${MINE}/${enc(enquiryId)}`)

// ---------------------------------------------------------------- owner

/** The owner's requests, open first, then newest, as the server orders them. */
export const listOwnerEnquiries = (signal?: AbortSignal) =>
  request<OwnerEnquiry[]>('GET', INBOX, { signal })

export const readOwnerEnquiry = (enquiryId: string, signal?: AbortSignal) =>
  request<OwnerEnquiry>('GET', `${INBOX}/${enc(enquiryId)}`, { signal })

/** Answer a request with one of its `outcomes_allowed`. */
export const closeEnquiry = (enquiryId: string, outcome: Outcome) =>
  request<OwnerEnquiry>('POST', `${INBOX}/${enc(enquiryId)}/close`, { body: { outcome } })

// ------------------------------------------------------------- interest
// A family's interest in one listed batch [0049]: the phone number on their
// account, shared with whoever runs it, with nothing typed. The family's
// own list and withdrawal are never switched off.

/** Whom an interest would reach, and whether the account has a number to share. */
export const readInterestTarget = (slug: string, batchId: string, signal?: AbortSignal) =>
  request<InterestTarget>('GET', `${batchOf(slug, batchId)}/interest-target`, { signal })

/**
 * Share the account's phone number; sharing again answers the open one.
 * The adult-guardian declaration is the server's to check, as for a request.
 */
export const shareInterest = (slug: string, batchId: string) =>
  request<MyInterest>('POST', `${batchOf(slug, batchId)}/interest`, {
    body: { declares_adult_guardian: true },
  })

/** The caller's own interests, newest first. */
export const listMyInterests = (signal?: AbortSignal) =>
  request<MyInterest[]>('GET', MY_INTERESTS, { signal })

/** Take back one of the caller's interests: it is deleted completely. */
export const withdrawInterest = (interestId: string) =>
  request<undefined>('DELETE', `${MY_INTERESTS}/${enc(interestId)}`)

/** The owner's open interests, newest first. */
export const listOwnerInterests = (signal?: AbortSignal) =>
  request<OwnerInterest[]>('GET', INTERESTS, { signal })

/** Close an interest the owner has dealt with; the family is told nothing. */
export const closeInterest = (interestId: string) =>
  request<undefined>('POST', `${INTERESTS}/${enc(interestId)}/close`)

// ---------------------------------------------------------------- words

/** Join requests are switched off: the gated reads answer this 404. */
export function isEnquiriesOff(e: unknown): boolean {
  return e instanceof ApiError && e.code === 'HUB_ENQUIRIES_OFF'
}

/** The guardian's line for the owner's answer. */
export const GUARDIAN_OUTCOME_KEY: Record<Outcome, string> = {
  added: 'hub_enquiry_outcome_added',
  not_now: 'hub_enquiry_outcome_not_now',
  call_us: 'hub_enquiry_outcome_call_us',
}

/** The owner's line for their own answer. */
export const OWNER_OUTCOME_KEY: Record<Outcome, string> = {
  added: 'hub_enquiry_answered_added',
  not_now: 'hub_enquiry_answered_not_now',
  call_us: 'hub_enquiry_answered_call_us',
}

/** The owner's buttons, in the order offered. */
export const ACTIONS: readonly { outcome: Outcome; key: string }[] = [
  { outcome: 'added', key: 'hub_enquiry_action_add' },
  { outcome: 'not_now', key: 'hub_enquiry_action_not_now' },
  { outcome: 'call_us', key: 'hub_enquiry_action_call_us' },
]

/** A class level in the listing editor's words. */
export const levelKey = (level: OwnerEnquiry['class_level']) => `web_hub_level_${level}`
