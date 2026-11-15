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
//
// Sign-up with a username and a phone OR email; sign-in by any of the
// three; passwords [0032]. Usernames and passwords go in JSON bodies,
// never in a URL.

/** Exactly one of a phone number or an email address. */
export type Identifier = { phone: string } | { email: string }

/** `/verify` and `/password` answers: tokens, an MFA challenge, or a setup token. */
export type VerifyResponse = Schemas['VerifyResponse']

/** `/v1/me`: `phone` may be null (email-only account). */
export type Me = Schemas['MeResponse']

export type SignupRequest = Omit<Schemas['SignupRequest'], 'phone' | 'email'> & Identifier

/** Send a one-time code to a phone (SMS) or an email address. */
export const issueCode = (identifier: Identifier) =>
  request<Schemas['IssueResponse']>('POST', '/v1/auth/otp', {
    body: identifier,
    anonymous: true,
  })

/**
 * Spend the one-time code. **Never yields tokens**: the answer carries a
 * `password_setup_token` for {@link setUpPassword}, and says whether the
 * account will also need its authenticator code there.
 *
 * `username` is sent only on the Replace retry, after a 409
 * `account.username.unavailable`, with the same code [FR2.2].
 */
export const verifyCode = (identifier: Identifier, code: string, username?: string) =>
  request<VerifyResponse>('POST', '/v1/auth/verify', {
    body: username === undefined ? { ...identifier, code } : { ...identifier, code, username },
    anonymous: true,
  })

/**
 * Finish the code flow by choosing a password; the answer is the token
 * pair. Anonymous: a 401 here (`auth.password.setup_expired`) means the
 * setup token lapsed, never that a session ended.
 */
export const setUpPassword = (body: {
  token: string
  password: string
  code?: string | null
  recovery_code?: string | null
}) =>
  request<Schemas['TokenResponse']>('POST', '/v1/auth/password/setup', {
    body,
    anonymous: true,
  })

/**
 * Sign in with a password. The answer is the token pair, or an MFA
 * challenge for {@link finishSignIn}.
 *
 * `login` is a username, a phone or an email, exactly as typed and
 * trimmed: the client never classifies it, so the request has no
 * `phone` or `email` key that would say which [FR4.1] [NFR1.2].
 */
export const signInWithPassword = (login: string, password: string) =>
  request<VerifyResponse>('POST', '/v1/auth/password', {
    body: { login, password },
    anonymous: true,
  })

/**
 * Whether a username could be had, for the sign-up and Replace hints
 * [FR3.1]. Anonymous; the name goes in the body, never the URL [NFR3.1].
 */
export const checkUsername = (username: string, signal?: AbortSignal) =>
  request<Schemas['UsernameAvailabilityResponse']>('POST', '/v1/accounts/username-availability', {
    body: { username },
    anonymous: true,
    signal,
  })

/**
 * The same question asked as the signed-in account, so a name it released
 * reads as available to it (the gate and rename) [FR3.1].
 */
export const checkMyUsername = (username: string, signal?: AbortSignal) =>
  request<Schemas['UsernameAvailabilityResponse']>('POST', '/v1/me/username-availability', {
    body: { username },
    signal,
  })

/**
 * The second step: the challenge and one authenticator or recovery code.
 * Anonymous, like `/password`: there is no session yet, so a 401 here (the
 * challenge lapsed) never reaches token renewal or sign-out.
 */
export const finishSignIn = (
  challenge: string,
  proof: { code: string } | { recovery_code: string },
) =>
  request<Schemas['TokenResponse']>('POST', '/v1/auth/mfa', {
    body: { challenge, ...proof },
    anonymous: true,
  })

export const signUp = (body: SignupRequest) =>
  request<Schemas['SignupResponse']>('POST', '/v1/accounts', { body, anonymous: true })

/**
 * Whether a teacher already recorded this number or address [BR2.3,
 * BR4.5] [FR6.7]. Public and counted against sign-up's own ceilings, so
 * the form asks once per complete value and never while it is still
 * being typed.
 *
 * The one route here that carries a typed contact in its URL: C2 defines
 * it with a query parameter, and the route is U2's [NFR3.1 exception].
 */
export const lookupAlreadyAdded = (identifier: Identifier) =>
  request<Schemas['AlreadyAddedResponse']>('GET', '/v1/accounts/already-added', {
    query: 'phone' in identifier ? { phone: identifier.phone } : { email: identifier.email },
    anonymous: true,
  })

// ------------------------------------------------------------------- me

export const readMe = (signal?: AbortSignal) => request<Me>('GET', '/v1/me', { signal })

/**
 * Choose (`password` null) or change the signed-in account's username
 * [FR5.4] [FR7.1]. The name goes in the body, never the URL [NFR3.1];
 * the first choice sends no password key at all.
 */
export const setMyUsername = (username: string, password: string | null) =>
  request<Schemas['UsernameChangeResponse']>('PUT', '/v1/me/username', {
    body: password === null ? { username } : { username, password },
  })

/**
 * Set a first password (`current` null) or change it. Every session,
 * this one included, ends: the answer is the new pair to store.
 */
export const setMyPassword = (current: string | null, next: string) =>
  request<Schemas['TokenResponse']>('POST', '/v1/me/password', {
    body:
      current === null ? { new_password: next } : { current_password: current, new_password: next },
  })

/**
 * Send a code to a phone or email the account does not have yet, or —
 * with the current `password` — to the one replacing the account's
 * current phone or email [FR8.2] [C2]. Values in the body only [NFR3.1].
 */
export const requestContactCode = (identifier: Identifier, password?: string) =>
  request<Schemas['IssueResponse']>('POST', '/v1/me/contact', {
    body: password === undefined ? identifier : { ...identifier, password },
  })

/**
 * Remove the account's phone or email [FR8.3]. The server keeps at least
 * one (`account.contact.last_one`); the answer is the account as it now
 * stands.
 */
export const removeContact = (kind: 'phone' | 'email', password: string) =>
  request<Me>('POST', '/v1/me/contact/remove', { body: { kind, password } })

/** Spend that code; the answer is the account as it now stands. */
export const verifyContact = (identifier: Identifier, code: string) =>
  request<Me>('POST', '/v1/me/contact/verify', { body: { ...identifier, code } })

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

// ------------------------------------------------------------------ hub
//
// The owner's public listing and each batch's listing [0036]. The server
// says what is missing (`checklist`) and whether publishing is possible
// (`publishable`); the screens only show it.

export const readHubListing = (signal?: AbortSignal) =>
  request<Schemas['OwnerListingResponse']>('GET', '/v1/hub/listing', { signal })

export const saveHubListing = (body: Schemas['OwnerListingUpdateRequest']) =>
  request<Schemas['OwnerListingResponse']>('PUT', '/v1/hub/listing', { body })

export const publishHubListing = (consentVersion: string) =>
  request<Schemas['OwnerListingResponse']>('POST', '/v1/hub/listing/publish', {
    body: { consent_version: consentVersion },
  })

export const unpublishHubListing = () =>
  request<Schemas['OwnerListingResponse']>('POST', '/v1/hub/listing/unpublish')

export const checkHubSlug = (slug: string, signal?: AbortSignal) =>
  request<Schemas['SlugAvailability']>('GET', `/v1/hub/slugs/${enc(slug)}`, { signal })

/** Divisions when `parent` is omitted, else the areas directly inside it. */
export const listHubAreas = (parent?: string, signal?: AbortSignal) =>
  request<Schemas['AreaOption'][]>('GET', '/v1/hub/areas', { query: { parent }, signal })

export const listBatchListings = (signal?: AbortSignal) =>
  request<Schemas['BatchListingResponse'][]>('GET', '/v1/hub/batch-listings', { signal })

export const saveBatchListing = (batchId: string, body: Schemas['BatchListingUpdateRequest']) =>
  request<Schemas['BatchListingResponse']>('PUT', `/v1/batches/${enc(batchId)}/listing`, { body })

export const publishBatchListing = (batchId: string) =>
  request<Schemas['BatchListingResponse']>('POST', `/v1/batches/${enc(batchId)}/listing/publish`)

export const unpublishBatchListing = (batchId: string) =>
  request<Schemas['BatchListingResponse']>('POST', `/v1/batches/${enc(batchId)}/listing/unpublish`)

/** The caller's own accepted centre memberships, with their name consent. */
export const listCentreMemberships = (signal?: AbortSignal) =>
  request<Schemas['CentreMembershipResponse'][]>('GET', '/v1/me/centre-memberships', { signal })

export const setPublicNameConsent = (centreId: string, consent: boolean) =>
  request<undefined>('PUT', `/v1/centres/${enc(centreId)}/members/me/public-name-consent`, {
    body: { consent },
  })

function enc(segment: string): string {
  return encodeURIComponent(segment)
}
