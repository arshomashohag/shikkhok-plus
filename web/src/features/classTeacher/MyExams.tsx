/**
 * The exams this person marks at a centre, and one exam's marks: enter a
 * number or mark absent per student, then publish. Names and results only;
 * whether a mark may be entered, and whether the sheet is complete enough to
 * publish, are the server's answers.
 */
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import {
  listMyExams,
  publishMyExam,
  readMyExamResults,
  writeMyExamMark,
  type Schemas,
} from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { formatLongDay, formatMark } from '../../core/format'
import { toLatinDigits } from '../../core/money'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Snackbar, TopBar } from '../../ui/components'
import { ChevronIcon, WarningIcon } from '../../ui/icons'

type Examinee = Schemas['ExamineeResponse']

/** The state line under a student, from the server's result state. */
export function resultKey(row: Examinee): string | null {
  if (row.result_state === 'absent') return 'my_exam_absent'
  if (row.result_state === 'joined_after') return 'my_exam_joined_after'
  if (row.result_state === 'not_entered') return 'my_exam_not_entered'
  return null
}

/** Digits with at most one point: what a mark may be typed as. */
const MARK_SHAPE = /^(\d+(\.\d*)?|\.\d+)$/

/**
 * The mark to send for a typed number, or null while it is not one.
 * Bangla digits are read as Latin; anything but plain decimal digits
 * (`0x10`, `1e2`, `Infinity`) is not a mark. Format only: whether it is
 * within the exam's total is the server's answer.
 */
export function markBody(enrollmentId: string, typed: string): Schemas['MarkWriteRequest'] | null {
  const latin = toLatinDigits(typed).trim()
  if (!MARK_SHAPE.test(latin)) return null
  return { enrollment_id: enrollmentId, result_state: 'marked', marks: Number(latin) }
}

export function MyExams() {
  const { t, lang } = useT()
  const { resource, reload } = useResource((signal) => listMyExams(signal), [])
  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('my_exams_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = <EmptyState title={t('my_exams_title')} body={t('my_exams_empty')} />
  else
    body = (
      <ul className="card flush list">
        {resource.data.map((exam) => (
          <li key={exam.exam_id}>
            <Link
              className="row"
              to={`/my-exams/${exam.exam_id}`}
              style={exam.cancelled ? { opacity: 0.55 } : undefined}
            >
              <span className="grow">
                <span className="title">
                  {exam.title} · {exam.subject_name}
                </span>
                <br />
                <span className="meta">
                  {[
                    exam.batch_name,
                    exam.centre_name,
                    formatLongDay(exam.date, lang),
                    exam.cancelled
                      ? t('timetable_cancelled')
                      : exam.published
                        ? t('my_exam_published')
                        : t('my_exam_draft'),
                  ].join(' · ')}
                </span>
              </span>
              <ChevronIcon />
            </Link>
          </li>
        ))}
      </ul>
    )
  return (
    <>
      <TopBar title={t('my_exams_title')} />
      {body}
    </>
  )
}

function MarkRow({
  examId,
  row,
  total,
  writable,
  onSaved,
  onFailed,
}: {
  examId: string
  row: Examinee
  total: number
  writable: boolean
  onSaved: () => void
  onFailed: (text: string) => void
}) {
  const { t, message } = useT()
  const [typed, setTyped] = useState(
    row.marks === null || row.marks === undefined ? '' : String(row.marks),
  )
  const [busy, setBusy] = useState(false)
  const state = resultKey(row)

  async function send(body: Schemas['MarkWriteRequest']) {
    setBusy(true)
    try {
      await writeMyExamMark(examId, body)
      onSaved()
    } catch (e) {
      onFailed(e instanceof ApiError ? message(e.messageKey, e.details) : t('error_unexpected'))
    } finally {
      setBusy(false)
    }
  }

  const mark = markBody(row.enrollment_id, typed)
  return (
    <li>
      <div className="row">
        <span className="grow">
          <span className="title">{row.display_name}</span>
          {state ? (
            <>
              <br />
              <span className="meta">{t(state)}</span>
            </>
          ) : row.marks !== null && row.marks !== undefined ? (
            <>
              <br />
              <span className="meta">
                {formatMark(row.marks)} / {total}
              </span>
            </>
          ) : null}
        </span>
        {writable && row.result_state !== 'joined_after' ? (
          <>
            <input
              aria-label={t('my_exam_marks_label', total)}
              inputMode="decimal"
              style={{ width: 72 }}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={!mark || busy}
              onClick={() => mark && void send(mark)}
            >
              {t('my_exam_save')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={busy}
              onClick={() =>
                void send({ enrollment_id: row.enrollment_id, result_state: 'absent' })
              }
            >
              {t('my_exam_absent')}
            </button>
          </>
        ) : null}
      </div>
    </li>
  )
}

export function MyExamMarks() {
  const { examId = '' } = useParams()
  const { t, message } = useT()
  const { resource, reload } = useResource((signal) => readMyExamResults(examId, signal), [examId])
  const [snack, setSnack] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function publish() {
    setBusy(true)
    setFailure(null)
    try {
      await publishMyExam(examId)
      setSnack(t('my_exam_published_done'))
      reload()
    } catch (e) {
      setFailure(e instanceof ApiError ? message(e.messageKey, e.details) : t('error_unexpected'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <TopBar
        title={resource.state === 'loaded' ? resource.data.exam.title : t('my_exams_title')}
        subtitle={
          resource.state === 'loaded'
            ? `${resource.data.exam.batch_name} · ${resource.data.exam.subject_name}`
            : undefined
        }
        back="/my-exams"
      />
      {resource.state === 'loading' ? <Loading rows={3} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('my_exams_title')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' ? (
        <>
          <ul className="card flush list">
            {resource.data.results.map((row) => (
              <MarkRow
                key={`${row.enrollment_id}-${row.result_state}-${row.marks ?? ''}`}
                examId={examId}
                row={row}
                total={resource.data.exam.total_marks}
                writable={resource.data.writable}
                onSaved={() => {
                  setSnack(t('my_class_saved'))
                  reload()
                }}
                onFailed={setFailure}
              />
            ))}
          </ul>
          {failure ? (
            <div className="banner error" role="alert" style={{ marginTop: 12 }}>
              <WarningIcon />
              <span>{failure}</span>
            </div>
          ) : null}
          {resource.data.writable && !resource.data.exam.published ? (
            <div className="button-row">
              <button
                type="button"
                className="btn btn-primary grow"
                disabled={busy}
                onClick={() => void publish()}
              >
                {t('my_exam_publish')}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
