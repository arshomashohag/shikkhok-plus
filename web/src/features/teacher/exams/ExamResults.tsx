/**
 * Results (`/exams/:examId/results`): a marked exam, read-only, for
 * review before publishing and for checking after. Each recorded result
 * opens its history; corrections are made on the marks screen, which this
 * links to for the whole exam or one student.
 *
 * What it shows is the server's: each seat's state and mark, whether the
 * exam is published, and whether it is still writable. No average or
 * rank is worked out here; families see those on their marksheet, which
 * the server computes.
 */
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { formatMark, formatShortDate } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { useInCentre } from '../../../session/useInCentre'
import { ExaminerControl } from './Examiner'
import { EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { paths } from '../paths'
import { readResults } from './api'
import { mapResults, progressOf, rollLabel, STATE_KEYS, type ResultRow } from './mappers'
import { CancelExam, HistorySheet, PublishBar } from './parts'

export function ExamResults() {
  const { examId = '' } = useParams()
  const inCentre = useInCentre()
  const { t, lang } = useT()
  const { resource, reload } = useResource(
    (signal) => readResults(examId, signal).then(mapResults),
    [examId],
  )
  const [historyFor, setHistoryFor] = useState<ResultRow | null>(null)

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('student_results')} back />
        <Loading rows={6} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('student_results')} back />
        <ErrorCard title={t('student_results')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const results = resource.data
  const { done, of } = progressOf(results.rows)
  const fresh = resource.error === null
  return (
    <>
      <TopBar
        title={`${results.exam.title} · ${t('batch_exam_out_of', results.exam.totalMarks)}`}
        subtitle={[
          results.exam.subjectName,
          formatShortDate(results.exam.date, lang),
          of > 0 ? t('exam_entered_count', done, of) : null,
        ]
          .filter(Boolean)
          .join(' · ')}
        back
        actions={fresh ? <CancelExam exam={results.exam} onCancelled={reload} /> : undefined}
      />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      {!results.exam.published && results.writable ? (
        <p className="meta accent">{t('batch_exam_draft')}</p>
      ) : null}
      {results.exam.cancelled ? (
        <p className="banner">{t('marks_exam_cancelled')}</p>
      ) : !results.writable ? (
        <p className="banner">{t('mark_entry_read_only')}</p>
      ) : null}

      {inCentre ? (
        <div className="card">
          <ExaminerControl examId={examId} />
        </div>
      ) : null}

      {results.rows.length === 0 ? (
        <EmptyState title={t('mark_entry_empty_title')} body={t('mark_entry_empty_body')} />
      ) : (
        <>
          {fresh ? <PublishBar results={results} onPublished={reload} /> : null}
          <ul className="card flush list mark-list">
            {results.rows.map((row, index) => (
              <li key={row.enrollmentId} className="mark-row">
                <span className="mark-roll">{rollLabel(index)}</span>
                <span className="mark-name">{row.displayName}</span>
                <span className="mark-value">
                  {row.marks !== null ? (
                    <>
                      <strong>{formatMark(row.marks)}</strong>
                      <span className="meta">
                        {t('mark_entry_out_of', results.exam.totalMarks)}
                      </span>
                    </>
                  ) : (
                    <span className={row.state === 'not_entered' ? 'meta danger' : 'meta'}>
                      {t(STATE_KEYS[row.state])}
                    </span>
                  )}
                </span>
                <span className="mark-actions">
                  {row.hasHistory ? (
                    <button
                      type="button"
                      className="btn btn-text btn-small"
                      onClick={() => setHistoryFor(row)}
                      aria-label={`${t('mark_history_open')} · ${row.displayName}`}
                    >
                      {t('mark_history_open')}
                    </button>
                  ) : null}
                  {row.editable && fresh ? (
                    <Link
                      className="btn btn-text btn-small"
                      to={`${paths.examMarks(examId)}?seat=${encodeURIComponent(row.enrollmentId)}`}
                      aria-label={`${t('web_exams_correct_one')} · ${row.displayName}`}
                    >
                      {t('web_exams_correct_one')}
                    </Link>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
          {results.writable && fresh ? (
            <div className="button-row">
              <Link className="btn btn-tonal grow" to={paths.examMarks(examId)}>
                {t('web_exams_correct')}
              </Link>
            </div>
          ) : null}
        </>
      )}
      {historyFor ? (
        <HistorySheet examId={examId} row={historyFor} onClose={() => setHistoryFor(null)} />
      ) : null}
    </>
  )
}
