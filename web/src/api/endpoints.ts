/**
 * The API calls this client makes, typed from the committed OpenAPI
 * schema (`schema.d.ts`, generated; `npm run gen:api`). A contract change
 * that breaks a screen fails `tsc`, not a user.
 *
 * Responses are returned as the wire types. Money fields are still
 * strings here; each feature's mapper turns them into {@link Money} and
 * fails loudly on anything else.
 */
import { request } from './client'
import type { components } from './schema'

export type Schemas = components['schemas']

// ----------------------------------------------------------------- auth

export const issueCode = (phone: string) =>
  request<Schemas['IssueResponse']>('POST', '/v1/auth/otp', { body: { phone }, anonymous: true })

export const verifyCode = (phone: string, code: string) =>
  request<Schemas['TokenResponse']>('POST', '/v1/auth/verify', {
    body: { phone, code },
    anonymous: true,
  })

export const signUp = (body: Schemas['SignupRequest']) =>
  request<Schemas['SignupResponse']>('POST', '/v1/accounts', { body, anonymous: true })

// ------------------------------------------------------------------- me

export const readMe = () => request<Schemas['MeResponse']>('GET', '/v1/me')

export const listInvitations = () =>
  request<Schemas['InvitationResponse'][]>('GET', '/v1/invitations')

export const acceptInvitation = (enrollmentId: string) =>
  request<unknown>('POST', `/v1/invitations/${enc(enrollmentId)}/accept`)

export const declineInvitation = (enrollmentId: string) =>
  request<unknown>('POST', `/v1/invitations/${enc(enrollmentId)}/decline`)

// -------------------------------------------------------------- teacher

export const readToday = () => request<Schemas['TodayResponse']>('GET', '/v1/me/today')

export const listBatches = () => request<Schemas['BatchResponse'][]>('GET', '/v1/batches')

export const createBatch = (body: Schemas['BatchCreateRequest']) =>
  request<Schemas['BatchResponse']>('POST', '/v1/batches', { body })

export const readRoster = (batchId: string) =>
  request<Schemas['RosterRowResponse'][]>('GET', `/v1/batches/${enc(batchId)}/roster`)

export const readBatchFees = (batchId: string) =>
  request<Schemas['BatchFeesResponse']>('GET', `/v1/batches/${enc(batchId)}/fees`)

export const readDues = () => request<Schemas['DuesResponse']>('GET', '/v1/me/dues')

export const readQueue = () =>
  request<Schemas['VerificationQueueResponse']>('GET', '/v1/claims/queue')

export const approvePayment = (submissionId: string, body: Schemas['PaymentApprovalRequest']) =>
  request<Schemas['PaymentReviewResponse']>('POST', `/v1/payments/${enc(submissionId)}/approval`, {
    body,
  })

export const rejectPayment = (submissionId: string, body: Schemas['PaymentRejectionRequest']) =>
  request<Schemas['PaymentReviewResponse']>('POST', `/v1/payments/${enc(submissionId)}/rejection`, {
    body,
  })

// -------------------------------------------------------------- student

export const listMyBatches = () =>
  request<Schemas['StudentBatchResponse'][]>('GET', '/v1/me/enrollments')

// ------------------------------------------------------------- guardian

export const readGuardianHome = () =>
  request<Schemas['GuardianHomeResponse']>('GET', '/v1/guardian/home')

function enc(segment: string): string {
  return encodeURIComponent(segment)
}
