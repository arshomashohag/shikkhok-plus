/**
 * T1 · Today. The teacher's day: what is owed, the classes on today, and
 * payments waiting to be checked.
 */
import { Link } from 'react-router'
import { readToday } from '../../api/endpoints'
import {
  ago,
  formatClock,
  formatLongDay,
  formatShortMonth,
  initial,
  splitClock,
} from '../../core/format'
import { useResource } from '../../core/useResource'
import { useWide } from '../../core/useWide'
import { useT } from '../../i18n/i18n'
import { Avatar, ErrorCard, Loading, Section, StaleBanner, TopBar } from '../../ui/components'
import { CheckIcon, WarningIcon } from '../../ui/icons'
import { paths } from './paths'
import { mapToday, reviewName, type TodayClass, type TodayModel } from './mappers'

export function Today() {
  const { t } = useT()
  const { resource, reload } = useResource(() => readToday().then(mapToday), [])

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('today_title')} />
        <Loading rows={2} />
        <Section title={t('today_classes')}>
          <Loading rows={2} />
        </Section>
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('today_title')} />
        <ErrorCard title={t('today_load_failed')} error={resource.error} onRetry={reload} />
      </>
    )
  }
  return (
    <TodayLoaded
      model={resource.data}
      stale={resource.error ? { error: resource.error, at: resource.loadedAt } : null}
    />
  )
}

function TodayLoaded({
  model,
  stale,
}: {
  model: TodayModel
  stale: { error: import('../../api/errors').ApiError; at: Date } | null
}) {
  const { t, lang } = useT()
  const wide = useWide()
  const day = formatLongDay(model.date, lang)

  if (!model.hasBatches) {
    return (
      <>
        <TopBar title={t('today_title')} subtitle={day} />
        <div className="card">
          <h2 style={{ margin: '0 0 12px', fontSize: '1.125rem' }}>{t('today_first_run_title')}</h2>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.6 }}>
            <li>{t('today_step_one')}</li>
            <li>{t('today_step_two')}</li>
            <li>{t('today_step_three')}</li>
          </ol>
          <div className="button-row">
            <Link className="btn btn-primary grow" to="/batches/new">
              {t('today_create_batch')}
            </Link>
          </div>
        </div>
        <Section title={t('today_classes')}>
          <div className="card meta">{t('today_classes_empty')}</div>
        </Section>
        <Section title={t('today_to_verify')}>
          <div className="card meta">{t('today_to_verify_empty')}</div>
        </Section>
      </>
    )
  }

  const next = model.classes.find((c) => c.isNext && c.status !== 'cancelled') ?? null
  const nextTitle = next ? [next.subjectName, next.batchName].filter(Boolean).join(' · ') : ''

  return (
    <>
      <TopBar
        title={t('today_title')}
        subtitle={day}
        actions={
          wide ? (
            <>
              <Link to={paths.studentNew()} className="btn btn-outline">
                {t('students_add')}
              </Link>
              <Link to="/batches/new" className="btn btn-primary">
                {t('batch_create_title')}
              </Link>
            </>
          ) : null
        }
      />
      {stale ? <StaleBanner error={stale.error} loadedAt={stale.at} /> : null}

      {/* Three figures across a wide window; a phone keeps only what is
          owed, since the two lists below already carry the rest. */}
      <div className="dash dash-3" style={{ marginTop: stale ? 12 : 0 }}>
        <Link to="/dues" className="card kpi">
          <div className="label">{t('today_outstanding', model.outstanding.batchCount)}</div>
          <div className="figure">{model.outstanding.total.format()}</div>
          {model.outstanding.overdue.isZero() ? null : (
            <div>
              <span className="chip chip-overdue">
                <WarningIcon size={14} />
                {t(
                  'today_overdue',
                  model.outstanding.overdue.format(),
                  model.outstanding.overdueStudents,
                )}
              </span>
            </div>
          )}
        </Link>
        {wide ? (
          <>
            <Link to={paths.verify()} className="card kpi">
              <div className="label">{t('verify_title')}</div>
              <div className="figure">{model.toVerifyCount}</div>
              <div className="meta">
                {model.toVerifyCount > 0 ? t('web_today_waiting') : t('web_today_nothing_waiting')}
              </div>
            </Link>
            <div className="card kpi">
              <div className="label">{t('today_classes')}</div>
              <div className="figure">{model.classes.length}</div>
              <div className="meta">
                {next
                  ? next.startsInMinutes !== null
                    ? t('web_today_next_in', nextTitle, next.startsInMinutes)
                    : t('web_today_next_class', nextTitle, formatClock(next.startTime, lang))
                  : t('web_today_no_next')}
              </div>
            </div>
          </>
        ) : null}
      </div>

      <div className="dash dash-3-2">
        <section className="card flush" aria-labelledby="today-classes">
          <div className="panel-head">
            <h2 id="today-classes">{t('today_classes_count', model.classes.length)}</h2>
          </div>
          {model.classes.length === 0 ? (
            <div className="meta" style={{ padding: '16px 20px' }}>
              {t('today_no_classes')}
            </div>
          ) : (
            <ul className="list">
              {model.classes.map((c) => (
                <ClassRow key={c.sessionId} item={c} />
              ))}
            </ul>
          )}
        </section>

        <section className="card flush" aria-labelledby="today-verify">
          <div className="panel-head">
            <h2 id="today-verify">{t('today_to_verify_count', model.toVerifyCount)}</h2>
            {model.toVerifyCount > 0 ? (
              <Link to={paths.verify()} className="btn btn-text btn-small">
                {t('today_see_all')}
              </Link>
            ) : null}
          </div>
          {model.toVerify.length === 0 ? (
            <div className="meta" style={{ padding: '16px 20px' }}>
              {t('today_nothing_to_verify')}
            </div>
          ) : (
            <>
              <ul className="list">
                {model.toVerify.map((r) => {
                  const name = reviewName(r)
                  const period = r.children[0]?.period
                  return (
                    <li key={r.submissionId}>
                      <Link className="row" to={paths.payment(r.submissionId)}>
                        <Avatar letter={initial(name)} />
                        <div className="grow">
                          <div className="title">{name}</div>
                          <div className="meta">
                            {[
                              r.channelLabel,
                              period ? formatShortMonth(period, lang) : null,
                              ago(r.submittedAt, new Date(), t),
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                          </div>
                        </div>
                        <div className="end">
                          <span className="amount">{r.totalAmount.format()}</span>
                          <span className="meta">
                            {r.comparison === 'matches'
                              ? t('today_matches_fee')
                              : r.comparison === 'short'
                                ? t('verify_line_short', r.difference.format())
                                : t('verify_line_over', r.difference.format())}
                          </span>
                        </div>
                      </Link>
                    </li>
                  )
                })}
              </ul>
              {wide ? (
                <div style={{ padding: '0 20px 20px' }}>
                  <Link to={paths.verify()} className="btn btn-primary" style={{ width: '100%' }}>
                    {t('web_today_review')}
                  </Link>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </>
  )
}

function ClassRow({ item }: { item: TodayClass }) {
  const { t, lang } = useT()
  const clock = splitClock(item.startTime, lang)
  const title = [item.subjectName, item.batchName].filter(Boolean).join(' · ')
  let status: React.ReactNode
  if (item.status === 'cancelled') {
    status = <span className="meta danger">{t('today_cancelled')}</span>
  } else if (item.topicLogged && item.topic) {
    status = (
      <span className="meta">
        <CheckIcon size={14} style={{ verticalAlign: '-2px', marginRight: 4 }} />
        {item.topic}
      </span>
    )
  } else if (item.isNext && item.startsInMinutes !== null) {
    status = <span className="meta accent">{t('today_next_in', item.startsInMinutes)}</span>
  } else if (item.examTitle) {
    status = <span className="meta">{t('today_exam', item.examTitle)}</span>
  } else {
    status = <span className="meta">{t('today_not_recorded')}</span>
  }
  // T1: a class not yet recorded offers Record; an exam day offers Marks.
  // Both open a screen; nothing is written from this row.
  const action =
    item.status === 'cancelled'
      ? null
      : item.examId
        ? { to: paths.examMarks(item.examId), label: t('today_marks') }
        : !item.topicLogged
          ? { to: paths.session(item.batchId, item.sessionId), label: t('today_record') }
          : null
  return (
    <li className={item.isNext ? 'row highlight' : 'row'}>
      <Link className="today-class" to={paths.session(item.batchId, item.sessionId)}>
        <div style={{ width: 56, flexShrink: 0 }}>
          <div className="amount">{clock.time}</div>
          <div className="meta">{clock.meridiem}</div>
        </div>
        <div className="grow">
          <div className="title">{title}</div>
          {status}
        </div>
      </Link>
      {action ? (
        <Link className="btn btn-tonal btn-small" to={action.to}>
          {action.label}
        </Link>
      ) : null}
    </li>
  )
}
