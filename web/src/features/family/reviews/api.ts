/**
 * The guardian's review calls [H4]. The reviewer lens is resolved by the
 * server from the batch in the path; nothing here says who may review.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

const enc = encodeURIComponent
const mine = (batchId: string) => `/v1/hub/batches/${enc(batchId)}/my-review`

/** Batches the caller may review, is waiting to, or has reviewed. */
export const listReviewable = (signal?: AbortSignal) =>
  request<Schemas['ReviewableBatch'][]>('GET', '/v1/hub/reviewable', { signal })

/** Where the caller stands with one batch's review, and the review itself. */
export const readMyReview = (batchId: string, signal?: AbortSignal) =>
  request<Schemas['MyReviewResponse']>('GET', mine(batchId), { signal })

/** Write or edit the caller's review; it goes back to moderation. */
export const saveMyReview = (batchId: string, body: Schemas['ReviewWrite']) =>
  request<Schemas['MyReviewResponse']>('PUT', mine(batchId), { body })

/** Delete the caller's review completely, with its reply and reports. */
export const deleteMyReview = (batchId: string) => request<undefined>('DELETE', mine(batchId))
