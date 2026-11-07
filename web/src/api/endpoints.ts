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

export const readMe = (signal?: AbortSignal) =>
  request<Schemas['MeResponse']>('GET', '/v1/me', { signal })

export const listInvitations = (signal?: AbortSignal) =>
  request<Schemas['InvitationResponse'][]>('GET', '/v1/invitations', { signal })

export const acceptInvitation = (enrollmentId: string) =>
  request<unknown>('POST', `/v1/invitations/${enc(enrollmentId)}/accept`)

export const declineInvitation = (enrollmentId: string) =>
  request<unknown>('POST', `/v1/invitations/${enc(enrollmentId)}/decline`)

// ------------------------------------------------------------- centres [0022]

export const openCentre = (body: Schemas['CentreCreateRequest']) =>
  request<Schemas['CentreResponse']>('POST', '/v1/centres', { body })

export const listMembers = (signal?: AbortSignal) =>
  request<Schemas['MemberResponse'][]>('GET', '/v1/centre/members', { signal })

export const inviteMember = (body: Schemas['MemberInviteRequest']) =>
  request<Schemas['MemberResponse']>('POST', '/v1/centre/members', { body })

export const revokeMember = (memberId: string) =>
  request<undefined>('POST', `/v1/centre/members/${enc(memberId)}/revoke`)

export const listStaff = (signal?: AbortSignal) =>
  request<Schemas['StaffResponse'][]>('GET', '/v1/centre/staff', { signal })

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

export const listRooms = (signal?: AbortSignal) =>
  request<Schemas['RoomResponse'][]>('GET', '/v1/centre/rooms', { signal })

export const addRoom = (name: string) =>
  request<Schemas['RoomResponse']>('POST', '/v1/centre/rooms', { body: { name } })

export const updateRoom = (roomId: string, body: Schemas['RoomUpdateRequest']) =>
  request<Schemas['RoomResponse']>('PATCH', `/v1/centre/rooms/${enc(roomId)}`, { body })

export const readTimetable = (from: string, to: string, signal?: AbortSignal) =>
  request<Schemas['TimetableClassResponse'][]>('GET', '/v1/centre/timetable', {
    signal,
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

export const listMyClasses = (from: string, to: string, signal?: AbortSignal) =>
  request<Schemas['MyClassResponse'][]>('GET', '/v1/me/classes', { signal, query: { from, to } })

export const readClassRoster = (sessionId: string, signal?: AbortSignal) =>
  request<Schemas['ClassRosterResponse']>('GET', `/v1/me/classes/${enc(sessionId)}/attendance`, {
    signal,
  })

export const submitClassRoster = (sessionId: string, body: Schemas['AttendanceSubmitRequest']) =>
  request<Schemas['AttendanceSubmitResponse']>(
    'POST',
    `/v1/me/classes/${enc(sessionId)}/attendance`,
    { body },
  )

export const writeClassTopic = (sessionId: string, body: Schemas['TopicWriteRequest']) =>
  request<Schemas['TopicWriteResponse']>('PUT', `/v1/me/classes/${enc(sessionId)}/topic`, {
    body,
  })

export const listMyExams = (signal?: AbortSignal) =>
  request<Schemas['MyExamResponse'][]>('GET', '/v1/me/exams', { signal })

export const readMyExamResults = (examId: string, signal?: AbortSignal) =>
  request<Schemas['ExaminerResultsResponse']>('GET', `/v1/me/exams/${enc(examId)}/results`, {
    signal,
  })

export const writeMyExamMark = (examId: string, body: Schemas['MarkWriteRequest']) =>
  request<undefined>('POST', `/v1/me/exams/${enc(examId)}/marks`, { body })

export const publishMyExam = (examId: string) =>
  request<undefined>('POST', `/v1/me/exams/${enc(examId)}/publish`)

export const readPayroll = (period: string, signal?: AbortSignal) =>
  request<Schemas['SalaryLineResponse'][]>('GET', `/v1/centre/payroll/${enc(period)}`, { signal })

export const drawPayroll = (period: string) =>
  request<Schemas['SalaryLineResponse'][]>('POST', `/v1/centre/payroll/${enc(period)}/lines`)

export const addSalaryAdjustment = (lineId: string, body: Schemas['AdjustmentRequest']) =>
  request<Schemas['SalaryLineResponse']>(
    'POST',
    `/v1/centre/payroll/lines/${enc(lineId)}/adjustments`,
    { body },
  )

export const removeSalaryAdjustment = (lineId: string, adjustmentId: string) =>
  request<Schemas['SalaryLineResponse']>(
    'DELETE',
    `/v1/centre/payroll/lines/${enc(lineId)}/adjustments/${enc(adjustmentId)}`,
  )

export const approveSalary = (lineId: string) =>
  request<Schemas['SalaryLineResponse']>('POST', `/v1/centre/payroll/lines/${enc(lineId)}/approve`)

export const paySalary = (lineId: string, body: Schemas['SalaryPaymentRequest']) =>
  request<Schemas['SalaryLineResponse']>(
    'POST',
    `/v1/centre/payroll/lines/${enc(lineId)}/payments`,
    { body },
  )

export const readMyPay = (signal?: AbortSignal) =>
  request<Schemas['SalaryLineResponse'][]>('GET', '/v1/me/pay', { signal })

export const listMemberships = (signal?: AbortSignal) =>
  request<Schemas['MembershipResponse'][]>('GET', '/v1/memberships', { signal })

export const acceptMembership = (memberId: string) =>
  request<Schemas['MembershipDecisionResponse']>('POST', `/v1/memberships/${enc(memberId)}/accept`)

export const declineMembership = (memberId: string) =>
  request<Schemas['MembershipDecisionResponse']>('POST', `/v1/memberships/${enc(memberId)}/decline`)

// -------------------------------------------------------------- teacher

export const readToday = (signal?: AbortSignal) =>
  request<Schemas['TodayResponse']>('GET', '/v1/me/today', { signal })

export const listBatches = (signal?: AbortSignal) =>
  request<Schemas['BatchResponse'][]>('GET', '/v1/batches', { signal })

export const createBatch = (body: Schemas['BatchCreateRequest']) =>
  request<Schemas['BatchResponse']>('POST', '/v1/batches', { body })

export const readRoster = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['RosterRowResponse'][]>('GET', `/v1/batches/${enc(batchId)}/roster`, { signal })

export const readBatchFees = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['BatchFeesResponse']>('GET', `/v1/batches/${enc(batchId)}/fees`, { signal })

export const readDues = (signal?: AbortSignal) =>
  request<Schemas['DuesResponse']>('GET', '/v1/me/dues', { signal })

export const readQueue = (signal?: AbortSignal) =>
  request<Schemas['VerificationQueueResponse']>('GET', '/v1/claims/queue', { signal })

export const approvePayment = (submissionId: string, body: Schemas['PaymentApprovalRequest']) =>
  request<Schemas['PaymentReviewResponse']>('POST', `/v1/payments/${enc(submissionId)}/approval`, {
    body,
  })

export const rejectPayment = (submissionId: string, body: Schemas['PaymentRejectionRequest']) =>
  request<Schemas['PaymentReviewResponse']>('POST', `/v1/payments/${enc(submissionId)}/rejection`, {
    body,
  })

// -------------------------------------------------------------- student

export const listMyBatches = (signal?: AbortSignal) =>
  request<Schemas['StudentBatchResponse'][]>('GET', '/v1/me/enrollments', { signal })

// ------------------------------------------------------------- guardian

export const readGuardianHome = (signal?: AbortSignal) =>
  request<Schemas['GuardianHomeResponse']>('GET', '/v1/guardian/home', { signal })

function enc(segment: string): string {
  return encodeURIComponent(segment)
}
