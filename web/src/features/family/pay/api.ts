/**
 * The calls the family paying screens make. Which endpoint depends on the
 * reader; the server checks the lens on every one of them [D-2].
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import type { Reader } from '../reader'

const enc = (s: string) => encodeURIComponent(s)

/** A student's own seats. */
export const readMySeats = (signal?: AbortSignal) =>
  request<Schemas['StudentBatchResponse'][]>('GET', '/v1/me/enrollments', { signal })

/** A guardian's children and their seats (Android's `guardianSeats`). */
export const readGuardianHome = (signal?: AbortSignal) =>
  request<Schemas['GuardianHomeResponse']>('GET', '/v1/guardian/home', { signal })

/** Where the teacher of one seat accepts money. */
export const readSeatMethods = (reader: Reader, seat: string, signal?: AbortSignal) =>
  request<Schemas['FamilyPaymentMethodsResponse']>(
    'GET',
    reader === 'me'
      ? `/v1/me/enrollments/${enc(seat)}/payment-methods`
      : `/v1/children/${enc(seat)}/payment-methods`,
    { signal },
  )

/**
 * What the chosen seats owe together, as the server totals it.
 *
 * `enrollment_id` repeats, one per seat, which the shared request helper
 * cannot express, so the query string is built here.
 */
export const readOwedTogether = (
  seats: readonly string[],
  extraFeeId: string | null = null,
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams()
  for (const s of seats) query.append('enrollment_id', s)
  if (extraFeeId !== null) query.append('extra_fee_id', extraFeeId)
  return request<Schemas['OwedTogetherResponse']>('GET', `/v1/payments/owed?${query.toString()}`, {
    signal,
  })
}

/** The exam and other fees one seat was charged, soonest due first. */
export const readSeatExtraFees = (seat: string, signal?: AbortSignal) =>
  request<Schemas['SeatExtraFeesResponse']>('GET', `/v1/enrollments/${enc(seat)}/extra-fees`, {
    signal,
  })

export const submitPayment = (body: Schemas['PaymentSubmitRequest']) =>
  request<Schemas['PaymentSubmittedResponse']>('POST', '/v1/payments', { body })

/** A child's payments, month by month (G2). Guardian only: there is no student twin. */
export const readChildPayments = (seat: string, signal?: AbortSignal) =>
  request<Schemas['PaymentsResponse']>('GET', `/v1/children/${enc(seat)}/payments`, { signal })

/** What a seat owes next, as the server orders it. */
export const readPayables = (reader: Reader, seat: string, signal?: AbortSignal) =>
  reader === 'me'
    ? request<Schemas['PayablesResponse']>('GET', '/v1/me/payables', { signal })
    : request<Schemas['PayablesResponse']>('GET', `/v1/children/${enc(seat)}/payables`, { signal })

/** One seat's fee history, for the family reader. */
export const readFamilyFees = (reader: Reader, seat: string, signal?: AbortSignal) =>
  reader === 'me'
    ? request<Schemas['FeeHistoryResponse']>('GET', '/v1/me/fees', {
        signal,
        query: { enrollment_id: seat },
      })
    : request<Schemas['FeeHistoryResponse']>('GET', `/v1/children/${enc(seat)}/fees`, { signal })
