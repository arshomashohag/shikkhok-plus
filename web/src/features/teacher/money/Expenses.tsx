/**
 * `/expenses`: one month's spending, recording an expense, voiding one;
 * `/money-summary`: the month's money in and out and what is owed today.
 *
 * Every total and the surplus-or-deficit verdict come from the server.
 */
import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatMonth, formatShortDate } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Section,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { mutationId } from '../classes/api'
import { paths } from '../paths'
import {
  EXPENSE_CATEGORIES,
  EXPENSE_WHAT_MAX,
  currentMonth,
  expenseBody,
  listExpenses,
  mapExpenseMonth,
  mapSummary,
  openExpense,
  readMoneySummary,
  recordExpense,
  shiftMonth,
  voidExpense,
  type ExpenseInput,
  type ExpenseRow,
} from './spending'

function MonthPicker({ month, onMonth }: { month: string; onMonth: (m: string) => void }) {
  const { lang } = useT()
  return (
    <div className="button-row" style={{ alignItems: 'center', marginBottom: 12 }}>
      <button
        type="button"
        className="btn btn-text btn-small"
        aria-label={formatMonth(shiftMonth(month, -1), lang)}
        onClick={() => onMonth(shiftMonth(month, -1))}
      >
        ‹
      </button>
      <span className="title grow" style={{ textAlign: 'center' }}>
        {formatMonth(month, lang)}
      </span>
      <button
        type="button"
        className="btn btn-text btn-small"
        aria-label={formatMonth(shiftMonth(month, 1), lang)}
        disabled={month >= currentMonth()}
        onClick={() => onMonth(shiftMonth(month, 1))}
      >
        ›
      </button>
    </div>
  )
}

function errorText(e: unknown, t: (k: string) => string, message: (k: string) => string) {
  const error = e instanceof ApiError ? e : null
  return error?.offline
    ? t('web_money_offline_nothing_changed')
    : message(error?.messageKey ?? 'error.unexpected')
}

function RecordSheet({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { t, message } = useT()
  const [input, setInput] = useState<ExpenseInput>(() =>
    openExpense(mutationId(), new Date().toISOString().slice(0, 10)),
  )
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const body = expenseBody(input)
  const set = (patch: Partial<ExpenseInput>) => setInput((i) => ({ ...i, ...patch }))

  async function save() {
    if (!body) return
    setBusy(true)
    setFailure(null)
    try {
      await recordExpense(body)
      onSaved()
    } catch (e) {
      setFailure(errorText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('expenses_record')} onClose={onClose}>
      <div className="field" style={{ marginTop: 0 }}>
        <label htmlFor="exp-cat">{t('expenses_category')}</label>
        <select
          id="exp-cat"
          value={input.category}
          onChange={(e) => set({ category: e.target.value as ExpenseInput['category'] })}
        >
          {EXPENSE_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`expenses_cat_${c}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="exp-what">{t('expenses_what')}</label>
        <input
          id="exp-what"
          maxLength={EXPENSE_WHAT_MAX}
          value={input.what}
          onChange={(e) => set({ what: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="exp-amount">{t('expenses_amount')}</label>
        <input
          id="exp-amount"
          inputMode="decimal"
          value={input.typed}
          onChange={(e) => set({ typed: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="exp-date">{t('expenses_spent_on')}</label>
        <input
          id="exp-date"
          type="date"
          value={input.spentOn}
          onChange={(e) => set({ spentOn: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="exp-payee">{t('expenses_payee')}</label>
        <input
          id="exp-payee"
          value={input.payee}
          onChange={(e) => set({ payee: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="exp-note">{t('expenses_note')}</label>
        <input id="exp-note" value={input.note} onChange={(e) => set({ note: e.target.value })} />
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
          {t('expenses_save')}
        </button>
      </div>
    </Sheet>
  )
}

function VoidSheet({
  row,
  onClose,
  onVoided,
}: {
  row: ExpenseRow
  onClose: () => void
  onVoided: () => void
}) {
  const { t, message } = useT()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function confirm() {
    setBusy(true)
    setFailure(null)
    try {
      await voidExpense(row.id, reason.trim() || null)
      onVoided()
    } catch (e) {
      setFailure(errorText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('expenses_void_title')} onClose={onClose}>
      <p className="meta">
        {row.what} · {row.amount.format()}
      </p>
      <p className="meta">{t('expenses_void_body')}</p>
      <div className="field">
        <label htmlFor="void-reason">{t('expenses_void_reason')}</label>
        <input id="void-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
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
          className="btn btn-danger-filled grow"
          disabled={busy}
          onClick={() => void confirm()}
        >
          {t('expenses_void')}
        </button>
      </div>
    </Sheet>
  )
}

export function Expenses() {
  const { t, lang } = useT()
  const [month, setMonth] = useState(currentMonth)
  const { resource, reload } = useResource(
    (signal) => listExpenses(month, signal).then(mapExpenseMonth),
    [month],
  )
  const [recording, setRecording] = useState(false)
  const [voiding, setVoiding] = useState<ExpenseRow | null>(null)
  const [snack, setSnack] = useState<string | null>(null)
  const dismiss = useCallback(() => setSnack(null), [])
  const add = (
    <button type="button" className="btn btn-primary" onClick={() => setRecording(true)}>
      {t('expenses_record')}
    </button>
  )

  return (
    <>
      <TopBar
        title={t('expenses_title')}
        back="/more"
        actions={
          <>
            <Link className="btn btn-text btn-small" to={paths.moneySummary()}>
              {t('money_open_summary')}
            </Link>
            {add}
          </>
        }
      />
      <MonthPicker month={month} onMonth={setMonth} />
      {resource.state === 'loading' ? (
        <Loading />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={t('expenses_load_failed')} error={resource.error} onRetry={reload} />
      ) : (
        <>
          {resource.error ? (
            <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
          ) : null}
          {resource.data.rows.length === 0 ? (
            <EmptyState title={t('expenses_title')} body={t('expenses_empty')} action={add} />
          ) : (
            <>
              <div className="card">
                <div className="hero-amount" style={{ margin: 0 }}>
                  {t('expenses_month_total', resource.data.total.format())}
                </div>
              </div>
              <ul className="card flush list" style={{ marginTop: 12 }}>
                {resource.data.rows.map((row) => (
                  <li key={row.id} className="row">
                    <div className="grow">
                      <div
                        className="title"
                        style={row.voided ? { textDecoration: 'line-through' } : undefined}
                      >
                        {row.what}
                      </div>
                      <div className="meta">
                        {t(`expenses_cat_${row.category}`)} · {formatShortDate(row.spentOn, lang)}
                        {row.payee ? ` · ${row.payee}` : ''}
                      </div>
                      {row.voided ? (
                        <div className="meta">
                          {t('expenses_voided')}
                          {row.voidReason ? ` · ${row.voidReason}` : ''}
                        </div>
                      ) : null}
                    </div>
                    <span
                      className="title"
                      style={row.voided ? { textDecoration: 'line-through' } : undefined}
                    >
                      {row.amount.format()}
                    </span>
                    {row.voided ? null : (
                      <button
                        type="button"
                        className="btn btn-text btn-small"
                        onClick={() => setVoiding(row)}
                      >
                        {t('expenses_void')}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {resource.data.byCategory.length > 0 ? (
                <Section title={t('expenses_by_category')}>
                  <dl className="card money-lines">
                    {resource.data.byCategory.map((c) => (
                      <div key={c.category}>
                        <dt>{t(`expenses_cat_${c.category}`)}</dt>
                        <dd className="amount">{c.total.format()}</dd>
                      </div>
                    ))}
                  </dl>
                </Section>
              ) : null}
            </>
          )}
        </>
      )}
      {recording ? (
        <RecordSheet
          onClose={() => setRecording(false)}
          onSaved={() => {
            setRecording(false)
            setSnack(t('expenses_saved'))
            reload()
          }}
        />
      ) : null}
      {voiding ? (
        <VoidSheet
          row={voiding}
          onClose={() => setVoiding(null)}
          onVoided={() => {
            setVoiding(null)
            reload()
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </>
  )
}

export function MoneySummaryScreen() {
  const { t, lang } = useT()
  const [month, setMonth] = useState(currentMonth)
  const { resource, reload } = useResource(
    (signal) => readMoneySummary(month, signal).then(mapSummary),
    [month],
  )
  return (
    <>
      <TopBar
        title={t('summary_title')}
        subtitle={t('summary_basis')}
        back="/more"
        actions={
          <Link className="btn btn-text btn-small" to={paths.expenses()}>
            {t('money_open_expenses')}
          </Link>
        }
      />
      <MonthPicker month={month} onMonth={setMonth} />
      {resource.state === 'loading' ? (
        <Loading />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={t('summary_title')} error={resource.error} onRetry={reload} />
      ) : (
        <>
          {resource.error ? (
            <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
          ) : null}
          <div className="card" aria-label={formatMonth(month, lang)}>
            <dl className="money-lines" style={{ margin: 0 }}>
              <div>
                <dt>{t('summary_collected')}</dt>
                <dd className="amount">{resource.data.collected.total.format()}</dd>
              </div>
              <div>
                <dt>{t('summary_spent')}</dt>
                <dd className="amount">{resource.data.spentTotal.format()}</dd>
              </div>
              <div className="money-lines-total">
                <dt>{t(`summary_${resource.data.netKind}`)}</dt>
                <dd className="amount">{resource.data.net.format()}</dd>
              </div>
            </dl>
          </div>
          <Section title={t('summary_collected')}>
            <dl className="card money-lines">
              <div>
                <dt>{t('summary_monthly')}</dt>
                <dd className="amount">{resource.data.collected.monthly.format()}</dd>
              </div>
              <div>
                <dt>{t('summary_exam')}</dt>
                <dd className="amount">{resource.data.collected.exam.format()}</dd>
              </div>
              <div>
                <dt>{t('summary_other')}</dt>
                <dd className="amount">{resource.data.collected.other.format()}</dd>
              </div>
            </dl>
          </Section>
          {resource.data.spentByCategory.length > 0 ? (
            <Section title={t('summary_spent')}>
              <dl className="card money-lines">
                {resource.data.spentByCategory.map((c) => (
                  <div key={c.category}>
                    <dt>{t(`expenses_cat_${c.category}`)}</dt>
                    <dd className="amount">{c.total.format()}</dd>
                  </div>
                ))}
              </dl>
            </Section>
          ) : null}
          <Section title={t('summary_owed_today')}>
            <dl className="card money-lines">
              <div>
                <dt>{t('summary_owed_monthly')}</dt>
                <dd className="amount">{resource.data.owedMonthly.format()}</dd>
              </div>
              <div>
                <dt>{t('summary_owed_extra')}</dt>
                <dd className="amount">{resource.data.owedExtra.format()}</dd>
              </div>
            </dl>
          </Section>
          {resource.data.fees.length > 0 ? (
            <Section title={t('summary_per_fee')}>
              <ul className="card flush list">
                {resource.data.fees.map((f) => (
                  <li key={f.id} className="row">
                    <div className="grow">
                      <div className="title">{f.label}</div>
                      <div className="meta">
                        {t('summary_fee_line', f.collected.format(), f.spent.format())}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
        </>
      )}
    </>
  )
}
