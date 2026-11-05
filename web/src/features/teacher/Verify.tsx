/**
 * T4 · Payment verification.
 *
 * Buttons appear only once the claim has loaded from the server — never
 * approve from stale data — so a queue that failed to refresh hides its
 * decision buttons instead of offering them against what was on screen.
 *
 * Built here: approve as reported, approve a different amount for a
 * one-child payment (carry the shortfall forward, or waive it), reject
 * with a note, and the duplicate-transaction warning. Splitting a payment
 * across several children is in the Android app for now, and the sheet
 * says so rather than guessing a split.
 */
import { useCallback, useState } from 'react'
import { approvePayment, readQueue, rejectPayment, type Schemas } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import {
  ago,
  formatMonth,
  formatPhone,
  formatShortDate,
  formatShortMonth,
  initial,
} from '../../core/format'
import { Money } from '../../core/money'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import {
  Avatar,
  EmptyState,
  ErrorCard,
  FeeChip,
  Loading,
  Section,
  Sheet,
  Snackbar,
  TopBar,
} from '../../ui/components'
import { CheckCircleIcon, HalfCircleIcon, WarningIcon } from '../../ui/icons'
import { mapQueue, reviewName, type PaymentReview } from './mappers'

const NOTE_MAX = 200

/** Whether a payment may be approved without opening the sheet. */
export function oneTap(review: PaymentReview): boolean {
  return review.comparison === 'matches' && review.duplicateOf === null
}

type Dialog =
  { kind: 'partial'; review: PaymentReview } | { kind: 'reject'; review: PaymentReview } | null

export function Verify() {
  const { t, message } = useT()
  const { resource, reload } = useResource(() => readQueue().then(mapQueue), [])
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [snack, setSnack] = useState<{ text: string; retry?: () => void } | null>(null)
  const dismissSnack = useCallback(() => setSnack(null), [])

  async function decide(
    review: PaymentReview,
    send: () => Promise<Schemas['PaymentReviewResponse']>,
    done: string,
  ) {
    setBusy(review.submissionId)
    try {
      await send()
      setDialog(null)
      setSnack({ text: done })
      reload()
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setSnack({
        text: error?.offline
          ? t('web_verify_offline')
          : message(error?.messageKey ?? 'error.unexpected'),
        retry: error?.retryable ? () => void decide(review, send, done) : undefined,
      })
    } finally {
      setBusy(null)
    }
  }

  /**
   * One tap, **only for a payment that needs no further choice**: the
   * server says it matches what is owed and its transaction ID was not
   * used before — `VerifyViewModel.approveAsReported`'s rule. Anything
   * short, over or reused goes through the sheet, where carry-forward,
   * waive and the duplicate warning live.
   */
  const approveAsReported = (r: PaymentReview) =>
    oneTap(r) &&
    decide(
      r,
      () =>
        approvePayment(r.submissionId, { received_amount: r.totalAmount.wire, correcting: false }),
      t('payments_approved', r.totalAmount.format(), reviewName(r)),
    )

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
                onPartial={() => setDialog({ kind: 'partial', review: r })}
                onReject={() => setDialog({ kind: 'reject', review: r })}
              />
            ))}
          </div>
        )}
        {decidedRecently.length > 0 ? (
          <Section title={t('verify_decided_today')}>
            <ul className="card flush list">
              {decidedRecently.map((d) => (
                <li key={d.submissionId} className="row">
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
      {dialog?.kind === 'partial' ? (
        <PartialSheet
          review={dialog.review}
          busy={busy !== null}
          onClose={() => setDialog(null)}
          onConfirm={(request, label) =>
            void decide(
              dialog.review,
              () => approvePayment(dialog.review.submissionId, request),
              label,
            )
          }
        />
      ) : null}
      {dialog?.kind === 'reject' ? (
        <RejectSheet
          review={dialog.review}
          busy={busy !== null}
          onClose={() => setDialog(null)}
          onConfirm={(note) =>
            void decide(
              dialog.review,
              () =>
                rejectPayment(dialog.review.submissionId, {
                  note: note || null,
                  correcting: false,
                }),
              t('web_verify_rejected', reviewName(dialog.review)),
            )
          }
        />
      ) : null}
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

function ReviewCard({
  review,
  decidable,
  onApprove,
  onPartial,
  onReject,
}: {
  review: PaymentReview
  decidable: boolean
  onApprove: () => void
  onPartial: () => void
  onReject: () => void
}) {
  const { t, lang } = useT()
  const name = reviewName(review)
  const period = review.children[0]?.period
  const comparison =
    review.comparison === 'matches' ? (
      <span className="chip chip-paid">
        <CheckCircleIcon size={14} />
        {t('verify_matches', period ? formatShortMonth(period, lang) : '')}
      </span>
    ) : review.comparison === 'short' ? (
      <span className="chip chip-partial">
        <HalfCircleIcon size={14} />
        {t('verify_short', review.difference.format(), review.owedTogether.format())}
      </span>
    ) : (
      <span className="chip chip-partial">
        {t('verify_over', review.difference.format(), review.owedTogether.format())}
      </span>
    )

  return (
    <article className={review.duplicateOf ? 'card error' : 'card'} aria-label={name}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <Avatar letter={initial(name)} />
        <div className="grow">
          <div className="title">{name}</div>
          <div className="meta">
            {review.batchName} · {ago(review.submittedAt, new Date(), t)}
          </div>
        </div>
      </div>
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
        {comparison}
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
            <dd>{formatPhone(review.fromAccount)}</dd>
          </>
        ) : null}
        <dt>{t('verify_paid_on')}</dt>
        <dd>{formatShortDate(review.paidOn, lang)}</dd>
        {review.children.length > 1 ? (
          <>
            <dt>{t('verify_owed_together')}</dt>
            <dd>
              {review.children
                .map((c) => t('verify_child_line', c.displayName, c.owed.format()))
                .join(', ')}
            </dd>
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
              review.duplicateOf.amount.format(),
              t(`verify_decision_${review.duplicateOf.status}`),
            )}
          </div>
        </div>
      ) : null}

      {decidable ? (
        <div className="button-row">
          <button type="button" className="btn btn-danger" onClick={onReject}>
            {review.duplicateOf ? t('verify_reject_duplicate') : t('verify_reject')}
          </button>
          {oneTap(review) ? (
            <>
              <button type="button" className="btn btn-tonal" onClick={onPartial}>
                {t('verify_partial')}
              </button>
              <button type="button" className="btn btn-primary grow" onClick={onApprove}>
                {t('verify_approve')}
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-primary grow" onClick={onPartial}>
              {review.duplicateOf
                ? t('verify_approve_anyway')
                : `${t('verify_partial_confirm', review.totalAmount.format())}…`}
            </button>
          )}
        </div>
      ) : null}
    </article>
  )
}

function PartialSheet({
  review,
  busy,
  onClose,
  onConfirm,
}: {
  review: PaymentReview
  busy: boolean
  onClose: () => void
  onConfirm: (request: Schemas['PaymentApprovalRequest'], doneLabel: string) => void
}) {
  const { t, lang } = useT()
  // Starts at what the payer reported; the teacher edits it if a
  // different amount actually arrived.
  const [typed, setTyped] = useState(review.totalAmount.wire.replace(/\.00$/, ''))
  const [disposition, setDisposition] = useState<'carried' | 'waived' | null>(null)
  const [note, setNote] = useState('')
  const received = Money.fromTyped(typed)
  const child = review.children[0]
  const name = reviewName(review)
  // Against what is owed together, as `ApprovalSheet.side` on Android.
  const side = received ? received.compare(review.owedTogether) : null
  const several = review.children.length > 1

  // Shaping the form only — see Money.compare. The server decides.
  const short = side === -1
  const canConfirm =
    received !== null && !received.isZero() && !several && (!short || disposition !== null)

  return (
    <Sheet
      title={
        received && short
          ? t('verify_sheet_title_partial', received.format(), review.owedTogether.format())
          : t('verify_sheet_title')
      }
      subtitle={[name, child ? formatMonth(child.period, lang) : null, review.channelLabel]
        .filter(Boolean)
        .join(' · ')}
      onClose={onClose}
    >
      {several ? (
        <p className="banner">{t('web_more_payments_on_android')}</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="ps-received">{t('verify_received_amount')}</label>
            <input
              id="ps-received"
              inputMode="decimal"
              value={typed}
              onChange={(e) => {
                setTyped(e.target.value)
                setDisposition(null)
              }}
              aria-invalid={typed !== '' && received === null ? true : undefined}
            />
            {typed !== '' && received === null ? (
              <span className="field-error">{t('fee_invalid')}</span>
            ) : null}
          </div>
          {short ? (
            <fieldset className="field">
              <legend>{t('fees_verification_disposition_required')}</legend>
              <label className="choice">
                <input
                  type="radio"
                  name="disp"
                  checked={disposition === 'carried'}
                  onChange={() => setDisposition('carried')}
                />
                <span>
                  <span className="title">{t('verify_carry_forward')}</span>
                  <br />
                  <span className="meta">{t('verify_carry_forward_body')}</span>
                </span>
              </label>
              <label className="choice">
                <input
                  type="radio"
                  name="disp"
                  checked={disposition === 'waived'}
                  onChange={() => setDisposition('waived')}
                />
                <span>
                  <span className="title">{t('verify_waive')}</span>
                  <br />
                  <span className="meta">{t('verify_waive_body')}</span>
                </span>
              </label>
            </fieldset>
          ) : null}
          <div className="field">
            <label htmlFor="ps-note">{t('verify_note_to_them')}</label>
            <textarea
              id="ps-note"
              maxLength={NOTE_MAX}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </>
      )}
      <div className="button-row">
        <button
          type="button"
          className="btn btn-primary btn-money"
          disabled={!canConfirm || busy}
          onClick={() =>
            received &&
            onConfirm(
              {
                received_amount: received.wire,
                shortfall_disposition: short ? disposition : null,
                note: note.trim() || null,
                correcting: false,
              },
              t('payments_approved', received.format(), name),
            )
          }
        >
          {received ? t('verify_partial_confirm', received.format()) : t('verify_approve')}
        </button>
        <button type="button" className="btn btn-text btn-money" onClick={onClose}>
          {t('action_cancel')}
        </button>
      </div>
    </Sheet>
  )
}

function RejectSheet({
  review,
  busy,
  onClose,
  onConfirm,
}: {
  review: PaymentReview
  busy: boolean
  onClose: () => void
  onConfirm: (note: string) => void
}) {
  const { t } = useT()
  const [note, setNote] = useState('')
  return (
    <Sheet title={t('verify_reject_title')} onClose={onClose}>
      <p className="meta">
        {t('verify_reject_body', reviewName(review), review.totalAmount.format())}
      </p>
      <div className="field">
        <label htmlFor="rs-note">{t('verify_reject_reason')}</label>
        <textarea
          id="rs-note"
          maxLength={NOTE_MAX}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <span className="help">{t('verify_reject_reason_count', note.length, NOTE_MAX)}</span>
      </div>
      <p className="meta">{t('verify_rejected_help')}</p>
      <div className="button-row">
        <button
          type="button"
          className="btn btn-danger btn-money"
          disabled={busy}
          onClick={() => onConfirm(note.trim())}
        >
          {t('verify_reject')}
        </button>
        <button type="button" className="btn btn-text btn-money" onClick={onClose}>
          {t('action_cancel')}
        </button>
      </div>
    </Sheet>
  )
}
