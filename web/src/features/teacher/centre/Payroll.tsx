/**
 * A centre's payroll, a month at a time: draw the lines from the staff
 * records, add bonuses and deductions to drafts, approve, and record
 * payments. Every figure is the server's — the base from the classes held,
 * what is owed, paid and left — and every refusal is its message.
 */
import { useRef, useState } from 'react'
import {
  addSalaryAdjustment,
  approveSalary,
  drawPayroll,
  paySalary,
  readPayroll,
  removeSalaryAdjustment,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatMonth } from '../../../core/format'
import { Money } from '../../../core/money'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  ConfirmSheet,
  EmptyState,
  ErrorCard,
  Loading,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { mutationId } from '../classes/api'
import { currentMonth, shiftMonth } from '../money/spending'
import { adjustmentBody, basisLine, paymentBody, type SalaryLine } from './payroll'

function failureText(e: unknown, t: (k: string) => string, message: (k: string) => string) {
  const error = e instanceof ApiError ? e : null
  return error?.offline
    ? t('web_money_offline_nothing_changed')
    : message(error?.messageKey ?? 'error.unexpected')
}

const money = (wire: string) => Money.fromWire(wire).format()

function AdjustSheet({
  line,
  onClose,
  onDone,
}: {
  line: SalaryLine
  onClose: () => void
  onDone: () => void
}) {
  const { t, message } = useT()
  const [kind, setKind] = useState<'addition' | 'deduction'>('addition')
  const [label, setLabel] = useState('')
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const body = adjustmentBody(kind, label, typed)

  async function save() {
    if (!body) return
    setBusy(true)
    setFailure(null)
    try {
      await addSalaryAdjustment(line.line_id, body)
      onDone()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      title={t('payroll_adjust')}
      onClose={onClose}
      dirty={label.trim() !== '' || typed.trim() !== ''}
    >
      <p className="meta" style={{ marginTop: 0 }}>
        {line.staff_name} · {t('payroll_owed', money(line.owed))}
      </p>
      <div className="field">
        <label htmlFor="pa-kind">{t('payroll_adjust')}</label>
        <select id="pa-kind" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="addition">{t('payroll_addition')}</option>
          <option value="deduction">{t('payroll_deduction')}</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="pa-label">{t('payroll_label')}</label>
        <input
          id="pa-label"
          maxLength={80}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pa-amount">{t('payroll_amount')}</label>
        <input
          id="pa-amount"
          inputMode="decimal"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!body || busy}
          onClick={() => void save()}
        >
          {t('staff_save')}
        </button>
      </div>
    </Sheet>
  )
}

function PaySheet({
  line,
  onClose,
  onDone,
}: {
  line: SalaryLine
  onClose: () => void
  onDone: () => void
}) {
  const { t, message } = useT()
  const [prefilled] = useState(() => Money.fromWire(line.remaining).wire)
  const [typed, setTyped] = useState(prefilled)
  const [paidOn, setPaidOn] = useState('')
  const [note, setNote] = useState('')
  const [key] = useState(mutationId)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const body = paymentBody(typed, paidOn, note, key)

  async function save() {
    if (!body) return
    setBusy(true)
    setFailure(null)
    try {
      await paySalary(line.line_id, body)
      onDone()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      title={t('payroll_pay_title')}
      onClose={onClose}
      dirty={typed !== prefilled || paidOn !== '' || note.trim() !== ''}
    >
      <p className="meta" style={{ marginTop: 0 }}>
        {line.staff_name} · {t('payroll_paid_remaining', money(line.paid), money(line.remaining))}
      </p>
      <div className="field">
        <label htmlFor="pp-amount">{t('payroll_amount')}</label>
        <input
          id="pp-amount"
          inputMode="decimal"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pp-date">{t('payroll_paid_on')}</label>
        <input
          id="pp-date"
          type="date"
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pp-note">{t('payroll_note')}</label>
        <input
          id="pp-note"
          maxLength={200}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!body || busy}
          onClick={() => void save()}
        >
          {t('payroll_pay')}
        </button>
      </div>
    </Sheet>
  )
}

/** One line's card, shared by the manager's payroll and the teacher's My pay. */
export function SalaryCard({
  line,
  actions,
  onRemoveAdjustment,
  disabled = false,
}: {
  line: SalaryLine
  actions?: React.ReactNode
  onRemoveAdjustment?: (adjustment: Adjustment) => void
  /** While a write is on its way or the line is not confirmed fresh. */
  disabled?: boolean
}) {
  const { t } = useT()
  return (
    <article className="card">
      <div className="title">
        {line.staff_name} ·{' '}
        {line.status === 'approved' ? t('payroll_status_approved') : t('payroll_status_draft')}
      </div>
      <div className="meta">
        {basisLine(line, t)} · {t('payroll_owed', money(line.owed))}
      </div>
      <div className="meta">
        {t('payroll_paid_remaining', money(line.paid), money(line.remaining))}
      </div>
      {line.adjustments.length > 0 ? (
        <ul className="meta" style={{ margin: '8px 0 0', paddingLeft: 18 }}>
          {line.adjustments.map((a) => (
            <li key={a.adjustment_id}>
              {a.kind === 'addition' ? '+' : '−'} {money(a.amount)} · {a.label}
              {onRemoveAdjustment ? (
                <button
                  type="button"
                  className="btn btn-text btn-small"
                  disabled={disabled}
                  // Every row says "Remove"; the name says which one [UX-9].
                  aria-label={t('web_payroll_remove_named', a.label)}
                  onClick={() => onRemoveAdjustment(a)}
                >
                  {t('payroll_remove')}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {actions ? <div className="button-row">{actions}</div> : null}
    </article>
  )
}

type Adjustment = SalaryLine['adjustments'][number]

type Open =
  | { sheet: 'adjust' | 'pay'; line: SalaryLine }
  | { sheet: 'remove'; line: SalaryLine; adjustment: Adjustment }
  | null

export function Payroll() {
  const { t, lang, message } = useT()
  const [month, setMonth] = useState(currentMonth)
  // A month switch starts from loading (useResource drops the old key's
  // lines), so last month's line ids never sit under this month's heading.
  const { resource, reload } = useResource((signal) => readPayroll(month, signal), [month])
  const [open, setOpen] = useState<Open>(null)
  const [snack, setSnack] = useState<string | null>(null)
  // One write at a time: a double click must not send a second money POST.
  const [busy, setBusy] = useState(false)
  const writing = useRef(false)

  // Decide only on lines the last read confirmed: not while a re-read is
  // on its way, and not over lines a failed re-read could not confirm.
  const fresh = resource.state === 'loaded' && !resource.refreshing && resource.error === null
  const canAct = fresh && !busy

  async function act(work: () => Promise<unknown>) {
    if (writing.current) return
    writing.current = true
    setBusy(true)
    try {
      await work()
      setSnack(t('staff_saved'))
      reload()
    } catch (e) {
      setSnack(failureText(e, t, message))
    } finally {
      writing.current = false
      setBusy(false)
    }
  }

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('payroll_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = <EmptyState title={t('payroll_title')} body={t('payroll_empty')} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <div className="grid-2">
          {resource.data.map((line) => (
            <SalaryCard
              key={line.line_id}
              line={line}
              disabled={!canAct}
              onRemoveAdjustment={
                line.status === 'draft'
                  ? (adjustment) => setOpen({ sheet: 'remove', line, adjustment })
                  : undefined
              }
              actions={
                line.status === 'draft' ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-outline"
                      disabled={!canAct}
                      onClick={() => setOpen({ sheet: 'adjust', line })}
                    >
                      {t('payroll_adjust')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary grow"
                      disabled={!canAct}
                      onClick={() => void act(() => approveSalary(line.line_id))}
                    >
                      {t('payroll_approve')}
                    </button>
                  </>
                ) : !Money.fromWire(line.remaining).isZero() ? (
                  <button
                    type="button"
                    className="btn btn-primary grow"
                    disabled={!canAct}
                    onClick={() => setOpen({ sheet: 'pay', line })}
                  >
                    {t('payroll_pay')}
                  </button>
                ) : null
              }
            />
          ))}
        </div>
      </>
    )

  return (
    <>
      <TopBar
        title={t('payroll_title')}
        subtitle={t('payroll_sub')}
        actions={
          <button
            type="button"
            className="btn btn-primary btn-small"
            disabled={busy}
            onClick={() => void act(() => drawPayroll(month))}
          >
            {t('payroll_draw')}
          </button>
        }
      />
      <div className="button-row" style={{ marginTop: 0, marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-text btn-small"
          aria-label={t('calendar_prev_month')}
          disabled={busy}
          onClick={() => setMonth(shiftMonth(month, -1))}
        >
          ‹
        </button>
        <span className="grow" style={{ textAlign: 'center' }} aria-live="polite">
          {formatMonth(month, lang)}
        </span>
        <button
          type="button"
          className="btn btn-text btn-small"
          aria-label={t('calendar_next_month')}
          disabled={busy || month >= currentMonth()}
          onClick={() => setMonth(shiftMonth(month, 1))}
        >
          ›
        </button>
      </div>
      {body}
      {open?.sheet === 'adjust' ? (
        <AdjustSheet
          line={open.line}
          onClose={() => setOpen(null)}
          onDone={() => {
            setOpen(null)
            setSnack(t('staff_saved'))
            reload()
          }}
        />
      ) : null}
      {open?.sheet === 'pay' ? (
        <PaySheet
          line={open.line}
          onClose={() => setOpen(null)}
          onDone={() => {
            setOpen(null)
            setSnack(t('staff_saved'))
            reload()
          }}
        />
      ) : null}
      {open?.sheet === 'remove' ? (
        <ConfirmSheet
          title={t('web_payroll_remove_title')}
          body={t('web_payroll_remove_body', open.adjustment.label, open.line.staff_name)}
          confirmLabel={t('payroll_remove')}
          onConfirm={() => {
            const { line, adjustment } = open
            setOpen(null)
            void act(() => removeSalaryAdjustment(line.line_id, adjustment.adjustment_id))
          }}
          onCancel={() => setOpen(null)}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
