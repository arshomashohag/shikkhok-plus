/**
 * T3 · Marks entry (`/exams/:examId/marks`), the web MarkEntryScreen.kt.
 *
 * **Continuous entry, keyboard first.** Every markable student has a box;
 * type a mark and press Enter to save it and move to the next student, or
 * Tab away (which also saves). The dock under the list names who is being
 * entered and offers Absent and the mark's history. On a phone the box
 * opens the decimal keyboard, which takes the place of Android's keypad.
 *
 * **Each mark is saved on its own, and the list is re-read after each**:
 * what a row shows is what the server recorded, never what was typed. A
 * refused mark (above the total, too precise) keeps the typed value in
 * its box with the server's message under it. Corrections after
 * publishing go through the same boxes; the server appends and supersedes,
 * and the history sheet shows both.
 *
 * Draft → review → publish: the publish bar above the list says how many
 * still need a result and offers Publish when none do. A refused publish
 * outlines the rows still missing one, as the design's review board does.
 */
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useParams, useSearchParams } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatMark, formatShortDate } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Sheet, TopBar } from '../../../ui/components'
import { readResults, updateExam, writeMark } from './api'
import { ExamFields, type ExamValues } from './ExamForm'
import {
  cleanTyped,
  mapResults,
  progressOf,
  rollLabel,
  STATE_KEYS,
  typedMark,
  type ExamResults,
  type ResultRow,
} from './mappers'
import { CancelExam, HistorySheet, PUBLISH_INCOMPLETE_KEY, PublishBar } from './parts'

export function MarkEntry() {
  const { examId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(
    (signal) => readResults(examId, signal).then(mapResults),
    [examId],
  )

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('screen_title_mark_entry')} back />
        <Loading rows={6} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('screen_title_mark_entry')} back />
        <ErrorCard title={t('screen_title_mark_entry')} error={resource.error} onRetry={reload} />
      </>
    )
  }
  return <Entry results={resource.data} reload={reload} stale={resource.error !== null} />
}

function Entry({
  results,
  reload,
  stale,
}: {
  results: ExamResults
  reload: () => void
  stale: boolean
}) {
  const { t, lang, message } = useT()
  const [search] = useSearchParams()
  const examId = results.exam.examId
  const editable = results.rows.filter((r) => r.editable)
  const [current, setCurrent] = useState<string | null>(
    () =>
      editable.find((r) => r.enrollmentId === search.get('seat'))?.enrollmentId ??
      editable.find((r) => r.state === 'not_entered')?.enrollmentId ??
      editable[0]?.enrollmentId ??
      null,
  )
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const [outlineMissing, setOutlineMissing] = useState(false)
  const [historyFor, setHistoryFor] = useState<ResultRow | null>(null)
  const [editing, setEditing] = useState(false)
  const inputs = useRef(new Map<string, HTMLInputElement>())
  const inFlight = useRef(new Map<string, string>())
  /** Rows just marked Absent: their box's blur must not also save the typed number. */
  const skipCommit = useRef(new Set<string>())

  useEffect(() => {
    if (current) inputs.current.get(current)?.focus()
  }, [current])

  const shown = (row: ResultRow) =>
    drafts[row.enrollmentId] ?? (row.marks !== null ? formatMark(row.marks) : '')

  const send = useCallback(
    async (row: ResultRow, body: { result_state: 'marked' | 'absent'; marks: number | null }) => {
      const key = `${body.result_state}:${body.marks ?? ''}`
      if (inFlight.current.get(row.enrollmentId) === key) return
      inFlight.current.set(row.enrollmentId, key)
      setRowErrors(({ [row.enrollmentId]: _, ...rest }) => rest)
      try {
        await writeMark(examId, { enrollment_id: row.enrollmentId, ...body })
        setDrafts(({ [row.enrollmentId]: _, ...rest }) => rest)
        reload()
      } catch (e) {
        setRowErrors((all) => ({
          ...all,
          [row.enrollmentId]:
            e instanceof ApiError ? message(e.messageKey, e.details) : t('error_unexpected'),
        }))
      } finally {
        inFlight.current.delete(row.enrollmentId)
      }
    },
    [examId, message, reload, t],
  )

  /** Save what is typed in a row, if it differs from what the server holds. */
  const commit = (row: ResultRow) => {
    if (skipCommit.current.delete(row.enrollmentId)) return
    const typed = drafts[row.enrollmentId]
    if (typed === undefined) return
    const mark = typedMark(typed)
    if (mark === null) {
      // There is no "un-enter": an emptied box goes back to what is recorded.
      setDrafts(({ [row.enrollmentId]: _, ...rest }) => rest)
      return
    }
    if (row.state === 'marked' && row.marks === mark) {
      setDrafts(({ [row.enrollmentId]: _, ...rest }) => rest)
      return
    }
    void send(row, { result_state: 'marked', marks: mark })
  }

  const moveNext = (row: ResultRow) => {
    const at = editable.findIndex((r) => r.enrollmentId === row.enrollmentId)
    const next = editable[at + 1]
    if (next) setCurrent(next.enrollmentId)
  }

  const onKey = (row: ResultRow) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit(row)
      moveNext(row)
    }
  }

  const currentRow = editable.find((r) => r.enrollmentId === current) ?? null
  const { done, of } = progressOf(results.rows)
  const missing = outlineMissing && results.toEnter > 0

  return (
    <>
      <TopBar
        title={`${results.exam.title} · ${t('batch_exam_out_of', results.exam.totalMarks)}`}
        subtitle={[results.exam.subjectName, formatShortDate(results.exam.date, lang)].join(' · ')}
        back
        actions={
          <>
            {of > 0 ? (
              <span className="amount mark-counter" aria-label={t('exam_entered_count', done, of)}>
                {t('mark_entry_counter', done, of)}
              </span>
            ) : null}
            {results.writable ? (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() => setEditing(true)}
              >
                {t('exam_edit_title')}
              </button>
            ) : null}
            {stale ? null : <CancelExam exam={results.exam} onCancelled={reload} />}
          </>
        }
      />
      {of > 0 ? (
        <div className="mark-progress" aria-hidden="true">
          <span style={{ width: `${(done / of) * 100}%` }} />
        </div>
      ) : null}

      {results.exam.cancelled ? (
        <p className="banner">{t('marks_exam_cancelled')}</p>
      ) : !results.writable ? (
        <p className="banner">{t('mark_entry_read_only')}</p>
      ) : null}
      {stale ? (
        <p className="banner" role="status">
          {t('error_network_unreachable')}
        </p>
      ) : null}

      {/* A wide window puts the entry dock beside the list, as W-T3 does. */}
      <div className="mark-layout">
        <div>
          {results.rows.length === 0 ? (
            <EmptyState title={t('mark_entry_empty_title')} body={t('mark_entry_empty_body')} />
          ) : (
            <>
              <PublishBar
                results={results}
                onPublished={reload}
                onRefused={(key) => setOutlineMissing(key === PUBLISH_INCOMPLETE_KEY)}
              />
              <ul className="card flush list mark-list" aria-label={t('screen_title_mark_entry')}>
                {results.rows.map((row, index) => {
                  const isCurrent = row.enrollmentId === current
                  const error = rowErrors[row.enrollmentId]
                  const flag = missing && row.editable && row.state === 'not_entered'
                  return (
                    <li
                      key={row.enrollmentId}
                      className={`mark-row${isCurrent ? ' current' : ''}${flag || error ? ' flagged' : ''}`}
                    >
                      <span className="mark-roll">{rollLabel(index)}</span>
                      <label className="mark-name" htmlFor={`mark-${row.enrollmentId}`}>
                        {row.displayName}
                      </label>
                      {row.editable && !stale ? (
                        <span className="mark-cell">
                          <input
                            id={`mark-${row.enrollmentId}`}
                            ref={(el) => {
                              if (el) inputs.current.set(row.enrollmentId, el)
                              else inputs.current.delete(row.enrollmentId)
                            }}
                            className={`mark-input${flag ? ' missing' : ''}`}
                            inputMode="decimal"
                            autoComplete="off"
                            enterKeyHint="next"
                            placeholder={row.state === 'absent' ? t('mark_entry_absent') : ''}
                            value={shown(row)}
                            onFocus={() => setCurrent(row.enrollmentId)}
                            onChange={(e) =>
                              setDrafts((d) => ({
                                ...d,
                                [row.enrollmentId]: cleanTyped(e.target.value),
                              }))
                            }
                            onBlur={() => commit(row)}
                            onKeyDown={onKey(row)}
                            aria-invalid={error || flag ? true : undefined}
                            aria-describedby={error ? `mark-${row.enrollmentId}-error` : undefined}
                          />
                          {error ? (
                            <span
                              className="field-error mark-error"
                              id={`mark-${row.enrollmentId}-error`}
                              role="alert"
                            >
                              {error}
                            </span>
                          ) : null}
                        </span>
                      ) : (
                        <span className="mark-value">
                          {row.state === 'joined_after'
                            ? t('mark_entry_locked')
                            : row.marks !== null
                              ? formatMark(row.marks)
                              : t(STATE_KEYS[row.state])}
                        </span>
                      )}
                      <span className="mark-out-of">
                        {row.state === 'joined_after'
                          ? ''
                          : t('mark_entry_out_of', results.exam.totalMarks)}
                      </span>
                    </li>
                  )
                })}
              </ul>
              <p className="meta mark-hint">{t('web_exams_keyboard_hint')}</p>
            </>
          )}
        </div>
        {currentRow && results.writable && !stale ? (
          <div className="mark-dock" aria-label={t('mark_entry_now_entering', '')}>
            <div className="grow">
              <div className="meta">
                {t(
                  'mark_entry_now_entering',
                  rollLabel(
                    results.rows.findIndex((r) => r.enrollmentId === currentRow.enrollmentId),
                  ),
                )}
              </div>
              <div className="title">{currentRow.displayName}</div>
            </div>
            {currentRow.hasHistory ? (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() => setHistoryFor(currentRow)}
              >
                {t('mark_history_open')}
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-outline btn-small"
              // Keep focus in the list: clicking must not blur-save first.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                skipCommit.current.add(currentRow.enrollmentId)
                setDrafts(({ [currentRow.enrollmentId]: _, ...rest }) => rest)
                void send(currentRow, { result_state: 'absent', marks: null })
                moveNext(currentRow)
              }}
            >
              {t('mark_entry_absent')}
            </button>
          </div>
        ) : null}
      </div>

      {historyFor ? (
        <HistorySheet examId={examId} row={historyFor} onClose={() => setHistoryFor(null)} />
      ) : null}
      {editing ? (
        <EditExamSheet results={results} onClose={() => setEditing(false)} onSaved={reload} />
      ) : null}
    </>
  )
}

/** Edit exam, as EditExamScreen: title, date, total and topics; the subject stays. */
function EditExamSheet({
  results,
  onClose,
  onSaved,
}: {
  results: ExamResults
  onClose: () => void
  onSaved: () => void
}) {
  const { t, message } = useT()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(values: ExamValues) {
    setSaving(true)
    setError(null)
    try {
      await updateExam(results.exam.examId, {
        title: values.title,
        date: values.date,
        total_marks: values.totalMarks,
        topics: values.topics,
      })
      onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? message(e.messageKey, e.details) : t('error_unexpected'))
      setSaving(false)
    }
  }

  return (
    <Sheet title={t('exam_edit_title')} onClose={onClose}>
      <ExamFields
        initial={{
          title: results.exam.title,
          date: results.exam.date,
          totalMarks: results.exam.totalMarks,
          topics: results.exam.topics,
        }}
        saving={saving}
        error={error}
        submitLabel={t('exam_edit_save')}
        onSubmit={(v) => void save(v)}
        onCancel={onClose}
      />
    </Sheet>
  )
}
