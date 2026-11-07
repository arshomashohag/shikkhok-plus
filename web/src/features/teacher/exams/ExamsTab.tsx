/**
 * T7 · Exams tab: needs marks, coming up, and marked (newest first), as
 * ExamsTab.kt groups them. A marked exam opens its results; any other
 * opens mark entry. "Draft · not published" marks a marked exam families
 * cannot see yet. A cancelled exam stays on the tab under its own heading
 * with a Cancelled chip, and opens its read-only results.
 */
import { Link } from 'react-router'
import { formatShortDate } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Section } from '../../../ui/components'
import { PlusIcon } from '../../../ui/icons'
import type { BatchTabProps } from '../area'
import { paths } from '../paths'
import { listExams } from './api'
import { groupExams, mapExam, type ExamItem } from './mappers'

export function ExamsTab({ batchId }: BatchTabProps) {
  const { t } = useT()
  const { resource, reload } = useResource(
    (signal) => listExams(batchId, signal).then((rows) => rows.map(mapExam)),
    [batchId],
  )

  const fab = (
    <Link to={paths.examNew(batchId)} className="btn btn-primary fab">
      <PlusIcon />
      {t('screen_title_create_exam')}
    </Link>
  )

  if (resource.state === 'loading') return <Loading rows={3} />
  if (resource.state === 'failed') {
    return <ErrorCard title={t('batch_exams_failed')} error={resource.error} onRetry={reload} />
  }
  if (resource.data.length === 0) {
    return (
      <>
        <EmptyState
          title={t('batch_exams_empty')}
          body={t('batch_exams_empty_body')}
          action={
            <Link to={paths.examNew(batchId)} className="btn btn-primary btn-money">
              {t('exams_add')}
            </Link>
          }
        />
      </>
    )
  }

  return (
    <>
      {groupExams(resource.data).map((group) => (
        <Section key={group.titleKey} title={t(group.titleKey)}>
          <ul className="card flush list">
            {group.exams.map((exam) => (
              <ExamRow key={exam.examId} exam={exam} />
            ))}
          </ul>
        </Section>
      ))}
      <div style={{ height: 72 }} />
      {fab}
    </>
  )
}

function ExamRow({ exam }: { exam: ExamItem }) {
  const { t, lang } = useT()
  const to =
    exam.state === 'complete' || exam.cancelled
      ? paths.examResults(exam.examId)
      : paths.examMarks(exam.examId)
  return (
    <li>
      <Link className="row" to={to} style={{ minHeight: 64 }}>
        <div className="grow">
          <div className="title">{exam.title}</div>
          <div className="meta">
            {[
              exam.subjectName,
              formatShortDate(exam.date, lang),
              t('batch_exam_out_of', exam.totalMarks),
            ].join(' · ')}
          </div>
          {exam.state === 'complete' && !exam.published && !exam.cancelled ? (
            <div className="meta accent">{t('batch_exam_draft')}</div>
          ) : null}
        </div>
        {exam.cancelled ? (
          <span className="chip exam-cancelled-chip">{t('exam_cancelled_chip')}</span>
        ) : null}
        {exam.state === 'needs_marks' && !exam.cancelled ? (
          <span className="btn btn-tonal btn-small" aria-hidden="true">
            {t('batch_enter_marks')}
          </span>
        ) : null}
        {exam.state === 'complete' && !exam.cancelled ? (
          <span className="meta">
            {t('batch_exam_entered', exam.enteredCount, exam.expectedCount)}
          </span>
        ) : null}
      </Link>
    </li>
  )
}
