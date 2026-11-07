/**
 * S3 · Send money, for a student and for a guardian (Android `PayScreen`).
 *
 * Three steps, as Android has them: choose how to pay (one of the
 * teacher's methods, or cash in hand), fill in the form, see it sent.
 * The seat in the URL only chooses where the screen opens; every batch
 * the reader can pay for is offered, and a guardian with two children in
 * one batch pays for both at once.
 *
 * **What is owed is the server's figure** (`/v1/payments/owed`), and it
 * only fills the amount field; the person can send any amount. Nothing
 * here adds, subtracts or compares money [TC-9]. The send button exists
 * only on freshly loaded data and while online, and a retry of the same
 * payment reuses its mutation id so a lost response can never record the
 * money twice. There is no offline queue [D-9].
 */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import type { Schemas } from '../../../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../../../api/errors'
import { formatPhone, formatShortDate } from '../../../core/format'
import { Money } from '../../../core/money'
import { useOnline } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, FeeChip, Loading, TopBar } from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { familyPaths, type Reader } from '../reader'
import {
  readGuardianHome,
  readMySeats,
  readOwedTogether,
  readSeatMethods,
  submitPayment,
} from './api'
import {
  attemptFor,
  childPayBatches,
  dhakaToday,
  initialBatch,
  initialSelection,
  joinNames,
  myPayBatches,
  outcomeOf,
  requestOf,
  suggestedAmount,
  toggleSeat,
  type PayBatch,
  type PayChoice,
  type PayForm,
  type PaymentAttempt,
  type SentOutcome,
} from './mappers'
import './pay.css'

interface Scope {
  batches: PayBatch[]
  batch: PayBatch
  selected: string[]
  methods: Schemas['PaymentMethodResponse'][]
  teacherName: string | null
}

type Step =
  | { step: 'loading' }
  | { step: 'failed'; error: ApiError }
  | { step: 'none' }
  | { step: 'methods'; scope: Scope }
  | { step: 'form'; scope: Scope; choice: PayChoice }
  | {
      step: 'sent'
      scope: Scope
      choice: PayChoice
      payment: Schemas['PaymentSubmittedResponse']
      reference: string | null
      outcome: SentOutcome
    }

function asApiError(e: unknown): ApiError {
  if (!(e instanceof ApiError)) console.error(e)
  return e instanceof ApiError ? e : new ApiError(0, 'UNEXPECTED', UNEXPECTED_KEY, true)
}

const newId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`

export function PayScreen({ reader }: { reader: Reader }) {
  const { seat = '' } = useParams()
  const { t } = useT()
  const [step, setStep] = useState<Step>({ step: 'loading' })
  const [nonce, setNonce] = useState(0)

  const scopeFor = useCallback(
    async (batches: PayBatch[], batch: PayBatch, selected: string[]): Promise<Scope> => {
      const first = batch.seats[0]?.enrollmentId ?? ''
      const methods = await readSeatMethods(reader, first)
      return {
        batches,
        batch,
        selected,
        methods: methods.methods,
        teacherName: methods.teacher_display_name ?? batch.teacherName,
      }
    },
    [reader],
  )

  useEffect(() => {
    let live = true
    setStep({ step: 'loading' })
    ;(async () => {
      const batches =
        reader === 'me'
          ? myPayBatches(await readMySeats())
          : childPayBatches(await readGuardianHome())
      const batch = initialBatch(batches, seat)
      if (!batch) return { step: 'none' } as const
      return {
        step: 'methods',
        scope: await scopeFor(batches, batch, initialSelection(batch, seat)),
      } as const
    })().then(
      (next) => live && setStep(next),
      (e: unknown) => live && setStep({ step: 'failed', error: asApiError(e) }),
    )
    return () => {
      live = false
    }
  }, [reader, seat, scopeFor, nonce])

  const chooseBatch = async (key: string, keepChoice: PayChoice | null) => {
    if (step.step !== 'methods' && step.step !== 'form') return
    const batch = step.scope.batches.find((b) => b.key === key)
    if (!batch || batch.key === step.scope.batch.key) return
    try {
      const scope = await scopeFor(step.scope.batches, batch, initialSelection(batch, null))
      // Keep the chosen method only when this batch's teacher offers the same one.
      const same =
        keepChoice?.kind === 'method'
          ? scope.methods.find((m) => m.method_id === keepChoice.method.method_id)
          : null
      if (keepChoice?.kind === 'cash') setStep({ step: 'form', scope, choice: keepChoice })
      else if (same) setStep({ step: 'form', scope, choice: { kind: 'method', method: same } })
      else setStep({ step: 'methods', scope })
    } catch (e) {
      setStep({ step: 'failed', error: asApiError(e) })
    }
  }

  const close = reader === 'me' ? '/my-batches' : familyPaths.payments('child', seat)
  const title =
    step.step === 'sent'
      ? t('pay_sent_title')
      : step.step === 'form' && step.choice.kind === 'method'
        ? step.choice.method.kind === 'bank'
          ? t('pay_bank_title')
          : t('pay_mobile_title', step.choice.method.provider ?? '')
        : step.step === 'form'
          ? t('pay_cash')
          : t('pay_title')

  let body: React.ReactNode
  switch (step.step) {
    case 'loading':
      body = <Loading rows={3} />
      break
    case 'failed':
      body = (
        <ErrorCard
          title={t('pay_title')}
          error={step.error}
          onRetry={() => setNonce((n) => n + 1)}
        />
      )
      break
    case 'none':
      body = <EmptyState title={t('pay_nothing_title')} body={t('pay_nothing_body')} />
      break
    case 'methods':
      body = (
        <MethodsStep
          scope={step.scope}
          onBatch={(key) => void chooseBatch(key, null)}
          onChoose={(choice) => setStep({ step: 'form', scope: step.scope, choice })}
        />
      )
      break
    case 'form':
      body = (
        <FormStep
          key={`${step.scope.batch.key}|${step.choice.kind === 'method' ? step.choice.method.method_id : 'cash'}`}
          scope={step.scope}
          choice={step.choice}
          onBatch={(key) => void chooseBatch(key, step.choice)}
          onScope={(scope) => setStep({ ...step, scope })}
          onBack={() => setStep({ step: 'methods', scope: step.scope })}
          onSent={(payment, reference) =>
            setStep({
              step: 'sent',
              scope: step.scope,
              choice: step.choice,
              payment,
              reference,
              outcome: outcomeOf(payment.status),
            })
          }
        />
      )
      break
    case 'sent':
      body = <SentStep step={step} close={close} />
      break
  }

  return (
    <>
      <TopBar title={title} back={step.step === 'sent' ? close : true} />
      <div className="form-page">{body}</div>
    </>
  )
}

// -------------------------------------------------------------- step 1

function BatchPicker({ scope, onBatch }: { scope: Scope; onBatch: (key: string) => void }) {
  const { t } = useT()
  return (
    <div className="field">
      <span className="label">{t('pay_batch')}</span>
      {scope.batches.length === 1 ? (
        <div className="title">{scope.batch.name}</div>
      ) : (
        <div className="pay-batches" role="radiogroup" aria-label={t('pay_batch')}>
          {scope.batches.map((b) => (
            <button
              key={b.key}
              type="button"
              role="radio"
              aria-checked={b.key === scope.batch.key}
              className="pay-batch"
              onClick={() => onBatch(b.key)}
            >
              <span className="title">{b.name}</span>
              {b.seats.some((s) => s.childName) ? (
                <span className="meta">
                  {b.seats
                    .map((s) => s.childName)
                    .filter(Boolean)
                    .join(', ')}
                </span>
              ) : null}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MethodsStep({
  scope,
  onBatch,
  onChoose,
}: {
  scope: Scope
  onBatch: (key: string) => void
  onChoose: (choice: PayChoice) => void
}) {
  const { t } = useT()
  const mobile = scope.methods.filter((m) => m.kind === 'mobile')
  const bank = scope.methods.filter((m) => m.kind === 'bank')
  return (
    <div className="card">
      <BatchPicker scope={scope} onBatch={onBatch} />
      <h2 className="pay-heading">{t('pay_choose_heading')}</h2>
      <p className="meta" style={{ marginTop: 0 }}>
        {scope.teacherName ? t('pay_choose_sub', scope.teacherName) : t('pay_choose_sub_unnamed')}
      </p>
      {mobile.length > 0 ? <div className="label pay-group">{t('pay_group_mobile')}</div> : null}
      {mobile.map((m) => (
        <MethodRow
          key={m.method_id}
          title={m.provider ?? ''}
          detail={m.mobile_number ? formatPhone(m.mobile_number) : ''}
          onClick={() => onChoose({ kind: 'method', method: m })}
        />
      ))}
      {bank.length > 0 ? <div className="label pay-group">{t('pay_group_bank')}</div> : null}
      {bank.map((m) => (
        <MethodRow
          key={m.method_id}
          title={m.provider ?? ''}
          detail={m.branch_name ?? ''}
          onClick={() => onChoose({ kind: 'method', method: m })}
        />
      ))}
      <div className="label pay-group" aria-hidden="true" />
      <MethodRow
        title={t('pay_cash')}
        detail={t('pay_cash_hint')}
        onClick={() => onChoose({ kind: 'cash' })}
      />
      {scope.methods.length === 0 ? (
        <p className="meta" style={{ marginBottom: 0 }}>
          {t('pay_no_methods')}
        </p>
      ) : null}
    </div>
  )
}

function MethodRow({
  title,
  detail,
  onClick,
}: {
  title: string
  detail: string
  onClick: () => void
}) {
  return (
    <button type="button" className="pay-method" onClick={onClick}>
      <span className="grow">
        <span className="title">{title}</span>
        {detail ? <span className="meta">{detail}</span> : null}
      </span>
      <span aria-hidden="true" className="pay-method-chevron">
        ›
      </span>
    </button>
  )
}

// -------------------------------------------------------------- step 2

function Destination({ method }: { method: Schemas['PaymentMethodResponse'] }) {
  const { t } = useT()
  const [copied, setCopied] = useState(false)
  const bank = method.kind === 'bank'
  const number = (bank ? method.account_number : method.mobile_number) ?? ''
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(number)
      setCopied(true)
    } catch {
      // No clipboard permission: the number is on screen to copy by hand.
    }
  }
  return (
    <div className="pay-destination">
      {bank ? (
        <dl className="kv" style={{ marginTop: 0 }}>
          {method.provider ? (
            <>
              <dt>{t('pay_bank_name')}</dt>
              <dd>{method.provider}</dd>
            </>
          ) : null}
          {method.branch_name ? (
            <>
              <dt>{t('pay_branch')}</dt>
              <dd>{method.branch_name}</dd>
            </>
          ) : null}
          {method.account_name ? (
            <>
              <dt>{t('pay_account_name')}</dt>
              <dd>{method.account_name}</dd>
            </>
          ) : null}
        </dl>
      ) : (
        <div className="meta">{t('pay_send_to')}</div>
      )}
      <div className="pay-number-row">
        <div className="grow">
          {bank ? <div className="meta">{t('pay_account_no')}</div> : null}
          <div className="pay-number">{bank ? number : formatPhone(number)}</div>
          {!bank && (method.provider || method.account_name) ? (
            <div className="meta">
              {[method.provider, method.account_name].filter(Boolean).join(' · ')}
            </div>
          ) : null}
        </div>
        {number ? (
          <button type="button" className="btn btn-text btn-small" onClick={() => void copy()}>
            {copied ? t('web_pay_copied') : t('pay_copy')}
          </button>
        ) : null}
      </div>
      {method.note ? (
        <p className="meta" style={{ marginBottom: 0 }}>
          {method.note}
        </p>
      ) : null}
    </div>
  )
}

function FormStep({
  scope,
  choice,
  onBatch,
  onScope,
  onBack,
  onSent,
}: {
  scope: Scope
  choice: PayChoice
  onBatch: (key: string) => void
  onScope: (scope: Scope) => void
  onBack: () => void
  onSent: (payment: Schemas['PaymentSubmittedResponse'], reference: string | null) => void
}) {
  const { t, message } = useT()
  const online = useOnline()
  const [form, setForm] = useState<PayForm>(() => ({
    amount: '',
    paidOn: dhakaToday(),
    transactionId: '',
    fromAccount: '',
    note: '',
  }))
  const [owed, setOwed] = useState<Schemas['OwedTogetherResponse'] | null>(null)
  // The exam or other fee this payment is for; null is the monthly fee.
  const [forFee, setForFee] = useState<string | null>(null)
  // Kept from the monthly read so the choice stays on screen while a fee's
  // own figure is being read.
  const [feeOptions, setFeeOptions] = useState<Schemas['ExtraFeeRefResponse'][]>([])
  const [sending, setSending] = useState(false)
  const [failed, setFailed] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState<PaymentAttempt | null>(null)
  const kind = choice.kind === 'method' ? choice.method.kind : 'cash'
  const provider = choice.kind === 'method' ? (choice.method.provider ?? '') : ''
  const selectedKey = scope.selected.join(',')

  // What the chosen seats owe together, from the server. Re-read whenever
  // the choice of seats changes; it fills the amount only while the field
  // is empty or still shows the previous suggestion.
  const owedRef = useRef<Schemas['OwedTogetherResponse'] | null>(null)
  useEffect(() => {
    let live = true
    setOwed(null)
    readOwedTogether(selectedKey.split(','), forFee).then(
      (o) => {
        if (!live) return
        if (forFee === null) setFeeOptions(o.extra_fee_options ?? [])
        const previous = owedRef.current
        const before = previous ? suggestedAmount(Money.fromWire(previous.owed_together)) : ''
        owedRef.current = o
        setOwed(o)
        setForm((f) =>
          f.amount === '' || f.amount === before
            ? { ...f, amount: suggestedAmount(Money.fromWire(o.owed_together)) }
            : f,
        )
      },
      () => {
        // The owed line is a convenience; without it the form still works.
      },
    )
    return () => {
      live = false
    }
  }, [selectedKey, forFee])

  // A different set of children may not share the chosen fee.
  useEffect(() => {
    setForFee(null)
  }, [selectedKey])

  const { request, problem } = useMemo(
    () => requestOf(scope.selected, choice, form, forFee),
    [scope.selected, choice, form, forFee],
  )
  const set = (k: keyof PayForm) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  async function send(e: FormEvent) {
    e.preventDefault()
    if (!request || sending || !online) return
    const next = attemptFor(attempt, request, newId)
    setAttempt(next)
    setSending(true)
    setFailed(null)
    try {
      const payment = await submitPayment({ ...request, client_mutation_id: next.clientMutationId })
      onSent(payment, request.transaction_id ?? request.from_account ?? null)
    } catch (err) {
      setFailed(asApiError(err))
      setSending(false)
    }
  }

  const owedNames = owed
    ? joinNames(
        owed.children.map((c) => c.display_name),
        t('pay_and'),
      )
    : ''
  const owedTogether = owed ? Money.fromWire(owed.owed_together) : null
  const typedAmount = form.amount === '' ? null : Money.fromTyped(form.amount)

  return (
    <form className="card" onSubmit={(e) => void send(e)} noValidate>
      {choice.kind === 'method' ? (
        <Destination method={choice.method} />
      ) : (
        <p className="meta" style={{ marginTop: 0 }}>
          {t('pay_cash_help')}
        </p>
      )}
      <button type="button" className="btn btn-text btn-small pay-change" onClick={onBack}>
        {t('auth_change')}
      </button>

      <BatchPicker scope={scope} onBatch={onBatch} />
      <ForField
        scope={scope}
        onToggle={(s) =>
          onScope({ ...scope, selected: toggleSeat(scope.batch, scope.selected, s) })
        }
      />

      {feeOptions.length > 0 ? (
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend>{t('pay_for_question')}</legend>
          <div className="list" role="radiogroup" aria-label={t('pay_for_question')}>
            {[null, ...feeOptions].map((fee) => (
              <label
                key={fee?.extra_fee_id ?? 'monthly'}
                className="row"
                style={{ cursor: 'pointer' }}
              >
                <input
                  type="radio"
                  name="pay-for"
                  checked={forFee === (fee?.extra_fee_id ?? null)}
                  onChange={() => setForFee(fee?.extra_fee_id ?? null)}
                />
                <span className="grow">
                  <span className="title">{fee ? fee.label : t('payment_for_monthly')}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      {owed && owedTogether ? (
        <p className="meta" role="status">
          {owedTogether.isZero()
            ? t('pay_owed_nothing', owedNames)
            : t('pay_owed_for', owedNames, owedTogether.format())}
        </p>
      ) : null}

      {kind === 'mobile' ? (
        <div className="field">
          <label htmlFor="pay-txn">{t('pay_txn_label')}</label>
          <input
            id="pay-txn"
            className="mono"
            autoComplete="off"
            autoCapitalize="characters"
            value={form.transactionId}
            onChange={set('transactionId')}
            aria-invalid={problem === 'transaction_id_short' || undefined}
            aria-describedby="pay-txn-help"
          />
          {problem === 'transaction_id_short' ? (
            <span id="pay-txn-help" className="field-error">
              {t('pay_txn_short', provider)}
            </span>
          ) : (
            <span id="pay-txn-help" className="help">
              {t('pay_mobile_help', provider)}
            </span>
          )}
        </div>
      ) : null}
      {kind === 'bank' ? (
        <div className="field">
          <label htmlFor="pay-from">{t('pay_from_account')}</label>
          <input id="pay-from" value={form.fromAccount} onChange={set('fromAccount')} />
          <span className="help">{t('pay_bank_help')}</span>
        </div>
      ) : null}

      <div className="field">
        <label htmlFor="pay-amount">{t('pay_amount')}</label>
        <input
          id="pay-amount"
          inputMode="decimal"
          value={form.amount}
          onChange={set('amount')}
          aria-invalid={(form.amount !== '' && typedAmount === null) || undefined}
        />
        {form.amount !== '' && typedAmount === null ? (
          <span className="field-error">{t('fee_invalid')}</span>
        ) : null}
      </div>
      <div className="field">
        <label htmlFor="pay-date">{t('pay_date')}</label>
        <input
          id="pay-date"
          type="date"
          max={dhakaToday()}
          value={form.paidOn}
          onChange={set('paidOn')}
        />
      </div>
      <div className="field">
        <label htmlFor="pay-note">{t('pay_note')}</label>
        <textarea id="pay-note" maxLength={500} value={form.note} onChange={set('note')} />
      </div>

      {failed ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          <WarningIcon />
          <div>
            {failed.offline ? (
              <>
                <strong>{t('pay_offline_title')}</strong> {t('pay_offline_body')}
              </>
            ) : (
              message(failed.messageKey, failed.details)
            )}
          </div>
        </div>
      ) : null}

      <div className="action-bar">
        <button
          type="submit"
          className="btn btn-primary btn-money"
          disabled={!request || sending || !online}
        >
          {!online ? t('pay_needs_connection') : sending ? t('pay_sending') : t('pay_send')}
        </button>
      </div>
    </form>
  )
}

/** Who the money is for. A guardian with two children in one batch chooses. */
function ForField({ scope, onToggle }: { scope: Scope; onToggle: (seat: string) => void }) {
  const { t } = useT()
  const seats = scope.batch.seats
  if (seats.length <= 1) {
    return (
      <div className="field">
        <span className="label">{t('pay_for')}</span>
        <div className="title">{seats[0]?.childName ?? t('pay_for_self')}</div>
      </div>
    )
  }
  return (
    <fieldset className="field">
      <legend>{t('pay_for')}</legend>
      <div className="chips">
        {seats.map((s) => (
          <button
            key={s.enrollmentId}
            type="button"
            className="chip chip-filter"
            aria-pressed={scope.selected.includes(s.enrollmentId)}
            onClick={() => onToggle(s.enrollmentId)}
          >
            {s.childName ?? t('pay_for_self')}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

// -------------------------------------------------------------- step 3

function SentStep({ step, close }: { step: Extract<Step, { step: 'sent' }>; close: string }) {
  const { t, lang } = useT()
  const teacher = step.scope.teacherName ?? t('pay_teacher_fallback')
  const amount = Money.fromWire(step.payment.total_amount).format()
  const names = joinNames(
    [...new Set(step.payment.claims.map((c) => c.display_name))],
    t('pay_and'),
  )
  let body: string
  if (step.outcome === 'approved') body = t('pay_recorded_body_approved', amount, teacher)
  else if (step.outcome === 'rejected') body = t('pay_recorded_body_rejected', amount, teacher)
  else if (step.choice.kind === 'cash') body = t('pay_sent_body_cash', teacher, amount)
  else if (step.choice.method.kind === 'bank')
    body = t('pay_sent_body_bank', teacher, amount, step.reference ?? '')
  else
    body = t(
      'pay_sent_body_mobile',
      teacher,
      amount,
      step.choice.method.provider ?? '',
      step.reference ?? '',
    )
  const status =
    step.outcome === 'approved'
      ? t('inbox_outcome_approved')
      : step.outcome === 'rejected'
        ? t('inbox_outcome_rejected')
        : t('pay_pending')

  return (
    <>
      <div className="card" role="status">
        {step.outcome === 'pending' ? <FeeChip chip={{ kind: 'verifying', amount: null }} /> : null}
        {step.outcome === 'approved' ? (
          <FeeChip chip={{ kind: 'paid', label: t('inbox_outcome_approved') }} />
        ) : null}
        {step.outcome !== 'pending' ? (
          <h2 className="pay-heading">{t('pay_recorded_title')}</h2>
        ) : null}
        <p className="pay-sent-body">{body}</p>
        <dl className="kv">
          <dt>{t('pay_for')}</dt>
          <dd>{t('pay_for_line', names, step.scope.batch.name)}</dd>
          <dt>{t('pay_amount_row')}</dt>
          <dd className="amount">{amount}</dd>
          <dt>{t('pay_paid_on_row')}</dt>
          <dd>{formatShortDate(step.payment.paid_on, lang)}</dd>
          {step.reference ? (
            <>
              <dt>{t('verify_transaction_id')}</dt>
              <dd className="mono">{step.reference}</dd>
            </>
          ) : null}
          <dt>{t('pay_status_row')}</dt>
          <dd>{status}</dd>
        </dl>
        {step.outcome === 'pending' ? (
          <p className="meta" style={{ marginBottom: 0 }}>
            {t('pay_until_verified')}
          </p>
        ) : null}
      </div>
      <div className="action-bar">
        <Link className="btn btn-primary btn-money" to={close}>
          {t('pay_done')}
        </Link>
      </div>
    </>
  )
}
