/**
 * The money area's API calls, typed from the committed OpenAPI schema.
 * Responses are returned as wire types; the mappers beside this file turn
 * money strings into `Money` and fail loudly on anything else.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const enc = encodeURIComponent

// ---------------------------------------------------------------- payments

export const readPayment = (submissionId: string) =>
  request<Schemas['PaymentReviewResponse']>('GET', `/v1/payments/${enc(submissionId)}`)

export const approvePayment = (submissionId: string, body: Schemas['PaymentApprovalRequest']) =>
  request<Schemas['PaymentReviewResponse']>('POST', `/v1/payments/${enc(submissionId)}/approval`, {
    body,
  })

export const rejectPayment = (submissionId: string, body: Schemas['PaymentRejectionRequest']) =>
  request<Schemas['PaymentReviewResponse']>('POST', `/v1/payments/${enc(submissionId)}/rejection`, {
    body,
  })

/**
 * Record money the teacher received by hand for one seat, approved in the
 * same step. The body's `client_mutation_id` makes a resend a replay.
 */
export const recordPayment = (enrollmentId: string, body: Schemas['ReceivedPaymentRequest']) =>
  request<Schemas['PaymentReviewResponse']>(
    'POST',
    `/v1/enrollments/${enc(enrollmentId)}/payments`,
    { body },
  )

// -------------------------------------------------------------- one seat

export const readSeatFees = (enrollmentId: string, months = 6) =>
  request<Schemas['FeeHistoryResponse']>('GET', `/v1/enrollments/${enc(enrollmentId)}/fees`, {
    query: { months },
  })

export type DashboardRange = '6m' | 'year' | 'all'

export const readSeatDashboard = (enrollmentId: string, range: DashboardRange) =>
  request<Schemas['DashboardResponse']>('GET', `/v1/enrollments/${enc(enrollmentId)}/dashboard`, {
    query: { range },
  })

// ---------------------------------------------------------- payment methods

export const listPaymentMethods = () =>
  request<Schemas['PaymentMethodResponse'][]>('GET', '/v1/payment-methods')

export const createPaymentMethod = (body: Schemas['PaymentMethodRequest']) =>
  request<Schemas['PaymentMethodResponse']>('POST', '/v1/payment-methods', { body })

export const updatePaymentMethod = (methodId: string, body: Schemas['PaymentMethodRequest']) =>
  request<Schemas['PaymentMethodResponse']>('PATCH', `/v1/payment-methods/${enc(methodId)}`, {
    body,
  })

export const retirePaymentMethod = (methodId: string) =>
  request<unknown>('DELETE', `/v1/payment-methods/${enc(methodId)}`)

// -------------------------------------------------------------- collections

/**
 * The collections report. `batch_id` repeats once per chosen batch, which
 * the client's scalar `query` option cannot say, so the query string is
 * built here. No batch means every batch.
 */
export const readCollections = (batchIds: readonly string[], months = 6) => {
  const params = new URLSearchParams({ months: String(months) })
  for (const id of batchIds) params.append('batch_id', id)
  return request<Schemas['CollectionsResponse']>('GET', `/v1/analytics/collections?${params}`)
}

/** One batch's month; no period means the server's current one. */
export const readBatchMonth = (batchId: string, period?: string) =>
  request<Schemas['BatchFeesResponse']>('GET', `/v1/batches/${enc(batchId)}/fees`, {
    query: { period },
  })
