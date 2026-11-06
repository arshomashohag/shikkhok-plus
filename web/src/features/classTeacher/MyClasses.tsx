/**
 * A centre teacher's classes: a week at a time, across every centre they
 * teach at, each opening to its roster and topic. The list is the
 * server's: only classes assigned to this account appear.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { listMyClasses } from '../../api/endpoints'
import { formatClock, formatLongDay } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Section, TopBar } from '../../ui/components'
import { ChevronIcon } from '../../ui/icons'
import { byDay, isoDay, shiftWeek, weekFrom } from '../teacher/centre/timetable'

export function MyClasses() {
  const { t, lang } = useT()
  const [start, setStart] = useState(() => isoDay(new Date()))
  const days = weekFrom(start)
  const { resource, reload } = useResource(() => listMyClasses(start, days[6] ?? start), [start])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('my_classes_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = <EmptyState title={t('my_classes_title')} body={t('my_classes_empty')} />
  else
    body = byDay(
      days,
      resource.data.map((c) => ({ ...c, batch_id: '', overridden: false })),
    )
      .filter(([, list]) => list.length > 0)
      .map(([day, list]) => (
        <Section key={day} title={formatLongDay(day, lang)}>
          <ul className="card flush list">
            {list.map((c) => {
              const mine = resource.data.find((m) => m.session_id === c.session_id)
              return (
                <li key={c.session_id}>
                  <Link
                    className="row"
                    to={`/my-classes/${c.session_id}`}
                    style={c.status === 'cancelled' ? { opacity: 0.55 } : undefined}
                  >
                    <span className="meta" style={{ minWidth: 64 }}>
                      {formatClock(c.start_time, lang)}
                    </span>
                    <span className="grow">
                      <span className="title">
                        {c.batch_name}
                        {c.subject ? ` · ${c.subject}` : ''}
                      </span>
                      <br />
                      <span className="meta">
                        {[
                          mine?.centre_name,
                          c.room_name,
                          c.status === 'cancelled' ? t('timetable_cancelled') : null,
                          mine?.topic_logged ? t('my_class_topic_logged') : null,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </span>
                    <ChevronIcon />
                  </Link>
                </li>
              )
            })}
          </ul>
        </Section>
      ))

  return (
    <>
      <TopBar title={t('my_classes_title')} subtitle={t('my_classes_sub')} />
      <div className="button-row" style={{ marginTop: 0, marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-text btn-small"
          onClick={() => setStart(shiftWeek(start, -1))}
        >
          ‹ {t('timetable_prev_week')}
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-text btn-small"
          onClick={() => setStart(shiftWeek(start, 1))}
        >
          {t('timetable_next_week')} ›
        </button>
      </div>
      {body}
    </>
  )
}
