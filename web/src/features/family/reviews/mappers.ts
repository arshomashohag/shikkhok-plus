/**
 * What the review screens draw from what the server sent [H4]. Pure, and
 * the test target. **Nothing here decides anything the server owns**:
 * eligibility is `standing` and `can_write`, the edit window is
 * `edit_until`, a status is `status`, the reason is `rejection_code`, and
 * an average is `average_label`, already rendered. These tables only
 * name the string each server value is worded with.
 */
import type { Schemas } from '../../../api/endpoints'
import type { ApiError } from '../../../api/errors'

export type MyReviewState = Schemas['MyReviewResponse']
export type MyReview = Schemas['MyReviewBody']
export type Reviewable = Schemas['ReviewableBatch']
export type ReviewStatus = MyReview['status']
export type Tenure = MyReview['tenure']

/** The longest review or reply the server accepts, once stripped. */
export const MAX_TEXT = 1000

/** One to five, each with its label, for the rating radios. */
export const STARS: readonly { rating: number; key: string }[] = [1, 2, 3, 4, 5].map((rating) => ({
  rating,
  key: `hub_review_star_${rating}`,
}))

/**
 * A review's or a reply's status in words. A held item is back with the
 * moderators, so its author reads "Awaiting review": that someone reported
 * it is not theirs to learn here. Rejected and removed name the reason.
 */
export const REVIEW_STATUS_KEY: Record<ReviewStatus, string> = {
  pending: 'hub_review_status_pending',
  approved: 'hub_review_status_approved',
  published: 'hub_review_status_published',
  rejected: 'hub_review_status_not_published',
  removed: 'hub_review_status_not_published',
  held: 'hub_review_status_pending',
}

export const REVIEW_STATUS_CHIP: Record<ReviewStatus, string> = {
  pending: 'chip',
  approved: 'chip',
  published: 'chip chip-paid',
  rejected: 'chip chip-overdue',
  removed: 'chip chip-overdue',
  held: 'chip',
}

/** The moderators' closed vocabulary (`REVIEW_REJECTION_CODES`). */
const REASONS: readonly string[] = [
  'identifiable_child',
  'personal_info',
  'abusive',
  'off_topic',
  'other',
]

/** The reason's string; a code this client does not know reads as "other". */
export function reasonKey(code: string | null | undefined): string {
  return `hub_review_reason_${code && REASONS.includes(code) ? code : 'other'}`
}

type T = (key: string, ...args: (string | number)[]) => string

/** "Awaiting review", "Published", "Not published: it is abusive or offensive"… */
export function statusText(status: ReviewStatus, code: string | null | undefined, t: T): string {
  const key = REVIEW_STATUS_KEY[status]
  return status === 'rejected' || status === 'removed' ? t(key, t(reasonKey(code))) : t(key)
}

/** Who wrote a review, as the public reads it: a tenure, never a name. */
export const TENURE_KEY: Record<Tenure, string> = {
  lt_6m: 'hub_review_tenure_lt_6m',
  '6_12m': 'hub_review_tenure_6_12m',
  gt_1y: 'hub_review_tenure_gt_1y',
}

/** A row of the reviewable list, as its state says. */
export const REVIEWABLE_KEY: Record<Reviewable['state'], string> = {
  eligible: 'hub_reviews_state_eligible',
  not_yet: 'hub_reviews_state_not_yet',
  reviewed: 'hub_reviews_state_reviewed',
}

/** Why a member cannot write yet: the server's message key, and its day. */
export interface StandingNote {
  messageKey: string
  eligibleFrom: string | null
}

/**
 * The server's standing in the words of the matching refusal, so a read
 * and a refused write say the same thing. Null while nothing stands in
 * the way, and for an author who is no longer a member: `can_write`
 * already says whether they may edit.
 */
export function standingNote(state: MyReviewState): StandingNote | null {
  if (state.standing === 'not_yet') {
    return {
      messageKey:
        state.waiting_on === 'attendance'
          ? 'hub.review.needs_attendance'
          : 'hub.review.not_yet_eligible',
      eligibleFrom: state.eligible_from ?? null,
    }
  }
  if (state.standing === 'closed') {
    return { messageKey: 'hub.review.window_closed', eligibleFrom: null }
  }
  return null
}

/** A refused write's day, when the server sent one (`details.eligible_from`). */
export function refusedFrom(error: ApiError | null): string | null {
  return error?.details?.eligible_from ?? null
}

/**
 * Whether the editor has nothing of the server's to draw: no review, no
 * standing note and no form. Reviews switched off before a first review,
 * or an author whose review is gone, read this way; the screen then says
 * a review cannot be written now rather than drawing an empty page. It
 * reads only what the server sent.
 */
export function nothingToShow(state: MyReviewState): boolean {
  return !state.review && !state.can_write && standingNote(state) === null
}
