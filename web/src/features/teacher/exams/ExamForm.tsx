/**
 * New exam (`/batches/:batchId/exams/new`) and the edit form the marks
 * screen opens in a sheet, as ExamCreateForm.kt: title, date, total,
 * topics one per line, and — when creating — the batch subject it is in.
 *
 * Validation is format only: a title, a whole total of at least one, and
 * the topic limits Android states. Everything else is the server's,
 * shown through its `message_key`.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import type { Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatShortDate } from '../../../core/format'
import { toLatinDigits } from '../../../core/money'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { paths } from '../paths'
import { createExam, readBatch } from './api'
import { DEFAULT_EXAMINER, ExaminerPicker } from './Examiner'
import { useInCentre } from '../../../session/useInCentre'
import { topicsOf, topicsValid } from './mappers'

export interface ExamValues {
  title: string
  date: string
  totalMarks: number
  topics: string[]
  /** Only when creating. */
  subjectId?: string
}

/** Today in Bangladesh, as YYYY-MM-DD, for the date field's default. */
export function todayInDhaka(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(now)
}

export function ExamFields({
  initial,
  subjects,
  saving,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Partial<ExamValues>
  /** The batch's subjects when creating; omitted when editing. */
  subjects?: Schemas['SubjectOption'][]
  saving: boolean
  error: string | null
  submitLabel: string
  onSubmit: (values: ExamValues) => void
  onCancel: () => void
}) {
  const { t, lang } = useT()
  const [title, setTitle] = useState(initial?.title ?? '')
  const [date, setDate] = useState(initial?.date ?? todayInDhaka())
  const [total, setTotal] = useState(initial?.totalMarks ? String(initial.totalMarks) : '')
  const [topicsText, setTopicsText] = useState((initial?.topics ?? []).join('\n'))
  const [subjectId, setSubjectId] = useState<string | null>(
    subjects?.length === 1 ? (subjects[0]?.id ?? null) : null,
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const topics = topicsOf(topicsText)
  const topicsOk = topicsValid(topics)

  function submit(e: FormEvent) {
    e.preventDefault()
    const next: Record<string, string> = {}
    if (!title.trim()) next.title = t('address_required')
    const totalMarks = Number.parseInt(toLatinDigits(total.trim()), 10)
    if (!/^[0-9]+$/.test(toLatinDigits(total.trim())) || totalMarks < 1) {
      next.total = t('marks_exam_total_invalid')
    }
    if (!date) next.date = t('address_required')
    if (subjects && !subjectId) next.subject = t('batch_create_subject_required')
    setErrors(next)
    if (Object.keys(next).length || !topicsOk) return
    onSubmit({
      title: title.trim(),
      date,
      totalMarks,
      topics,
      ...(subjects && subjectId ? { subjectId } : {}),
    })
  }

  const fieldError = (k: string) =>
    errors[k] ? (
      <span className="field-error" id={`ex-${k}-error`}>
        {errors[k]}
      </span>
    ) : null

  return (
    <form onSubmit={submit} noValidate>
      <div className="field" style={{ marginTop: 0 }}>
        <label htmlFor="ex-title">{t('exam_create_title')}</label>
        <input
          id="ex-title"
          value={title}
          maxLength={120}
          onChange={(e) => setTitle(e.target.value)}
          aria-invalid={errors.title ? true : undefined}
          aria-describedby={errors.title ? 'ex-title-error' : undefined}
        />
        {fieldError('title')}
      </div>
      <div className="exam-form-pair">
        <div className="field">
          <label htmlFor="ex-date">
            {t('exam_create_date', date ? formatShortDate(date, lang) : '')}
          </label>
          <input
            id="ex-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            aria-invalid={errors.date ? true : undefined}
          />
          {fieldError('date')}
        </div>
        <div className="field">
          <label htmlFor="ex-total">{t('exam_create_total')}</label>
          <input
            id="ex-total"
            inputMode="numeric"
            value={total}
            onChange={(e) => setTotal(e.target.value)}
            aria-invalid={errors.total ? true : undefined}
            aria-describedby={errors.total ? 'ex-total-error' : undefined}
          />
          {fieldError('total')}
        </div>
      </div>
      {subjects ? (
        <fieldset className="field">
          <legend>{t('exam_create_subject')}</legend>
          {subjects.length === 0 ? (
            <span className="field-error">{t('exam_create_subjects_failed')}</span>
          ) : (
            <div className="chips">
              {subjects.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="chip chip-filter"
                  aria-pressed={subjectId === s.id}
                  onClick={() => setSubjectId(s.id)}
                >
                  {s.name}
                </button>
              ))}
            </div>
          )}
          {fieldError('subject')}
        </fieldset>
      ) : null}
      <div className="field">
        <label htmlFor="ex-topics">{t('exam_topics_label')}</label>
        <textarea
          id="ex-topics"
          value={topicsText}
          onChange={(e) => setTopicsText(e.target.value)}
          aria-invalid={topicsOk ? undefined : true}
        />
        {topicsOk ? null : <span className="field-error">{t('exam_topics_too_long')}</span>}
      </div>
      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}
      <div className="button-row">
        <button type="submit" className="btn btn-primary btn-money" disabled={saving}>
          {saving ? t('profile_saving') : submitLabel}
        </button>
        <button type="button" className="btn btn-text btn-money" onClick={onCancel}>
          {t('action_cancel')}
        </button>
      </div>
    </form>
  )
}

/** The create page. */
export function CreateExam() {
  const { batchId = '' } = useParams()
  const { t, message } = useT()
  const navigate = useNavigate()
  const back = paths.batch(batchId, 'exams')
  const { resource, reload } = useResource(() => readBatch(batchId), [batchId])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inCentre = useInCentre()
  const [examiner, setExaminer] = useState(DEFAULT_EXAMINER)

  async function create(values: ExamValues) {
    if (!values.subjectId) return
    setSaving(true)
    setError(null)
    try {
      await createExam(batchId, {
        title: values.title,
        date: values.date,
        total_marks: values.totalMarks,
        topics: values.topics,
        batch_subject_id: values.subjectId,
        ...(inCentre && examiner !== DEFAULT_EXAMINER ? { examiner_member_id: examiner } : {}),
      })
      // As Android: close on the server's answer, never on the tap.
      navigate(back, { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? message(e.messageKey) : t('error_unexpected'))
      setSaving(false)
    }
  }

  return (
    <>
      <TopBar
        title={t('screen_title_create_exam')}
        subtitle={resource.state === 'loaded' ? resource.data?.name : undefined}
        back={back}
      />
      {resource.state === 'loading' ? <Loading rows={3} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard
          title={t('exam_create_subjects_failed')}
          error={resource.error}
          onRetry={reload}
        />
      ) : null}
      {resource.state === 'loaded' ? (
        <div className="card">
          {inCentre ? <ExaminerPicker value={examiner} onChange={setExaminer} /> : null}
          <ExamFields
            subjects={resource.data?.subject_options ?? []}
            saving={saving}
            error={error}
            submitLabel={t('exam_create_submit')}
            onSubmit={(v) => void create(v)}
            onCancel={() => navigate(back)}
          />
        </div>
      ) : null}
    </>
  )
}
