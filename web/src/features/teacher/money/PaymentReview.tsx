/**
 * One payment: everything the teacher needs to decide it, the decision,
 * and — once decided — "Change decision…", which re-opens the controls and
 * sends `correcting: true` (`PaymentReviewScreen.kt`).
 *
 * **Controls appear only on a freshly loaded payment.** A refresh that
 * failed keeps the facts on screen and hides every decision button, and
 * a decision someone else recorded meanwhile (`PAYMENT_ALREADY_DECIDED`)
 * re-reads the payment and says so rather than overwriting it.
 *
 * `?act=approve` (from a queue card's "Approve ৳800…" or "Partial") opens
 * the approval sheet on arrival and `?act=reject` the rejection; neither
 * sends anything without the teacher's own click.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router'
import type { Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { ago, formatMonth, formatPhone, formatShortDate, initial } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  Avatar,
  ErrorCard,
  Loading,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { reviewName } from '../mappers'
import { paths } from '../paths'
import { readPayment, approvePayment, rejectPayment } from './api'
import { ApprovalSheet } from './ApprovalSheet'
import { ComparisonChip } from './ComparisonChip'
import { formatDateTime } from './format'
import {
  ALREADY_DECIDED_CODE,
  REVIEW_NOTE_MAX,
  asReportedBody,
  canDecide,
  mapPaymentDetail,
  openSheet,
  purposeFields,
  rejectionBody,
  samePurpose,
  type PaymentDetail,
  type PaymentFor,
  type SheetInput,
} from './review'

export function PaymentReviewScreen() {
  const { submissionId = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const { t, message } = useT()
  // 'monthly' or a fee id while the teacher is trying another purpose;
  // the server measures the payment against it and writes nothing.
  const [preview, setPreview] = useState<string | null>(null)
  const { resource, reload } = useResource(
    () => readPayment(submissionId, preview).then(mapPaymentDetail),
    [submissionId, preview],
  )
  // The payment as the last write returned it, until the next read.
  const [written, setWritten] = useState<PaymentDetail | null>(null)
  const [correcting, setCorrecting] = useState(false)
  const [note, setNote] = useState('')
  const [sheet, setSheet] = useState<SheetInput | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errorText, setErrorText] = useState<string | null>(null)
  const [snack, setSnack] = useState<string | null>(null)
  const dismissSnack = useCallback(() => setSnack(null), [])

  const loaded = resource.state === 'loaded' ? resource : null
  const detail = written ?? loaded?.data ?? null
  const fresh = loaded !== null && loaded.error === null && !loaded.refreshing
  const deciding = detail !== null && fresh && canDecide(detail, correcting)

  // A new read replaces whatever the last write returned.
  useEffect(() => {
    setWritten(null)
  }, [loaded?.loadedAt])

  // Arriving with ?act= opens the matching control once, never sends.
  const act = search.get('act')
  useEffect(() => {
    if (!act || !detail || !deciding) return
    if (act === 'approve') setSheet(openSheet(detail, note))
    if (act === 'reject') setRejecting(true)
    setSearch({}, { replace: true })
  }, [act, detail, deciding, note, setSearch])

  async function write(
    send: () => Promise<Schemas['PaymentReviewResponse']>,
    done: (d: PaymentDetail) => string,
  ) {
    setBusy(true)
    setErrorText(null)
    try {
      const decided = mapPaymentDetail(await send())
      setWritten(decided)
      setSheet(null)
      setRejecting(false)
      setCorrecting(false)
      setNote('')
      setPreview(null)
      setSnack(done(decided))
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setErrorText(
        error?.offline ? t('web_verify_offline') : message(error?.messageKey ?? 'error.unexpected'),
      )
      if (error?.code === ALREADY_DECIDED_CODE) {
        setSheet(null)
        setRejecting(false)
        setCorrecting(false)
        reload()
      }
    } finally {
      setBusy(false)
    }
  }

  const approve = (d: PaymentDetail) => {
    const body = asReportedBody(d, note, correcting)
    if (body) {
      void write(
        () => approvePayment(d.submissionId, { ...body, ...purposeFields(preview) }),
        (x) => t('payments_approved', x.totalAmount.format(), reviewName(x)),
      )
    } else {
      setErrorText(null)
      setSheet(openSheet(d, note))
    }
  }

  const decided = detail !== null && detail.status !== 'pending'
  const title = decided ? t('verify_detail_title_decided') : t('verify_detail_title')

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={title} subtitle={t('verify_checking')} back={paths.verify()} />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed' || !detail) {
    return (
      <>
        <TopBar title={title} back={paths.verify()} />
        {resource.state === 'failed' ? (
          <ErrorCard
            title={t('verify_detail_load_failed')}
            error={resource.error}
            onRetry={reload}
          />
        ) : null}
      </>
    )
  }

  return (
    <>
      <TopBar title={title} back={paths.verify()} />
      {loaded?.error ? <StaleBanner error={loaded.error} loadedAt={loaded.loadedAt} /> : null}
      {errorText ? (
        <div className="banner error" role="alert" style={{ marginBottom: 12 }}>
          <WarningIcon />
          <span>{errorText}</span>
        </div>
      ) : null}

      <div className="money-detail">
        <Summary detail={detail} />
        <Facts detail={detail} />
        {detail.duplicateOf ? (
          <Duplicate detail={detail} />
        ) : (
          <p className="meta">{t('verify_no_duplicate')}</p>
        )}

        {deciding && (detail.options.length > 0 || detail.requested !== null) ? (
          <PurposeCard
            detail={detail}
            busy={busy || resource.state !== 'loaded' || loaded?.refreshing === true}
            onChoose={(choice) => {
              setErrorText(null)
              setPreview(choice?.id ?? 'monthly')
            }}
          />
        ) : null}

        {deciding ? (
          <div className="card">
            <div className="field" style={{ marginTop: 0 }}>
              <label htmlFor="review-note">{t('verify_note_to_them')}</label>
              <textarea
                id="review-note"
                maxLength={REVIEW_NOTE_MAX}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn btn-text"
              style={{ marginTop: 8, paddingLeft: 0 }}
              disabled={busy}
              onClick={() => {
                setErrorText(null)
                setSheet(openSheet(detail, note))
              }}
            >
              {t('verify_approve_other')}
            </button>
            {detail.duplicateOf ? (
              // A reused transaction ID turns the defaults round: rejecting
              // is the filled, likely choice; approving is deliberate.
              <div className="button-row money-stack">
                <button
                  type="button"
                  className="btn btn-danger-filled btn-money"
                  disabled={busy}
                  onClick={() => setRejecting(true)}
                >
                  {t('verify_reject_duplicate')}
                </button>
                <button
                  type="button"
                  className="btn btn-outline btn-money"
                  disabled={busy}
                  onClick={() => approve(detail)}
                >
                  {t('verify_approve_anyway')}
                </button>
              </div>
            ) : (
              <div className="button-row">
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={busy}
                  onClick={() => setRejecting(true)}
                >
                  {t('verify_reject')}
                </button>
                <button
                  type="button"
                  className="btn btn-primary grow"
                  disabled={busy}
                  onClick={() => approve(detail)}
                >
                  {t('verify_approve')}
                </button>
              </div>
            )}
          </div>
        ) : decided ? (
          <>
            <Decision detail={detail} />
            {fresh ? (
              <button
                type="button"
                className="btn btn-outline btn-money"
                onClick={() => {
                  setErrorText(null)
                  setCorrecting(true)
                }}
              >
                {t('verify_change_decision')}
              </button>
            ) : null}
          </>
        ) : null}
      </div>

      {sheet ? (
        <ApprovalSheet
          review={detail}
          initial={sheet}
          correcting={correcting}
          busy={busy}
          errorText={errorText}
          onClose={() => setSheet(null)}
          onConfirm={(body, received) =>
            void write(
              () => approvePayment(detail.submissionId, { ...body, ...purposeFields(preview) }),
              (x) => t('payments_approved', received, reviewName(x)),
            )
          }
        />
      ) : null}

      {rejecting ? (
        <RejectSheet
          detail={detail}
          note={note}
          busy={busy}
          onClose={() => setRejecting(false)}
          onConfirm={(text) =>
            void write(
              () => rejectPayment(detail.submissionId, rejectionBody(text, correcting)),
              (x) => t('web_verify_rejected', reviewName(x)),
            )
          }
        />
      ) : null}

      {snack ? <Snackbar text={snack} onDismiss={dismissSnack} /> : null}
    </>
  )
}

/** The label one "payment for" choice reads as. */
function useForLabel(): (choice: PaymentFor) => string {
  const { t } = useT()
  return (choice) => choice?.label ?? t('payment_for_monthly')
}

/**
 * "Payment for": the monthly fee and every extra fee each covered child
 * was charged. Choosing one re-reads the payment measured against it, so
 * "matches" or "short" is always the server's answer for what is chosen.
 */
function PurposeCard({
  detail,
  busy,
  onChoose,
}: {
  detail: PaymentDetail
  busy: boolean
  onChoose: (choice: PaymentFor) => void
}) {
  const { t, lang } = useT()
  const label = useForLabel()
  const choices: PaymentFor[] = [null, ...detail.options]
  return (
    <fieldset className="card" style={{ border: undefined }}>
      <legend className="label">{t('payment_for_title')}</legend>
      <div className="list" role="radiogroup" aria-label={t('payment_for_title')}>
        {choices.map((choice) => {
          const on = samePurpose(choice, detail.appliedTo)
          return (
            <label key={choice?.id ?? 'monthly'} className="row" style={{ cursor: 'pointer' }}>
              <input
                type="radio"
                name="payment-for"
                checked={on}
                disabled={busy}
                onChange={() => onChoose(choice)}
              />
              <span className="grow">
                <span className="title">{label(choice)}</span>
                {choice ? (
                  <span className="meta">
                    {' '}
                    · {t('extra_fees_due', formatShortDate(choice.dueOn, lang))}
                  </span>
                ) : null}
              </span>
              {samePurpose(choice, detail.requested) ? (
                <span className="chip chip-neutral">{t('payment_for_family_chose')}</span>
              ) : null}
            </label>
          )
        })}
      </div>
      {samePurpose(detail.appliedTo, detail.requested) ? null : (
        <p className="meta" role="status">
          {t('payment_for_changed', label(detail.appliedTo), label(detail.requested))}
        </p>
      )}
    </fieldset>
  )
}

function StatusChip({ status }: { status: PaymentDetail['status'] }) {
  const { t } = useT()
  if (status === 'approved')
    return <span className="chip chip-paid">{t('verify_decision_approved')}</span>
  if (status === 'rejected')
    return <span className="chip chip-due">{t('verify_decision_rejected')}</span>
  return <span className="chip chip-verifying">{t('verify_decision_pending')}</span>
}

function Summary({ detail }: { detail: PaymentDetail }) {
  const { t, lang } = useT()
  const label = useForLabel()
  const name = reviewName(detail)
  const forLine =
    detail.appliedTo === null && detail.requested === null
      ? null
      : samePurpose(detail.appliedTo, detail.requested)
        ? t('payment_for_applied', label(detail.appliedTo))
        : t('payment_for_applied_instead', label(detail.appliedTo), label(detail.requested))
  return (
    <section className="card" aria-label={name}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <Avatar letter={initial(name)} />
        <div className="grow">
          <div className="title">{name}</div>
          <div className="meta">{detail.batchName}</div>
          {forLine ? <div className="meta">{forLine}</div> : null}
        </div>
        <StatusChip status={detail.status} />
      </div>
      <div className="hero-amount" style={{ marginTop: 12 }}>
        {detail.totalAmount.format()}
      </div>
      <ComparisonChip review={detail} />
      <dl className="money-lines" style={{ marginTop: 12 }}>
        {detail.children.map((c) => {
          const approved = detail.approved[c.enrollmentId]
          return (
            <div key={c.enrollmentId}>
              <dt>{t('verify_child_line', c.displayName, formatMonth(c.period, lang))}</dt>
              <dd className="amount">
                {c.owed.format()}
                {approved && detail.status === 'approved' ? (
                  <span className="meta">
                    {' '}
                    · {t('web_money_approved_amount', approved.format())}
                  </span>
                ) : null}
              </dd>
            </div>
          )
        })}
        <div className="money-lines-total">
          <dt>{t('verify_owed_together')}</dt>
          <dd className="amount">{detail.owedTogether.format()}</dd>
        </div>
      </dl>
    </section>
  )
}

function Facts({ detail }: { detail: PaymentDetail }) {
  const { t, lang } = useT()
  const sender = detail.submitterPhone ? formatPhone(detail.submitterPhone) : null
  const provider = detail.method.provider ?? ''
  const method =
    detail.method.kind === 'mobile'
      ? t('verify_method_mobile', provider, formatPhone(detail.method.number ?? ''))
      : detail.method.kind === 'bank'
        ? t('verify_method_bank', provider, detail.method.number ?? '')
        : detail.method.kind === 'cash'
          ? t('verify_method_cash')
          : provider
  return (
    <section className="card">
      <dl className="kv" style={{ marginTop: 0 }}>
        {sender ? (
          <>
            <dt>{t('verify_sent_by')}</dt>
            <dd>
              {detail.submitterRole === 'guardian'
                ? t('verify_from_guardian', sender)
                : detail.submitterRole === 'student'
                  ? t('verify_from_student', sender)
                  : sender}
            </dd>
          </>
        ) : null}
        <dt>{t('verify_method')}</dt>
        <dd>{method}</dd>
        {detail.transactionId ? (
          <>
            <dt>{t('verify_transaction_id')}</dt>
            <dd className="mono">{detail.transactionId}</dd>
          </>
        ) : null}
        {detail.fromAccount ? (
          <>
            <dt>{t('verify_paid_from')}</dt>
            <dd>{detail.fromAccount}</dd>
          </>
        ) : null}
        <dt>{t('verify_paid_on')}</dt>
        <dd>{formatShortDate(detail.paidOn, lang)}</dd>
        <dt>{t('verify_submitted')}</dt>
        <dd>
          {formatDateTime(detail.submittedAt, lang)} · {ago(detail.submittedAt, new Date(), t)}
        </dd>
        {detail.payerNote ? (
          <>
            <dt>{t('verify_their_note')}</dt>
            <dd>{detail.payerNote}</dd>
          </>
        ) : null}
      </dl>
    </section>
  )
}

function Duplicate({ detail }: { detail: PaymentDetail }) {
  const { t, lang } = useT()
  const dup = detail.duplicateOf
  if (!dup) return null
  const decision = t(`verify_decision_${dup.status}`)
  return (
    <div className="banner error" role="note">
      <WarningIcon />
      <div>
        <strong>{t('verify_duplicate_title')}</strong>{' '}
        {dup.decidedAt
          ? t(
              'verify_duplicate_body_dated',
              dup.displayName,
              decision,
              dup.amount.format(),
              formatShortDate(dup.decidedAt, lang),
            )
          : t('verify_duplicate_body', dup.displayName, decision, dup.amount.format())}
      </div>
    </div>
  )
}

function Decision({ detail }: { detail: PaymentDetail }) {
  const { t, lang } = useT()
  const rejected = detail.status === 'rejected'
  return (
    <section className="card">
      {detail.decidedAt ? (
        <div className="title">
          {t(
            rejected ? 'verify_decided_by_you_rejected' : 'verify_decided_by_you_approved',
            formatDateTime(detail.decidedAt, lang),
          )}
        </div>
      ) : null}
      {detail.decisionNote ? <p style={{ margin: '8px 0 0' }}>“{detail.decisionNote}”</p> : null}
      {rejected ? <p className="meta">{t('verify_rejected_help')}</p> : null}
    </section>
  )
}

function RejectSheet({
  detail,
  note,
  busy,
  onClose,
  onConfirm,
}: {
  detail: PaymentDetail
  note: string
  busy: boolean
  onClose: () => void
  onConfirm: (note: string) => void
}) {
  const { t } = useT()
  const [text, setText] = useState(note)
  return (
    <Sheet title={t('verify_reject_title')} onClose={onClose}>
      <p className="meta">
        {t('verify_reject_body', reviewName(detail), detail.totalAmount.format())}
      </p>
      <div className="field">
        <label htmlFor="reject-note">{t('verify_reject_reason')}</label>
        <textarea
          id="reject-note"
          maxLength={REVIEW_NOTE_MAX}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="help">
          {t('verify_reject_reason_count', text.length, REVIEW_NOTE_MAX)}
        </span>
      </div>
      <p className="meta">{t('verify_rejected_help')}</p>
      <div className="button-row">
        <button
          type="button"
          className="btn btn-danger btn-money"
          disabled={busy}
          onClick={() => onConfirm(text)}
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
