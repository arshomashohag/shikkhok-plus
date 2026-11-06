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

// ------------------------------------------------------------- centres [0022]

export const openCentre = (body: Schemas['CentreCreateRequest']) =>
  request<Schemas['CentreResponse']>('POST', '/v1/centres', { body })

export const listMembers = () => request<Schemas['MemberResponse'][]>('GET', '/v1/centre/members')

export const inviteMember = (body: Schemas['MemberInviteRequest']) =>
  request<Schemas['MemberResponse']>('POST', '/v1/centre/members', { body })

export const revokeMember = (memberId: string) =>
  request<undefined>('POST', `/v1/centre/members/${enc(memberId)}/revoke`)

export const listStaff = () => request<Schemas['StaffResponse'][]>('GET', '/v1/centre/staff')

export const inviteStaffTeacher = (body: Schemas['StaffTeacherRequest']) =>
  request<Schemas['StaffResponse']>('POST', '/v1/centre/staff/teachers', { body })

export const addOtherStaff = (body: Schemas['StaffOtherRequest']) =>
  request<Schemas['StaffResponse']>('POST', '/v1/centre/staff', { body })

export const updateStaff = (staffId: string, body: Schemas['StaffUpdateRequest']) =>
  request<Schemas['StaffResponse']>('PATCH', `/v1/centre/staff/${enc(staffId)}`, { body })

export const markStaffLeft = (staffId: string, leftOn: string | null) =>
  request<Schemas['StaffResponse']>('POST', `/v1/centre/staff/${enc(staffId)}/leave`, {
    body: leftOn ? { left_on: leftOn } : {},
  })

export const listRooms = () => request<Schemas['RoomResponse'][]>('GET', '/v1/centre/rooms')

export const addRoom = (name: string) =>
  request<Schemas['RoomResponse']>('POST', '/v1/centre/rooms', { body: { name } })

export const updateRoom = (roomId: string, body: Schemas['RoomUpdateRequest']) =>
  request<Schemas['RoomResponse']>('PATCH', `/v1/centre/rooms/${enc(roomId)}`, { body })

export const readTimetable = (from: string, to: string) =>
  request<Schemas['TimetableClassResponse'][]>('GET', '/v1/centre/timetable', {
    query: { from, to },
  })

export const assignClass = (sessionId: string, body: Schemas['AssignmentRequest']) =>
  request<Schemas['TimetableClassResponse']>('POST', `/v1/sessions/${enc(sessionId)}/assignment`, {
    body,
  })

export const swapClasses = (first: string, second: string) =>
  request<Schemas['TimetableClassResponse'][]>('POST', '/v1/centre/sessions/swap', {
    body: { first_session_id: first, second_session_id: second },
  })

export const listMemberships = () =>
  request<Schemas['MembershipResponse'][]>('GET', '/v1/memberships')

export const acceptMembership = (memberId: string) =>
  request<Schemas['MembershipDecisionResponse']>('POST', `/v1/memberships/${enc(memberId)}/accept`)

export const declineMembership = (memberId: string) =>
  request<Schemas['MembershipDecisionResponse']>('POST', `/v1/memberships/${enc(memberId)}/decline`)

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
