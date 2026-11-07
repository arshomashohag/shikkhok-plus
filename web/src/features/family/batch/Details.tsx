/**
 * The family detail screens (Android `FamilyDetailScreens.kt` and
 * `MarksheetScreen.kt`): one class, one upcoming exam, one notice, and an
 * exam's marksheet.
 *
 * There is no single-class or single-notice read: a class comes from its
 * month's calendar (the link carries `?month=`), a notice from the seat's
 * teaching view. Either may have gone since the link was made, which is
 * said plainly ("This is no longer available.").
 */
import { useParams, useSearchParams } from 'react-router'
import { formatMark } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Section, TopBar } from '../../../ui/components'
import { parseYearMonth } from '../../teacher/classes/mappers'
import type { Reader } from '../reader'
import { readFamilyCalendar, readFamilyExam, readMarksheet, readTeaching } from './api'
import { dayLabel, timeRange } from './format'
import {
  dhakaMonth,
  formatAverage,
  mapExam,
  mapFamilyMonth,
  mapMarksheet,
  mapTeaching,
  MARK_LABEL,
  RESULT_STATE_LABEL,
  type Marksheet,
} from './mappers'
import { NoticeMeta } from './SeatBatch'
import { seatTitles, useSeatId, useSeatIdentity } from './seat'

function Missing() {
  const { t } = useT()
  return <div className="card meta">{t('family_detail_missing')}</div>
}

// ----------------------------------------------------------------- class

export function ClassDetail({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { sessionId = '' } = useParams()
  const [search] = useSearchParams()
  const month = parseYearMonth(search.get('month') ?? '') ?? dhakaMonth()
  const { t, lang } = useT()
  const { who } = seatTitles(useSeatIdentity(reader, seat))
  const { resource, reload } = useResource(
    (signal) =>
      readFamilyCalendar(reader, seat, month.year, month.month, signal).then(
        (m) => mapFamilyMonth(m).classes.find((c) => c.sessionId === sessionId) ?? null,
      ),
    [reader, seat, sessionId, month.year, month.month],
  )
  const title = t('family_class_title')
  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={title} subtitle={who} back />
        <Loading rows={3} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={title} subtitle={who} back />
        <ErrorCard title={title} error={resource.error} onRetry={reload} />
      </>
    )
  }
  const c = resource.data
  return (
    <>
      <TopBar title={title} subtitle={who} back />
      {!c ? (
        <Missing />
      ) : (
        <div className="card">
          <h2 className="fb-heading">{c.subjectName ?? dayLabel(c.date, lang)}</h2>
          <p className="meta">
            {dayLabel(c.date, lang)} · {timeRange(c.startTime, c.endTime, lang)}
            {c.state === 'cancelled' ? ` · ${t('session_cancelled_mark')}` : ''}
          </p>
          <h3 className="fb-subheading">
            {t(c.state === 'taken' ? 'classday_topics_covered' : 'family_planned_topics')}
          </h3>
          <p className={c.topic ? 'fb-topic' : 'meta'}>
            {c.topic ??
              t(c.state === 'taken' ? 'session_topic_unlogged' : 'class_no_topics_planned')}
          </p>
          {c.notes ? (
            <>
              <h3 className="fb-subheading">{t('family_class_notes')}</h3>
              <p className="fb-topic">{c.notes}</p>
            </>
          ) : null}
          <h3 className="fb-subheading">{t('family_attendance')}</h3>
          <p>{t(MARK_LABEL[c.mark])}</p>
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------------ exam

export function ExamDetail({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { examId = '' } = useParams()
  const { t, lang } = useT()
  const { who } = seatTitles(useSeatIdentity(reader, seat))
  const { resource, reload } = useResource(
    (signal) => readFamilyExam(reader, seat, examId, signal).then(mapExam),
    [reader, seat, examId],
  )
  const title = t('family_exam_title')
  return (
    <>
      <TopBar title={title} subtitle={who} back />
      {resource.state === 'loading' ? (
        <Loading rows={3} />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={title} error={resource.error} onRetry={reload} />
      ) : (
        <>
          <div className="card">
            <h2 className="fb-heading">{resource.data.title}</h2>
            <p className="meta">
              {[
                resource.data.subjectName,
                dayLabel(resource.data.date, lang),
                t('batch_exam_out_of', resource.data.totalMarks),
              ].join(' · ')}
            </p>
          </div>
          <Section title={t('family_exam_topics')}>
            {resource.data.topics.length === 0 ? (
              <div className="card meta">{t('family_exam_no_topics')}</div>
            ) : (
              <ul className="card flush list">
                {resource.data.topics.map((topic, i) => (
                  <li key={i} className="row" style={{ minHeight: 56 }}>
                    {topic}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------- notice

export function NoticeDetail({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { noticeId = '' } = useParams()
  const { t } = useT()
  const { batch, who } = seatTitles(useSeatIdentity(reader, seat))
  const { resource, reload } = useResource(
    (signal) =>
      readTeaching(reader, seat, signal).then(
        (v) => mapTeaching(v).notices.find((n) => n.id === noticeId) ?? null,
      ),
    [reader, seat, noticeId],
  )
  const title = t('family_notice_title')
  const subtitle = [batch, who].filter(Boolean).join(' · ') || undefined
  return (
    <>
      <TopBar title={title} subtitle={subtitle} back />
      {resource.state === 'loading' ? (
        <Loading rows={2} />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={title} error={resource.error} onRetry={reload} />
      ) : !resource.data ? (
        <Missing />
      ) : (
        <div className="card">
          <p className="fb-topic" style={{ marginTop: 0 }}>
            {resource.data.body}
          </p>
          <NoticeMeta postedAt={resource.data.postedAt} edited={resource.data.edited} />
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------- marksheet

export function MarksheetScreen({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { examId = '' } = useParams()
  const { t } = useT()
  const { who } = seatTitles(useSeatIdentity(reader, seat))
  const { resource, reload } = useResource(
    (signal) => readMarksheet(reader, seat, examId, signal).then(mapMarksheet),
    [reader, seat, examId],
  )
  const title = t('screen_title_marksheet')
  return (
    <>
      <TopBar title={title} subtitle={who} back />
      {resource.state === 'loading' ? (
        <Loading rows={3} />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={title} error={resource.error} onRetry={reload} />
      ) : (
        <MarksheetBody sheet={resource.data} />
      )}
    </>
  )
}

export function MarksheetBody({ sheet }: { sheet: Marksheet }) {
  const { t, plural } = useT()
  return (
    <>
      <div className="card">
        <h2 className="fb-heading">{sheet.examTitle}</h2>
        <p className="meta">{t(RESULT_STATE_LABEL[sheet.ownState])}</p>
        {sheet.ownMarks !== null ? (
          <p className="fb-mark">
            <strong>{formatMark(sheet.ownMarks)}</strong>
            <span className="meta">{t('student_out_of', sheet.totalMarks)}</span>
          </p>
        ) : null}
      </div>
      {sheet.published ? (
        <>
          <div className="card">
            {sheet.rank !== null ? (
              <p className="title" style={{ margin: '0 0 4px' }}>
                {t('marksheet_rank', sheet.rank, sheet.markedCount)}
              </p>
            ) : null}
            <p style={{ margin: '0 0 4px' }}>
              {t('marksheet_average', formatAverage(sheet.average))}
            </p>
            <p style={{ margin: 0 }}>{t('marksheet_highest', formatMark(sheet.highest))}</p>
          </div>
          {sheet.bands.length ? (
            <Section title={t('web_fb_bands_title')}>
              <ul className="card flush list">
                {sheet.bands.map((b) => (
                  <li key={`${b.low}-${b.high}`} className="row" style={{ minHeight: 56 }}>
                    <span className="grow">
                      {b.low}–{b.high}
                    </span>
                    <span className="meta">{plural('batches_student_count', b.count)}</span>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
        </>
      ) : (
        <div className="card meta">{t('marksheet_no_comparison')}</div>
      )}
    </>
  )
}
