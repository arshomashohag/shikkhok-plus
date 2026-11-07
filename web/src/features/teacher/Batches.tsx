/**
 * T6 · Batch list, and T0's "create a batch" form.
 */
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { createBatch, listBatches } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { formatClock } from '../../core/format'
import { Money, toLatinDigits } from '../../core/money'
import { useResource } from '../../core/useResource'
import { useWide } from '../../core/useWide'
import { useT } from '../../i18n/i18n'
import { useSession } from '../../session/session'
import { EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../ui/components'
import { PlusIcon } from '../../ui/icons'
import { mapBatch, sortedDays, WEEK_ORDER, type BatchSummary } from './mappers'

/** Server weekday (0 = Monday) → string key. */
export const WEEKDAY_KEYS = [
  'weekday_mon',
  'weekday_tue',
  'weekday_wed',
  'weekday_thu',
  'weekday_fri',
  'weekday_sat',
  'weekday_sun',
] as const

export function useScheduleLine() {
  const { t, lang } = useT()
  return (batch: BatchSummary): string | null => {
    const days = sortedDays(batch.schedule)
    if (days.length === 0) return null
    const first = batch.schedule[0]
    const names = days.map((d) => t(WEEKDAY_KEYS[d] ?? 'weekday_mon')).join(' ')
    return first ? `${names} · ${formatClock(first.startTime, lang)}` : names
  }
}

export function Batches() {
  const { t, plural } = useT()
  const scheduleLine = useScheduleLine()
  const wide = useWide()
  const { resource, reload } = useResource(
    (signal) => listBatches(signal).then((b) => b.map(mapBatch)),
    [],
  )

  // A phone reaches "New batch" from the floating button; a wide window
  // from the page header, as the web boards put it.
  const fab = wide ? null : (
    <Link to="/batches/new" className="btn btn-primary fab">
      <PlusIcon />
      {t('batch_create_title')}
    </Link>
  )
  const headerAction = wide ? (
    <Link to="/batches/new" className="btn btn-primary">
      <PlusIcon />
      {t('batch_create_title')}
    </Link>
  ) : null

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('batches_title')} subtitle={t('batches_loading_label')} />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('batches_title')} />
        <ErrorCard title={t('batches_error_title')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const batches = resource.data
  if (batches.length === 0) {
    return (
      <>
        <TopBar title={t('batches_title')} subtitle={t('batches_subtitle_none')} />
        <EmptyState
          title={t('batches_empty_title')}
          body={t('batches_empty_body')}
          action={
            <Link to="/batches/new" className="btn btn-primary btn-money">
              {t('batches_create_first')}
            </Link>
          }
        />
      </>
    )
  }

  const students = batches.reduce((n, b) => n + b.enrollmentCount, 0)
  return (
    <>
      <TopBar
        title={t('batches_title')}
        subtitle={t('batches_count', batches.length, students)}
        actions={headerAction}
      />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      <div className="card-grid" style={{ marginTop: resource.error ? 12 : 0 }}>
        {batches.map((b) => {
          const schedule = scheduleLine(b)
          return (
            <Link key={b.id} to={`/batches/${b.id}`} className="card tile">
              <div>
                <div className="tile-title">{b.name}</div>
                <div className="meta">
                  {[b.subjects.join(', '), schedule].filter(Boolean).join(' · ')}
                </div>
              </div>
              {b.feeDueDay && b.defaultFee ? (
                <div className="meta">{t('batch_fee_due', b.defaultFee.format(), b.feeDueDay)}</div>
              ) : null}
              <div className="tile-foot">
                <span>
                  {plural('batches_student_count', b.enrollmentCount)}
                  {b.defaultFee && !b.feeDueDay
                    ? ` · ${t('batch_fee_monthly', b.defaultFee.format())}`
                    : ''}
                </span>
                {b.enrollmentCount > 0 ? (
                  <span className="chip chip-neutral">
                    {t('web_batches_joined', b.acceptedCount, b.enrollmentCount)}
                  </span>
                ) : (
                  <span className="meta accent">{t('batch_add_first_student')}</span>
                )}
              </div>
            </Link>
          )
        })}
        {wide ? (
          <Link to="/batches/new" className="card tile new-tile">
            <PlusIcon />
            {t('batch_create_title')}
            <span className="meta" style={{ fontWeight: 400, maxWidth: 240 }}>
              {t('web_batches_new_hint')}
            </span>
          </Link>
        ) : null}
      </div>
      {fab}
    </>
  )
}

export function CreateBatch() {
  const { t, message, lang } = useT()
  const navigate = useNavigate()
  const { refresh } = useSession()
  const [name, setName] = useState('')
  const [subjects, setSubjects] = useState('')
  const [days, setDays] = useState<number[]>([])
  const [start, setStart] = useState('16:00')
  const [end, setEnd] = useState('17:30')
  const [fee, setFee] = useState('')
  const [dueDay, setDueDay] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const next: Record<string, string> = {}
    const subjectList = subjects
      .split(/[,،]/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (!name.trim()) next.name = t('address_required')
    if (subjectList.length === 0) next.subjects = t('batch_create_subject_required')
    const money = fee.trim() ? Money.fromTyped(fee) : null
    if (fee.trim() && !money) next.fee = t('fee_invalid')
    const day = dueDay.trim() ? Number.parseInt(toLatinDigits(dueDay), 10) : null
    if (dueDay.trim() && (day === null || Number.isNaN(day) || day < 1 || day > 31))
      next.dueDay = t('due_day_invalid')
    if (days.length > 0 && end <= start) next.time = t('schedule_end_before_start')
    setErrors(next)
    if (Object.keys(next).length) return

    setBusy(true)
    setFormError(null)
    try {
      const created = await createBatch({
        name: name.trim(),
        subjects: subjectList,
        schedule: days.map((weekday) => ({ weekday, start_time: start, end_time: end })),
        default_fee: money?.wire ?? null,
        fee_due_day: day,
      })
      refresh()
      navigate(`/batches/${created.id}`, { replace: true })
    } catch (err) {
      setFormError(err instanceof ApiError ? message(err.messageKey) : t('error_unexpected'))
      setBusy(false)
    }
  }

  const err = (k: string) =>
    errors[k] ? (
      <span className="field-error" id={`cb-${k}-error`}>
        {errors[k]}
      </span>
    ) : null

  return (
    <>
      <TopBar title={t('batch_create_title')} back="/batches" />
      <form className="card" onSubmit={onSubmit} noValidate>
        <div className="field" style={{ marginTop: 0 }}>
          <label htmlFor="cb-name">{t('batch_create_name')}</label>
          <input
            id="cb-name"
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={!!errors.name || undefined}
          />
          {err('name')}
        </div>
        <div className="field">
          <label htmlFor="cb-subjects">{t('batch_create_subjects')}</label>
          <input
            id="cb-subjects"
            value={subjects}
            onChange={(e) => setSubjects(e.target.value)}
            aria-invalid={!!errors.subjects || undefined}
          />
          {err('subjects')}
        </div>
        <fieldset className="field">
          <legend>{t('schedule_days')}</legend>
          <div className="chips">
            {WEEK_ORDER.map((d) => (
              <button
                key={d}
                type="button"
                className="chip chip-filter"
                aria-pressed={days.includes(d)}
                onClick={() =>
                  setDays((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]))
                }
              >
                {t(WEEKDAY_KEYS[d] ?? 'weekday_mon')}
              </button>
            ))}
          </div>
        </fieldset>
        {days.length > 0 ? (
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="cb-start">{t('schedule_start', formatClock(start, lang))}</label>
              <input
                id="cb-start"
                type="time"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="cb-end">{t('schedule_end', formatClock(end, lang))}</label>
              <input
                id="cb-end"
                type="time"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                aria-invalid={!!errors.time || undefined}
              />
            </div>
          </div>
        ) : (
          <p className="meta">{t('schedule_none')}</p>
        )}
        {err('time')}
        <div className="field">
          <label htmlFor="cb-fee">{t('batch_create_fee')}</label>
          <input
            id="cb-fee"
            inputMode="decimal"
            value={fee}
            onChange={(e) => setFee(e.target.value)}
            aria-invalid={!!errors.fee || undefined}
          />
          {err('fee')}
        </div>
        <div className="field">
          <label htmlFor="cb-due">{t('batch_create_due_day')}</label>
          <input
            id="cb-due"
            inputMode="numeric"
            value={dueDay}
            onChange={(e) => setDueDay(e.target.value)}
            aria-invalid={!!errors.dueDay || undefined}
          />
          {err('dueDay')}
        </div>
        {formError ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            {formError}
          </div>
        ) : null}
        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {busy ? t('batch_create_submitting') : t('batch_create_submit')}
          </button>
        </div>
      </form>
    </>
  )
}
