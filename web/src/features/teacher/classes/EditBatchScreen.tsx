/**
 * Edit batch: name, subjects, monthly fee and due day — the fields
 * Android's EditBatchScreen offers (the schedule has its own screen, and
 * marksheet visibility belongs to exams). Only fields that changed are
 * sent. Whether a subject can be removed is the server's call: one with
 * classes or exams recorded against it is refused with its own message.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { listBatches, type Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { Money, toLatinDigits } from '../../../core/money'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { paths } from '../paths'
import { updateBatch } from './api'

type Batch = Schemas['BatchResponse']

interface Values {
  name: string
  subjects: string
  fee: string
  dueDay: string
}

export function valuesOf(batch: Batch): Values {
  return {
    name: batch.name,
    subjects: (batch.subjects as string[]).join(', '),
    fee: batch.default_fee ? Money.fromWire(batch.default_fee).formatExact().replace('৳', '') : '',
    dueDay: batch.fee_due_day ? String(batch.fee_due_day) : '',
  }
}

export function splitSubjects(raw: string): string[] {
  return raw
    .split(/[,،]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/**
 * The PATCH body: only what changed, so an untouched field is never
 * re-sent. `null` when nothing changed.
 */
export function changes(
  batch: Batch,
  next: { name: string; subjects: string[]; fee: Money | null; dueDay: number | null },
): Schemas['BatchUpdateRequest'] | null {
  const body: Schemas['BatchUpdateRequest'] = {}
  if (next.name !== batch.name) body.name = next.name
  const before = (batch.subjects as string[]).join('\u0000')
  if (next.subjects.join('\u0000') !== before) body.subjects = next.subjects
  if ((next.fee?.wire ?? null) !== (batch.default_fee ?? null))
    body.default_fee = next.fee?.wire ?? null
  if (next.dueDay !== (batch.fee_due_day ?? null)) body.fee_due_day = next.dueDay
  return Object.keys(body).length > 0 ? body : null
}

export function EditBatchScreen() {
  const { batchId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(
    (signal) => listBatches(signal).then((all) => all.find((b) => b.id === batchId) ?? null),
    [batchId],
  )
  const back = paths.batch(batchId)

  return (
    <>
      <TopBar title={t('batch_edit_title')} back={back} />
      {resource.state === 'loading' ? <Loading rows={3} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('batch_edit_title')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' && resource.data === null ? (
        <div className="card meta">{t('batch_not_found')}</div>
      ) : null}
      {resource.state === 'loaded' && resource.data ? (
        <EditForm batch={resource.data} fresh={resource.error === null} />
      ) : null}
    </>
  )
}

function EditForm({ batch, fresh }: { batch: Batch; fresh: boolean }) {
  const { t, message } = useT()
  const navigate = useNavigate()
  const [values, setValues] = useState<Values>(() => valuesOf(batch))
  const [errors, setErrors] = useState<Partial<Record<keyof Values, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof Values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [k]: e.target.value }))

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const next: Partial<Record<keyof Values, string>> = {}
    const name = values.name.trim()
    const subjects = splitSubjects(values.subjects)
    if (!name) next.name = t('address_required')
    if (subjects.length === 0) next.subjects = t('batch_create_subject_required')
    const fee = values.fee.trim() ? Money.fromTyped(values.fee) : null
    if (values.fee.trim() && !fee) next.fee = t('fee_invalid')
    const day = values.dueDay.trim() ? Number.parseInt(toLatinDigits(values.dueDay), 10) : null
    if (values.dueDay.trim() && (day === null || Number.isNaN(day) || day < 1 || day > 31))
      next.dueDay = t('due_day_invalid')
    setErrors(next)
    if (Object.keys(next).length) return
    const body = changes(batch, { name, subjects, fee, dueDay: day })
    if (!body) {
      navigate(paths.batch(batch.id))
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      await updateBatch(batch.id, body)
      navigate(paths.batch(batch.id))
    } catch (err) {
      setFormError(err instanceof ApiError ? message(err.messageKey) : t('error_unexpected'))
      setBusy(false)
    }
  }

  const field = (
    k: keyof Values,
    label: string,
    props: { inputMode?: 'decimal' | 'numeric' } = {},
  ) => (
    <div className="field">
      <label htmlFor={`eb-${k}`}>{label}</label>
      <input
        id={`eb-${k}`}
        value={values[k]}
        onChange={set(k)}
        aria-invalid={errors[k] ? true : undefined}
        aria-describedby={errors[k] ? `eb-${k}-error` : undefined}
        {...props}
      />
      {errors[k] ? (
        <span id={`eb-${k}-error`} className="field-error">
          {errors[k]}
        </span>
      ) : null}
    </div>
  )

  return (
    <form className="card" onSubmit={onSubmit} noValidate>
      {field('name', t('batch_create_name'))}
      {field('subjects', t('batch_create_subjects'))}
      {field('fee', t('batch_create_fee'), { inputMode: 'decimal' })}
      {field('dueDay', t('batch_create_due_day'), { inputMode: 'numeric' })}
      {formError ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {formError}
        </div>
      ) : null}
      {fresh ? (
        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {t('batch_edit_save')}
          </button>
        </div>
      ) : null}
    </form>
  )
}
