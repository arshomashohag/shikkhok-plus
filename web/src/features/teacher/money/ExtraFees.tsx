/**
 * Exam and other fees on one batch: the list, raising one, and one fee's
 * students with "Record payment" for money handed over in person.
 *
 * Every figure and every status is the server's (`extraFees.ts`). The raise
 * form offers exactly the students the server says a new fee would charge,
 * so it never lists someone the server would refuse.
 */
import { useCallback, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatShortDate } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  FeeChip,
  Loading,
  Snackbar,
  StaleBanner,
  TopBar,
  type FeeChipModel,
} from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { mutationId } from '../classes/api'
import { listExams } from '../exams/api'
import { paths } from '../paths'
import {
  FEE_LABEL_MAX,
  chargedCount,
  listExtraFees,
  mapFeeDetail,
  mapFeeSummary,
  openRaise,
  raiseBody,
  raiseExtraFee,
  readExtraFee,
  type FeeStudent,
  type FeeSummary,
  type RaiseInput,
  type SeatChoice,
} from './extraFees'
import { RecordPaymentSheet } from './RecordPaymentSheet'

/** The chip a student's charge shows, straight from the server's status. */
export function chargeChip(
  status: FeeStudent['status'],
  owed: FeeStudent['owed'],
  dueOn: string,
): FeeChipModel {
  switch (status) {
    case 'paid':
      return { kind: 'paid' }
    case 'partly_paid':
      return { kind: 'partial', left: owed }
    case 'waived':
      return { kind: 'waived' }
    case 'unpaid':
      return { kind: 'due', dueDate: dueOn }
  }
}

function FeeCard({ fee }: { fee: FeeSummary }) {
  const { t, lang } = useT()
  const settled = fee.owingCount === 0
  return (
    <li>
      <Link className="row" to={paths.extraFee(fee.id)}>
        <div className="grow">
          <div className="title">{fee.label}</div>
          <div className="meta">
            {fee.kind === 'exam' ? t('extra_fees_kind_exam') : t('extra_fees_kind_other')} ·{' '}
            {t('extra_fees_due', formatShortDate(fee.dueOn, lang))}
            {fee.examTitle ? ` · ${t('extra_fees_for_exam', fee.examTitle)}` : ''}
          </div>
          <div className="meta">
            {settled
              ? t('extra_fees_fully_paid')
              : t(
                  'extra_fees_counts',
                  fee.paidCount,
                  fee.studentCount,
                  fee.owingCount,
                  fee.owedTotal.format(),
                )}
          </div>
        </div>
        <div className="title" style={{ textAlign: 'right' }}>
          {t('extra_fees_collected', fee.collectedTotal.format(), fee.chargedTotal.format())}
        </div>
      </Link>
    </li>
  )
}

/** `/batches/:batchId/fees`: every fee raised on the batch, newest first. */
export function BatchExtraFees() {
  const { batchId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(
    () => listExtraFees(batchId).then((r) => r.fees.map(mapFeeSummary)),
    [batchId],
  )
  const raise = (
    <Link className="btn btn-primary" to={paths.extraFeeNew(batchId)}>
      {t('extra_fees_raise')}
    </Link>
  )
  return (
    <>
      <TopBar title={t('extra_fees_title')} back={paths.batch(batchId)} actions={raise} />
      {resource.state === 'loading' ? (
        <Loading />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={t('extra_fees_load_failed')} error={resource.error} onRetry={reload} />
      ) : (
        <>
          {resource.error ? (
            <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
          ) : null}
          {resource.data.length === 0 ? (
            <EmptyState title={t('extra_fees_title')} body={t('extra_fees_empty')} action={raise} />
          ) : (
            <ul className="card flush list">
              {resource.data.map((fee) => (
                <FeeCard key={fee.id} fee={fee} />
              ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}

function todayPlus(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** `/batches/:batchId/fees/new`: raise an exam or other fee. */
export function RaiseExtraFee() {
  const { batchId = '' } = useParams()
  const navigate = useNavigate()
  const { t, message } = useT()
  const { resource, reload } = useResource(
    () =>
      Promise.all([listExtraFees(batchId), listExams(batchId)]).then(([fees, exams]) => ({
        students: fees.chargeable_students ?? [],
        exams: exams.filter((e) => !e.cancelled && !e.published),
      })),
    [batchId],
  )
  const [input, setInput] = useState<RaiseInput>(() => openRaise(mutationId(), todayPlus(7)))
  const [busy, setBusy] = useState(false)
  const [errorText, setErrorText] = useState<string | null>(null)

  const studentIds = useMemo(
    () => (resource.state === 'loaded' ? resource.data.students.map((s) => s.enrollment_id) : []),
    [resource],
  )
  const body = raiseBody(input, studentIds)
  const count = chargedCount(input, studentIds)
  const set = (patch: Partial<RaiseInput>) => setInput((i) => ({ ...i, ...patch }))
  const choose = (id: string, choice: SeatChoice) =>
    setInput((i) => {
      const rest = Object.fromEntries(Object.entries(i.seats).filter(([key]) => key !== id))
      return { ...i, seats: choice === 'charge' ? rest : { ...rest, [id]: choice } }
    })

  async function submit() {
    if (!body) return
    setBusy(true)
    setErrorText(null)
    try {
      const fee = await raiseExtraFee(batchId, body)
      navigate(paths.extraFee(fee.extra_fee_id), {
        replace: true,
        state: { snack: t('extra_fees_raised', fee.label) },
      })
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setErrorText(
        error?.offline
          ? t('web_money_offline_nothing_changed')
          : message(error?.messageKey ?? 'error.unexpected'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <TopBar title={t('extra_fees_form_title')} back={paths.extraFees(batchId)} />
      {resource.state === 'loading' ? (
        <Loading />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={t('extra_fees_load_failed')} error={resource.error} onRetry={reload} />
      ) : (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <fieldset className="field" style={{ marginTop: 0, border: 0, padding: 0 }}>
            <legend>{t('extra_fees_form_kind')}</legend>
            <div className="chips" role="group">
              {(['exam', 'other'] as const).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className={`chip chip-filter${input.kind === kind ? ' selected' : ''}`}
                  aria-pressed={input.kind === kind}
                  onClick={() => set({ kind, examId: kind === 'exam' ? input.examId : '' })}
                >
                  {kind === 'exam' ? t('extra_fees_kind_exam') : t('extra_fees_kind_other')}
                </button>
              ))}
            </div>
          </fieldset>
          {input.kind === 'exam' ? (
            <div className="field">
              <label htmlFor="fee-exam">{t('extra_fees_form_exam')}</label>
              <select
                id="fee-exam"
                value={input.examId}
                onChange={(e) => set({ examId: e.target.value })}
              >
                <option value="">{t('extra_fees_form_no_exam')}</option>
                {resource.data.exams.map((exam) => (
                  <option key={exam.exam_id} value={exam.exam_id}>
                    {exam.title} · {exam.subject_name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="fee-label">{t('extra_fees_form_label')}</label>
            <input
              id="fee-label"
              maxLength={FEE_LABEL_MAX}
              value={input.label}
              onChange={(e) => set({ label: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="fee-amount">{t('extra_fees_form_amount')}</label>
            <input
              id="fee-amount"
              inputMode="decimal"
              value={input.typed}
              onChange={(e) => set({ typed: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="fee-due">{t('extra_fees_form_due')}</label>
            <input
              id="fee-due"
              type="date"
              value={input.dueOn}
              onChange={(e) => set({ dueOn: e.target.value })}
            />
          </div>
          <fieldset className="field" style={{ border: 0, padding: 0 }}>
            <legend>{t('extra_fees_form_students')}</legend>
            <ul className="list">
              {resource.data.students.map((s) => {
                const choice = input.seats[s.enrollment_id] ?? 'charge'
                return (
                  <li key={s.enrollment_id} className="row">
                    <div className="grow">{s.display_name}</div>
                    <label className="visually-hidden" htmlFor={`seat-${s.enrollment_id}`}>
                      {s.display_name}
                    </label>
                    <select
                      id={`seat-${s.enrollment_id}`}
                      value={choice}
                      onChange={(e) => choose(s.enrollment_id, e.target.value as SeatChoice)}
                    >
                      <option value="charge">{t('extra_fees_form_charge')}</option>
                      <option value="waive">{t('extra_fees_form_waive')}</option>
                      <option value="leave_out">{t('extra_fees_form_leave_out')}</option>
                    </select>
                  </li>
                )
              })}
            </ul>
          </fieldset>
          <p className="meta">{t('extra_fees_form_note')}</p>
          {errorText ? (
            <div className="banner error" role="alert">
              <WarningIcon />
              <span>{errorText}</span>
            </div>
          ) : null}
          <div className="button-row">
            <Link className="btn btn-outline" to={paths.extraFees(batchId)}>
              {t('action_cancel')}
            </Link>
            <button type="submit" className="btn btn-primary grow" disabled={!body || busy}>
              {t('extra_fees_raise_for', count)}
            </button>
          </div>
        </form>
      )}
    </>
  )
}

/** `/extra-fees/:feeId`: one fee's students, and recording cash against it. */
export function ExtraFeeDetail() {
  const { feeId = '' } = useParams()
  const { t, lang } = useT()
  const { resource, reload } = useResource(() => readExtraFee(feeId).then(mapFeeDetail), [feeId])
  const [recording, setRecording] = useState<FeeStudent | null>(null)
  // The raise form hands its "raised" message over on navigation.
  const raised = (useLocation().state as { snack?: string } | null)?.snack ?? null
  const [snack, setSnack] = useState<string | null>(raised)
  const dismiss = useCallback(() => setSnack(null), [])

  if (resource.state === 'loading') return <Loading />
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('extra_fees_title')} back />
        <ErrorCard title={t('extra_fees_load_failed')} error={resource.error} onRetry={reload} />
      </>
    )
  }
  const fee = resource.data
  return (
    <>
      <TopBar
        title={fee.label}
        subtitle={t('extra_fees_due', formatShortDate(fee.dueOn, lang))}
        back
      />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      <div className="card">
        <div className="hero-amount" style={{ margin: 0 }}>
          {t('extra_fees_collected', fee.collectedTotal.format(), fee.chargedTotal.format())}
        </div>
        {fee.examTitle ? <p className="meta">{t('extra_fees_for_exam', fee.examTitle)}</p> : null}
      </div>
      <ul className="card flush list" style={{ marginTop: 12 }}>
        {fee.students.map((s) => (
          <li key={s.enrollmentId} className="row">
            <div className="grow">
              <div className="title">{s.name}</div>
              <div className="meta">
                {t('extra_fees_student_line', s.paid.format(), s.owed.format())}
              </div>
            </div>
            <FeeChip chip={chargeChip(s.status, s.owed, fee.dueOn)} />
            {s.owed.isZero() ? null : (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() => setRecording(s)}
              >
                {t('extra_fees_record_payment')}
              </button>
            )}
          </li>
        ))}
      </ul>
      {recording ? (
        <RecordPaymentSheet
          enrollmentId={recording.enrollmentId}
          name={recording.name}
          owed={recording.owed}
          extraFeeId={fee.id}
          onClose={() => setRecording(null)}
          onRecorded={() => {
            setRecording(null)
            setSnack(t('fees_record_done'))
            reload()
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </>
  )
}
