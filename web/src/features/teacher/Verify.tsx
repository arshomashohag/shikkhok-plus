/**
 * T4 · Payment verification: the queue.
 *
 * Buttons appear only once the claim has loaded from the server — never
 * approve from stale data — so a queue that failed to refresh hides its
 * decision buttons instead of offering them against what was on screen.
 *
 * **One tap only for a payment that needs no further choice**: the server
 * says it matches what is owed and its transaction ID is new
 * (`VerifyViewModel.approveAsReported`). Everything else — a short or
 * over payment, a reused ID, a rejection, a payment shared by several
 * children — opens the payment (money/PaymentReview.tsx), where the
 * approval sheet, carry-or-waive, the child picker and the duplicate
 * warning live. `?act=` there opens the right control on arrival.
 */
import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { readQueue } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { ago, formatShortDate, initial } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import {
  Avatar,
  EmptyState,
  ErrorCard,
  FeeChip,
  Loading,
  Section,
  Snackbar,
  TopBar,
} from '../../ui/components'
import { WarningIcon } from '../../ui/icons'
import { mapQueue, reviewName, type PaymentReview } from './mappers'
import { paths } from './paths'
import { approvePayment } from './money/api'
import { ComparisonChip } from './money/ComparisonChip'
import { asReportedBody } from './money/review'

/** Whether a payment may be approved without opening it. */
export function oneTap(review: PaymentReview): boolean {
  return review.comparison === 'matches' && review.duplicateOf === null
}

export function Verify() {
  const { t, message } = useT()
  const { resource, reload } = useResource(() => readQueue().then(mapQueue), [])
  const [busy, setBusy] = useState<string | null>(null)
  const [snack, setSnack] = useState<{ text: string; retry?: () => void } | null>(null)
  const dismissSnack = useCallback(() => setSnack(null), [])

  async function approveAsReported(review: PaymentReview) {
    const body = oneTap(review) ? asReportedBody(review, '', false) : null
    if (!body) return
    setBusy(review.submissionId)
    try {
      await approvePayment(review.submissionId, body)
      setSnack({ text: t('payments_approved', review.totalAmount.format(), reviewName(review)) })
      reload()
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setSnack({
        text: error?.offline
          ? t('web_verify_offline')
          : message(error?.messageKey ?? 'error.unexpected'),
        retry: error?.retryable ? () => void approveAsReported(review) : undefined,
      })
      // Decided elsewhere meanwhile: show the queue as it is now.
      if (error?.code === 'PAYMENT_ALREADY_DECIDED') reload()
    } finally {
      setBusy(null)
    }
  }

  let body: React.ReactNode
  let subtitle: string | undefined
  if (resource.state === 'loading') {
    subtitle = t('verify_checking')
    body = <Loading rows={3} />
  } else if (resource.state === 'failed') {
    body = <ErrorCard title={t('verify_load_failed')} error={resource.error} onRetry={reload} />
  } else {
    const { pending, decidedRecently } = resource.data
    // A failed refresh hides the buttons: never decide against stale data.
    const decidable = resource.error === null && !resource.refreshing
    subtitle = pending.length ? t('verify_waiting', pending.length) : t('verify_nothing_waiting')
    body = (
      <>
        {pending.length === 0 ? (
          <div className="card">
            <EmptyState title={t('verify_all_caught_up')} body={t('verify_all_caught_up_body')} />
          </div>
        ) : (
          <div className="grid-2">
            {pending.map((r) => (
              <ReviewCard
                key={r.submissionId}
                review={r}
                decidable={decidable && busy === null}
                onApprove={() => void approveAsReported(r)}
              />
            ))}
          </div>
        )}
        {decidedRecently.length > 0 ? (
          <Section title={t('verify_decided_today')}>
            <ul className="card flush list">
              {decidedRecently.map((d) => (
                <li key={d.submissionId}>
                  <Link className="row" to={paths.payment(d.submissionId)}>
                    <div className="grow">
                      <div className="title">{d.displayName}</div>
                      <div className="meta">{d.batchName}</div>
                    </div>
                    <div className="end">
                      <span className="amount">{d.amount.format()}</span>
                      {d.status === 'approved' ? (
                        <FeeChip chip={{ kind: 'paid' }} />
                      ) : (
                        <span className="chip chip-neutral">{t('verify_decision_rejected')}</span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
      </>
    )
  }

  return (
    <>
      <TopBar title={t('verify_title')} subtitle={subtitle} back="/today" />
      {body}
      {snack ? (
        <Snackbar
          text={snack.text}
          action={snack.retry ? t('auth_retry') : undefined}
          onAction={snack.retry}
          onDismiss={dismissSnack}
        />
      ) : null}
    </>
  )
}

/** The detail, opening a control on arrival. */
function open(review: PaymentReview, act?: 'approve' | 'reject'): string {
  return `${paths.payment(review.submissionId)}${act ? `?act=${act}` : ''}`
}

function ReviewCard({
  review,
  decidable,
  onApprove,
}: {
  review: PaymentReview
  decidable: boolean
  onApprove: () => void
}) {
  const { t, lang } = useT()
  const name = reviewName(review)

  return (
    <article className={review.duplicateOf ? 'card error' : 'card'} aria-label={name}>
      <Link
        to={open(review)}
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'center',
          color: 'inherit',
          textDecoration: 'none',
        }}
      >
        <Avatar letter={initial(name)} />
        <div className="grow">
          <div className="title">{name}</div>
          <div className="meta">
            {review.batchName} · {ago(review.submittedAt, new Date(), t)}
          </div>
        </div>
      </Link>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
          marginTop: 12,
        }}
      >
        <span className="hero-amount" style={{ margin: 0 }}>
          {review.totalAmount.format()}
        </span>
        <ComparisonChip review={review} />
      </div>
      <dl className="kv">
        {review.transactionId ? (
          <>
            <dt>
              {review.channelLabel ? `${review.channelLabel} TrxID` : t('verify_transaction_id')}
            </dt>
            <dd className="mono">{review.transactionId}</dd>
          </>
        ) : null}
        {review.fromAccount ? (
          <>
            <dt>{t('verify_paid_from')}</dt>
            <dd>{review.fromAccount}</dd>
          </>
        ) : null}
        <dt>{t('verify_paid_on')}</dt>
        <dd>{formatShortDate(review.paidOn, lang)}</dd>
        {review.children.length > 1 ? (
          <>
            <dt>{t('verify_owed_together')}</dt>
            <dd>{review.children.map((c) => `${c.displayName} ${c.owed.format()}`).join(', ')}</dd>
          </>
        ) : null}
        {review.payerNote ? (
          <>
            <dt>{t('verify_their_note')}</dt>
            <dd>{review.payerNote}</dd>
          </>
        ) : null}
      </dl>

      {review.duplicateOf ? (
        <div className="banner error" style={{ marginTop: 12 }}>
          <WarningIcon />
          <div>
            <strong>{t('verify_duplicate_title')}</strong>{' '}
            {t(
              'verify_duplicate_body',
              review.duplicateOf.displayName,
              t(`verify_decision_${review.duplicateOf.status}`),
              review.duplicateOf.amount.format(),
            )}
          </div>
        </div>
      ) : null}

      {decidable ? (
        <div className="button-row">
          <Link className="btn btn-danger" to={open(review, 'reject')}>
            {review.duplicateOf ? t('verify_reject_duplicate') : t('verify_reject')}
          </Link>
          {oneTap(review) ? (
            <>
              <Link className="btn btn-tonal" to={open(review, 'approve')}>
                {t('verify_partial')}
              </Link>
              <button type="button" className="btn btn-primary grow" onClick={onApprove}>
                {t('verify_approve')}
              </button>
            </>
          ) : review.duplicateOf ? (
            <Link className="btn btn-outline grow" to={open(review)}>
              {t('verify_approve_anyway')}
            </Link>
          ) : review.comparison === 'short' ? (
            <Link className="btn btn-primary grow" to={open(review, 'approve')}>
              {`${t('verify_partial_confirm', review.totalAmount.format())}…`}
            </Link>
          ) : (
            <Link className="btn btn-primary grow" to={open(review)}>
              {t('verify_review')}
            </Link>
          )}
        </div>
      ) : null}
    </article>
  )
}
