/**
 * The owner's Reviews screen [H4]: each published batch's rating, then the
 * published reviews, newest month first as the server sends them, each
 * with a reply box.
 *
 * **Exactly what the public sees, and no more.** Below three published
 * reviews a batch's figures arrive as nulls and it shows a neutral line,
 * never a number: the line is drawn from the server's nulls, not from a
 * count kept here. The average is the server's `average_label`, shown as
 * sent; nothing is formatted from `average_tenths` [F13]. A review shows a
 * tenure and a month, never a name.
 *
 * A reply is checked before it appears, so a sent reply reads "Awaiting
 * review". A failed send keeps the words and offers Retry when the server
 * says it can help [TC-8]. `HUB_REVIEWS_OFF` draws nothing at all.
 */
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  deleteReviewReply,
  readOwnerReviews,
  saveReviewReply,
  type Schemas,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatMonthYear } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  ConfirmSheet,
  ErrorCard,
  Loading,
  RatingStars,
  Section,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { MAX_TEXT, REVIEW_STATUS_CHIP, TENURE_KEY, statusText } from '../../family/reviews/mappers'
import { paths } from '../paths'
import { failureText, FailureBanner, isReviewsOff } from './hubUi'

type Rating = Schemas['OwnerBatchRatingWire']
type Review = Schemas['OwnerReviewWire']

/** From five stars down to one. */
const STARS_DOWN = [5, 4, 3, 2, 1] as const

/** The report link for a review: its id is what `POST /v1/hub/reports` takes. */
const reportPath = (reviewId: string) =>
  `/hub-report?kind=review&id=${encodeURIComponent(reviewId)}`

export function OwnerReviews() {
  const { t } = useT()
  const { resource, reload } = useResource((signal) => readOwnerReviews(signal), [])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = isReviewsOff(resource.error) ? null : (
      <ErrorCard title={t('hub_reviews_title')} error={resource.error} onRetry={reload} />
    )
  else
    body = (
      <>
        {resource.error && !isReviewsOff(resource.error) ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <Content data={resource.data} />
      </>
    )

  return (
    <>
      <TopBar title={t('hub_reviews_title')} back={paths.hub()} />
      {body}
    </>
  )
}

function Content({ data }: { data: Schemas['OwnerReviewsResponse'] }) {
  const { t } = useT()
  const titles = new Map(data.batches.map((b) => [b.batch_id, b.batch_title ?? '']))
  return (
    <>
      <ul className="card flush list" aria-label={t('hub_reviews_title')}>
        {data.batches.map((b) => (
          <BatchRating key={b.batch_id} rating={b} />
        ))}
      </ul>
      <Section title={t('hub_reviews_published_heading')}>
        {data.reviews.length === 0 ? (
          <div className="card meta">{t('hub_reviews_none')}</div>
        ) : (
          data.reviews.map((r) => (
            <ReviewCard key={r.id} initial={r} batchTitle={titles.get(r.batch_id) ?? ''} />
          ))
        )}
      </Section>
    </>
  )
}

function BatchRating({ rating }: { rating: Rating }) {
  const { t, plural } = useT()
  const distribution = rating.distribution ?? null
  return (
    <li>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div className="grow">
          <div className="title">{rating.batch_title ?? ''}</div>
          {rating.average_label === null ? (
            <div className="meta">{t('hub_reviews_below_threshold')}</div>
          ) : (
            <>
              <div>
                <strong>{t('hub_reviews_average', rating.average_label)}</strong>
              </div>
              {rating.review_count !== null ? (
                <div className="meta">{plural('hub_reviews_count', rating.review_count)}</div>
              ) : null}
              {distribution ? (
                <div className="meta" style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                  {STARS_DOWN.map((star) => (
                    <span key={star}>
                      {t('hub_reviews_distribution', star, distribution[star - 1] ?? 0)}
                    </span>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </li>
  )
}

/** Which call failed, so Retry repeats it with what is on screen now. */
type Failed = { text: string; retry: 'send' | 'delete' | null }

function ReviewCard({ initial, batchTitle }: { initial: Review; batchTitle: string }) {
  const { t, message, lang } = useT()
  const [review, setReview] = useState(initial)
  const [reply, setReply] = useState(initial.my_reply_body ?? '')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failed | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  const boxId = `reply-${review.id}`

  function failed(prefix: string, e: unknown, retry: 'send' | 'delete'): Failed {
    const retryable = !(e instanceof ApiError) || e.offline || e.retryable
    return { text: `${t(prefix)} ${failureText(e, t, message)}`, retry: retryable ? retry : null }
  }

  async function send() {
    const body = reply.trim()
    if (!body || busy) return
    setBusy(true)
    setFailure(null)
    try {
      const saved = await saveReviewReply(review.id, { body })
      setReview(saved)
      setReply(saved.my_reply_body ?? body)
    } catch (e) {
      setFailure(failed('hub_reviews_reply_failed', e, 'send'))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setFailure(null)
    try {
      await deleteReviewReply(review.id)
      // 204: the reply is gone, in every status.
      setReview({
        ...review,
        reply_body: null,
        reply_month: null,
        my_reply_status: null,
        my_reply_body: null,
        my_reply_rejection_code: null,
      })
      setReply('')
      setSnack(t('hub_reviews_reply_deleted'))
    } catch (e) {
      setFailure(failed('hub_reviews_reply_delete_failed', e, 'delete'))
    } finally {
      setConfirming(false)
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send()
  }

  return (
    <article className="card">
      <div className="title">{batchTitle}</div>
      <RatingStars rating={review.rating} />
      <div className="meta">
        {t(TENURE_KEY[review.tenure])} · {formatMonthYear(review.published_month, lang)}
      </div>
      {review.body ? (
        <p style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{review.body}</p>
      ) : null}

      <form onSubmit={onSubmit} noValidate>
        <div className="field">
          <label htmlFor={boxId}>{t('hub_reviews_reply_label')}</label>
          <textarea
            id={boxId}
            rows={3}
            value={reply}
            maxLength={MAX_TEXT}
            disabled={busy}
            onChange={(e) => setReply(e.target.value)}
            aria-describedby={`${boxId}-count`}
          />
          <div className="row">
            <span className="help grow">{t('hub_reviews_reply_note')}</span>
            <span id={`${boxId}-count`} className="meta">
              {t('hub_report_note_count', reply.length, MAX_TEXT)}
            </span>
          </div>
        </div>
        {review.my_reply_status ? (
          <p>
            <span className={REVIEW_STATUS_CHIP[review.my_reply_status]}>
              {statusText(review.my_reply_status, review.my_reply_rejection_code, t)}
            </span>
          </p>
        ) : null}
        {failure ? (
          <FailureBanner
            text={failure.text}
            onRetry={
              failure.retry
                ? () => (failure.retry === 'send' ? void send() : setConfirming(true))
                : undefined
            }
          />
        ) : null}
        <div className="button-row">
          <button type="submit" className="btn btn-outline" disabled={busy || reply.trim() === ''}>
            {t('hub_reviews_reply_send')}
          </button>
          {review.my_reply_status ? (
            <button
              type="button"
              className="btn btn-text"
              disabled={busy}
              onClick={() => setConfirming(true)}
            >
              {t('hub_reviews_reply_delete')}
            </button>
          ) : null}
          <Link className="btn btn-text" to={reportPath(review.id)}>
            {t('hub_reviews_report')}
          </Link>
        </div>
      </form>

      {confirming ? (
        <ConfirmSheet
          title={t('hub_reviews_reply_delete_title')}
          body={t('hub_reviews_reply_delete_body')}
          confirmLabel={t('hub_reviews_reply_delete')}
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </article>
  )
}
