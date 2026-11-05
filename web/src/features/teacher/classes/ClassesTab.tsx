/**
 * T7 · Classes tab. The batch's month calendar, as Android's ClassesTab
 * draws it: each day coloured by the state the server gave it (taken,
 * today, upcoming, not recorded, cancelled), months limited to the range
 * the server says has classes. Choosing a day lists its classes; each
 * opens the class screen, which records, plans or shows it.
 *
 * Also here: "Add class" for a one-off class outside the weekly schedule,
 * and the way to the schedule editor.
 */
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatClock, formatLongDay, formatMonth, type Lang } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Sheet, Snackbar } from '../../../ui/components'
import { BackIcon, ChevronIcon, PlusIcon } from '../../../ui/icons'
import type { BatchTabProps } from '../area'
import { paths } from '../paths'
import { createSession, readCalendar } from './api'
import {
  compareMonths,
  isoDay,
  mapMonth,
  monthGrid,
  monthOf,
  shiftMonth,
  type ClassItem,
  type ClassState,
  type MonthModel,
  type YearMonth,
} from './mappers'

const WEEKDAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const

export const STATE_LABEL: Record<ClassState, string> = {
  taken: 'calendar_state_taken',
  today: 'calendar_state_today',
  upcoming: 'calendar_state_upcoming',
  not_recorded: 'calendar_state_not_recorded',
  cancelled: 'calendar_state_cancelled',
}

/** Today's date in Dhaka, `YYYY-MM-DD`: only to choose which month to open first. */
export function dhakaToday(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(now)
}

export function monthTitle(ym: YearMonth, lang: Lang): string {
  return `${formatMonth(`${ym.year}-${String(ym.month).padStart(2, '0')}`, lang)} ${ym.year}`
}

export function ClassesTab({ batchId, batch }: BatchTabProps) {
  const { t, lang } = useT()
  const [ym, setYm] = useState<YearMonth>(() => monthOf(dhakaToday()))
  const [selected, setSelected] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  const { resource, reload } = useResource(
    () => readCalendar(batchId, ym.year, ym.month).then(mapMonth),
    [batchId, ym.year, ym.month],
  )

  // Open on today when it is in the month shown, else on the first day
  // that has a class.
  useEffect(() => {
    if (resource.state !== 'loaded') return
    const m = resource.data
    setSelected((current) => {
      if (current && current.startsWith(`${m.year}-${String(m.month).padStart(2, '0')}`))
        return current
      if (m.days.has(m.today)) return m.today
      return [...m.days.keys()].sort()[0] ?? null
    })
  }, [resource])

  const toolbar = (
    <div className="classes-toolbar">
      <Link className="btn btn-outline btn-small" to={paths.batchSchedule(batchId)}>
        {t('batch_schedule')}
      </Link>
      <button type="button" className="btn btn-tonal btn-small" onClick={() => setAdding(true)}>
        <PlusIcon size={18} />
        {t('batch_add_class')}
      </button>
    </div>
  )

  let body: React.ReactNode
  if (resource.state === 'loading') {
    body = <Loading rows={4} />
  } else if (resource.state === 'failed') {
    body = <ErrorCard title={t('batch_classes_failed')} error={resource.error} onRetry={reload} />
  } else {
    const model = resource.data
    const day = selected ? model.days.get(selected) : undefined
    body = (
      <>
        <MonthCalendar
          model={model}
          selected={selected}
          onSelect={setSelected}
          onMonth={(next) => {
            setSelected(null)
            setYm(next)
          }}
        />
        {model.days.size === 0 ? (
          <p className="meta" style={{ marginTop: 12 }}>
            {t('web_classes_month_empty')}
          </p>
        ) : selected ? (
          <section className="section" aria-live="polite">
            <div className="section-head">
              <h2>{formatLongDay(selected, lang)}</h2>
            </div>
            {day && day.classes.length > 0 ? (
              <ul className="card flush list">
                {day.classes.map((c) => (
                  <ClassRow key={c.sessionId} batchId={batchId} item={c} />
                ))}
              </ul>
            ) : (
              <div className="card meta">{t('web_classes_no_class_day')}</div>
            )}
          </section>
        ) : null}
      </>
    )
  }

  return (
    <>
      {toolbar}
      {body}
      {adding ? (
        <AddClassSheet
          batchId={batchId}
          defaultDate={selected ?? dhakaToday()}
          defaultStart={batch?.schedule[0]?.startTime.slice(0, 5) ?? '16:00'}
          onClose={() => setAdding(false)}
          onAdded={(date) => {
            setAdding(false)
            setSnack(t('web_classes_added'))
            const target = monthOf(date)
            setSelected(date)
            if (compareMonths(target, ym) === 0) reload()
            else setYm(target)
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}

function ClassRow({ batchId, item }: { batchId: string; item: ClassItem }) {
  const { t, lang } = useT()
  const line = item.topic?.trim() || item.subjectName || null
  return (
    <li>
      <Link className="row" to={paths.session(batchId, item.sessionId)}>
        <div style={{ width: 80, flexShrink: 0 }}>
          <div className="amount">{formatClock(item.startTime, lang)}</div>
          {item.endTime ? <div className="meta">{formatClock(item.endTime, lang)}</div> : null}
        </div>
        <div className="grow">
          <span className={`class-state class-state-${item.state}`}>
            {t(STATE_LABEL[item.state])}
          </span>
          {line ? <div className="meta">{line}</div> : null}
        </div>
        <ChevronIcon />
      </Link>
    </li>
  )
}

function MonthCalendar({
  model,
  selected,
  onSelect,
  onMonth,
}: {
  model: MonthModel
  selected: string | null
  onSelect: (date: string) => void
  onMonth: (ym: YearMonth) => void
}) {
  const { t, lang } = useT()
  const prev = shiftMonth(model, -1)
  const next = shiftMonth(model, 1)
  const canPrev = compareMonths(prev, model.first) >= 0
  const canNext = compareMonths(next, model.last) <= 0
  return (
    <div className="card calendar">
      <div className="calendar-head">
        <button
          type="button"
          className="icon-btn"
          aria-label={t('calendar_prev_month')}
          disabled={!canPrev}
          onClick={() => onMonth(prev)}
        >
          <BackIcon />
        </button>
        <h2 className="calendar-title" aria-live="polite">
          {monthTitle(model, lang)}
        </h2>
        <button
          type="button"
          className="icon-btn"
          aria-label={t('calendar_next_month')}
          disabled={!canNext}
          onClick={() => onMonth(next)}
        >
          <ChevronIcon />
        </button>
      </div>
      <div className="calendar-grid" role="grid" aria-label={monthTitle(model, lang)}>
        <div role="row" className="calendar-row">
          {WEEKDAYS.map((d) => (
            <span key={d} role="columnheader" className="calendar-weekday">
              {t(`calendar_weekday_${d}`)}
            </span>
          ))}
        </div>
        {monthGrid(model).map((week, w) => (
          <div role="row" className="calendar-row" key={w}>
            {week.map((n, i) => {
              if (n === null) return <span key={i} role="gridcell" className="calendar-blank" />
              const date = isoDay(model, n)
              const day = model.days.get(date)
              if (!day) {
                return (
                  <span key={i} role="gridcell" className="calendar-day calendar-quiet">
                    {n}
                  </span>
                )
              }
              return (
                <span key={i} role="gridcell">
                  <button
                    type="button"
                    className={`calendar-day calendar-${day.state}`}
                    aria-pressed={selected === date}
                    aria-label={t('calendar_day_description', n, t(STATE_LABEL[day.state]))}
                    onClick={() => onSelect(date)}
                  >
                    {n}
                  </button>
                </span>
              )
            })}
          </div>
        ))}
      </div>
      <ul className="calendar-legend">
        {(Object.keys(STATE_LABEL) as ClassState[]).map((s) => (
          <li key={s}>
            <span className={`calendar-swatch calendar-${s}`} aria-hidden="true" />
            {t(STATE_LABEL[s])}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * A one-off class: a date and a start time, which is all Android's
 * AddSessionDialog asks. The subject is chosen when the class is recorded.
 */
function AddClassSheet({
  batchId,
  defaultDate,
  defaultStart,
  onClose,
  onAdded,
}: {
  batchId: string
  defaultDate: string
  defaultStart: string
  onClose: () => void
  onAdded: (date: string) => void
}) {
  const { t, message } = useT()
  const [date, setDate] = useState(defaultDate)
  const [start, setStart] = useState(defaultStart)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!date || !start) return
    setBusy(true)
    setError(null)
    try {
      await createSession(batchId, {
        date,
        start_time: start,
        end_time: null,
        batch_subject_id: null,
      })
      onAdded(date)
    } catch (err) {
      setError(err instanceof ApiError ? message(err.messageKey) : t('error_unexpected'))
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('sessions_add')} subtitle={t('session_add_note')} onClose={onClose}>
      <form onSubmit={onSubmit} noValidate>
        <div className="field">
          <label htmlFor="ac-date">{t('web_classes_date')}</label>
          <input
            id="ac-date"
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="ac-start">{t('web_classes_starts')}</label>
          <input
            id="ac-start"
            type="time"
            required
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        {error ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        ) : null}
        <div className="button-row">
          <button
            type="submit"
            className="btn btn-primary btn-money"
            disabled={busy || !date || !start}
          >
            {t('session_add_confirm')}
          </button>
          <button type="button" className="btn btn-text btn-money" onClick={onClose}>
            {t('action_cancel')}
          </button>
        </div>
      </form>
    </Sheet>
  )
}
