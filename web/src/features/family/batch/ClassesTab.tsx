/**
 * The seat's classes, one month at a time, browsable as Android's calendar
 * is (previous and next stop at the first and last month the server says
 * has classes). Two lists, as the design's S2 reads: what was covered,
 * newest first, with whether the student was there; then what is coming
 * up, soonest first. The server's state decides which list a class is in.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Section } from '../../../ui/components'
import { useHeading } from './seat'
import { BackIcon, ChevronIcon } from '../../../ui/icons'
import { compareMonths, shiftMonth, type YearMonth } from '../../teacher/classes/mappers'
import { familyPaths, type Reader } from '../reader'
import { readFamilyCalendar } from './api'
import { formatShortDate } from '../../../core/format'
import { monthTitle, timeRange, weekdayLabel } from './format'
import {
  dhakaMonth,
  mapFamilyMonth,
  MARK_LABEL,
  monthKey,
  STATE_LABEL,
  type FamilyClass,
  type SeatIdentity,
} from './mappers'

export function ClassesTab({
  reader,
  seat,
  identity,
}: {
  reader: Reader
  seat: string
  identity: SeatIdentity | null
}) {
  const { t, lang } = useT()
  const heading = useHeading()
  const [shown, setShown] = useState<YearMonth>(() => dhakaMonth())
  const { resource, reload } = useResource(
    () => readFamilyCalendar(reader, seat, shown.year, shown.month).then(mapFamilyMonth),
    [reader, seat, shown.year, shown.month],
  )

  if (resource.state === 'loading') return <Loading rows={4} />
  if (resource.state === 'failed') {
    return <ErrorCard title={t('batch_classes_failed')} error={resource.error} onRetry={reload} />
  }
  const m = resource.data
  const canPrev = compareMonths(m, m.first) > 0
  const canNext = compareMonths(m, m.last) < 0
  const comingUp = m.classes.filter((c) => c.state === 'upcoming').reverse()
  const covered = m.classes.filter((c) => c.state !== 'upcoming')
  const link = (c: FamilyClass) =>
    `${familyPaths.session(reader, seat, c.sessionId)}?month=${monthKey(m)}`

  return (
    <>
      <div className="fb-month">
        <button
          type="button"
          className="icon-btn"
          disabled={!canPrev}
          aria-label={t('calendar_prev_month')}
          onClick={() => setShown(shiftMonth(m, -1))}
        >
          <BackIcon />
        </button>
        <h2 className="fb-month-title" aria-live="polite">
          {monthTitle(m.year, m.month, lang)}
        </h2>
        <button
          type="button"
          className="icon-btn"
          disabled={!canNext}
          aria-label={t('calendar_next_month')}
          onClick={() => setShown(shiftMonth(m, 1))}
        >
          <ChevronIcon />
        </button>
      </div>
      {m.classes.length === 0 ? (
        <EmptyState title={t('web_fb_no_classes_month')} body={t('student_topics_empty')} />
      ) : null}
      {covered.length ? (
        <Section title={heading(identity, 'student_topics', 'web_fb_child_topics')}>
          <ul className="card flush list">
            {covered.map((c) => (
              <li key={c.sessionId}>
                <ClassRow c={c} to={link(c)} />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {comingUp.length ? (
        <Section title={heading(identity, 'student_coming_up', 'web_fb_child_coming_up')}>
          <ul className="card flush list">
            {comingUp.map((c) => (
              <li key={c.sessionId}>
                <ClassRow c={c} to={link(c)} />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  )
}

function ClassRow({ c, to }: { c: FamilyClass; to: string }) {
  const { t, lang } = useT()
  return (
    <Link className="row fb-class" to={to}>
      <span className="fb-class-date">
        <strong>{formatShortDate(c.date, lang)}</strong>
        <span className="meta">{weekdayLabel(c.date, lang)}</span>
      </span>
      <span className="grow">
        {/* An upcoming class with nothing planned shows just its time: a
            column of "No topics planned yet" says nothing. */}
        {c.state === 'upcoming' && !c.topic ? null : (
          <span className={c.topic ? 'fb-topic' : 'fb-topic meta'}>
            {c.state === 'cancelled'
              ? t('session_cancelled_mark')
              : (c.topic ??
                (c.state === 'taken' ? t('session_topic_unlogged') : t(STATE_LABEL[c.state])))}
          </span>
        )}
        <span className="meta" style={{ display: 'block' }}>
          {[
            c.subjectName,
            timeRange(c.startTime, c.endTime, lang),
            c.state === 'taken' ? t(MARK_LABEL[c.mark]) : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </span>
      <ChevronIcon />
    </Link>
  )
}
