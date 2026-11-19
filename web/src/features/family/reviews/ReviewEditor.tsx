/**
 * One batch's review, as its guardian author sees it [H4].
 *
 * **The server decides; the screen draws.** `can_write` alone says
 * whether the form is editable, `edit_until` is the last day an edit is
 * accepted, `standing` says why a member cannot write yet, and `status`
 * with `rejection_code` says where the review is in moderation. The client
 * counts no days, sessions or reviews.
 *
 * A failed write keeps the rating and the words; Retry is offered only
 * when the server says trying again can help, or the connection dropped
 * [TC-8]. A delete is sent only from its confirmation, and is never
 * gated: an author can always remove their words.
 */
import { useState, type FormEvent } from 'react'
import { useLocation, useParams } from 'react-router'
import { ApiError, UNEXPECTED_KEY } from '../../../api/errors'
import { formatDayOf } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  ConfirmSheet,
  ErrorCard,
  Loading,
  RatingStars,
  Section,
  Snackbar,
  TopBar,
} from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { reviewPaths } from '../reader'
import { deleteMyReview, readMyReview, saveMyReview } from './api'
import {
  MAX_TEXT,
  REVIEW_STATUS_CHIP,
  STARS,
  TENURE_KEY,
  refusedFrom,
  standingNote,
  statusText,
  type MyReviewState,
} from './mappers'
import type { ReviewLinkState } from './MyReviews'

function titleOf(state: unknown): string | undefined {
  const title = (state as Partial<ReviewLinkState> | null)?.title
  return typeof title === 'string' && title ? title : undefined
}

export function ReviewEditor() {
  const { t } = useT()
  const { batchId = '' } = useParams()
  const subtitle = titleOf(useLocation().state)
  const { resource, reload } = useResource((signal) => readMyReview(batchId, signal), [batchId])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = (
      <ErrorCard title={t('hub_review_editor_title')} error={resource.error} onRetry={reload} />
    )
  else body = <Editor batchId={batchId} initial={resource.data} />

  return (
    <>
      <TopBar title={t('hub_review_editor_title')} subtitle={subtitle} back={reviewPaths.list()} />
      {body}
    </>
  )
}

interface Failure {
  text: string
  eligibleFrom: string | null
  /** What Retry repeats, with what is on screen when it is pressed. */
  retry: 'save' | 'delete' | null
}

function Editor({ batchId, initial }: { batchId: string; initial: MyReviewState }) {
  const { t, message, lang } = useT()
  const [state, setState] = useState(initial)
  const [rating, setRating] = useState<number | null>(initial.review?.rating ?? null)
  const [text, setText] = useState(initial.review?.body ?? '')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)

  const review = state.review ?? null
  const note = review ? null : standingNote(state)

  function failed(prefix: string, e: unknown, retry: 'save' | 'delete'): Failure {
    const error = e instanceof ApiError ? e : null
    const retryable = !error || error.offline || error.retryable
    return {
      text: `${t(prefix)} ${message(error?.messageKey ?? UNEXPECTED_KEY, error?.details)}`,
      eligibleFrom: refusedFrom(error),
      retry: retryable ? retry : null,
    }
  }

  async function save() {
    if (rating === null || busy) return
    setBusy(true)
    setFailure(null)
    try {
      setState(await saveMyReview(batchId, { rating, body: text.trim() || null }))
    } catch (e) {
      setFailure(failed('hub_review_failed', e, 'save'))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setFailure(null)
    try {
      await deleteMyReview(batchId)
      setConfirming(false)
      setRating(null)
      setText('')
      setSnack(t('hub_review_deleted'))
      // What may be written now is the server's to say, so ask it again;
      // until it answers, nothing is offered that it did not confirm.
      try {
        setState(await readMyReview(batchId))
      } catch {
        setState({ ...state, review: null, edit_until: null, can_write: false })
      }
    } catch (e) {
      setConfirming(false)
      setFailure(failed('hub_review_delete_failed', e, 'delete'))
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void save()
  }

  const banner = failure ? (
    <div className="banner error" role="alert">
      <WarningIcon />
      <div className="grow">
        <div>{failure.text}</div>
        {failure.eligibleFrom ? (
          <div>{t('hub_review_eligible_from', formatDayOf(failure.eligibleFrom, lang))}</div>
        ) : null}
      </div>
      {failure.retry ? (
        <button
          type="button"
          className="btn btn-text btn-small"
          disabled={busy}
          onClick={() => (failure.retry === 'save' ? void save() : setConfirming(true))}
        >
          {t('auth_retry')}
        </button>
      ) : null}
    </div>
  ) : null

  return (
    <>
      {note ? (
        <div className="banner info" role="status">
          <div className="grow">
            <p style={{ margin: 0 }}>{message(note.messageKey)}</p>
            {note.eligibleFrom ? (
              <p style={{ margin: 0 }}>
                {t('hub_review_eligible_from', formatDayOf(note.eligibleFrom, lang))}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {review ? (
        <div className="card">
          <p style={{ marginTop: 0 }}>
            <span className={REVIEW_STATUS_CHIP[review.status]}>
              {statusText(review.status, review.rejection_code, t)}
            </span>
          </p>
          <div className="meta">{t(TENURE_KEY[review.tenure])}</div>
          {state.edit_until ? (
            <p className="meta">
              {t('hub_review_edit_until', formatDayOf(state.edit_until, lang))}
            </p>
          ) : null}
          {state.can_write ? null : (
            <>
              <RatingStars rating={review.rating} />
              {review.body ? (
                <p style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{review.body}</p>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      {state.can_write ? (
        <form className="card form-page" onSubmit={onSubmit} noValidate>
          <fieldset className="field">
            <legend>{t('hub_review_rating_legend')}</legend>
            {STARS.map((s) => (
              <label key={s.rating} className="choice">
                <input
                  type="radio"
                  name="rating"
                  value={s.rating}
                  checked={rating === s.rating}
                  disabled={busy}
                  onChange={() => setRating(s.rating)}
                />
                <span>{t(s.key)}</span>
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor="review-body">{t('hub_review_body_label')}</label>
            <textarea
              id="review-body"
              rows={5}
              value={text}
              maxLength={MAX_TEXT}
              disabled={busy}
              onChange={(e) => setText(e.target.value)}
              aria-describedby="review-body-count"
            />
            <div className="row">
              <span className="grow" />
              <span id="review-body-count" className="meta">
                {t('hub_report_note_count', text.length, MAX_TEXT)}
              </span>
            </div>
          </div>
          <p className="meta">{t('hub_review_privacy_note')}</p>
          {banner}
          <div className="button-row">
            <button type="submit" className="btn btn-primary" disabled={busy || rating === null}>
              {review ? t('hub_review_save') : t('hub_review_submit')}
            </button>
          </div>
        </form>
      ) : (
        banner
      )}

      {review?.reply_body ? (
        <Section title={t('hub_review_reply_heading')}>
          <p className="card" style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
            {review.reply_body}
          </p>
        </Section>
      ) : null}

      {review ? (
        <div className="button-row">
          <button
            type="button"
            className="btn btn-text"
            disabled={busy}
            onClick={() => setConfirming(true)}
          >
            {t('hub_review_delete')}
          </button>
        </div>
      ) : null}

      {confirming ? (
        <ConfirmSheet
          title={t('hub_review_delete_title')}
          body={t('hub_review_delete_body')}
          confirmLabel={t('hub_review_delete')}
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
