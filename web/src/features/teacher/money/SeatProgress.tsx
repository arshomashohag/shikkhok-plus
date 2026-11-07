/**
 * One student's progress, as their teacher sees it (`DashboardScreen.kt`,
 * teacher reader): attendance, exam average and what is owed as tiles,
 * then attendance by month, exam marks against the batch, and the fee
 * months with a link back to the fee history.
 */
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { formatMark, formatShortDate, formatShortMonth } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import type { Schemas } from '../../../api/endpoints'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Section, StaleBanner, TopBar } from '../../../ui/components'
import { readSeatDashboard, type DashboardRange } from './api'
import { ARROW, mapDashboard, type Dashboard } from './dashboard'
import { moneyPaths } from './paths'
import { MonthStrip } from './SeatFees'

const RANGES: [DashboardRange, string][] = [
  ['6m', 'dashboard_range_6m'],
  ['year', 'dashboard_range_year'],
  ['all', 'dashboard_range_all'],
]

export function SeatProgress() {
  const { enrollmentId = '' } = useParams()
  const [search] = useSearchParams()
  const name = search.get('name') ?? undefined
  const batch = search.get('batch') ?? undefined
  const { t } = useT()
  return (
    <DashboardView
      title={t('screen_title_progress')}
      subtitle={[name, batch].filter(Boolean).join(' · ') || undefined}
      load={(range, signal) => readSeatDashboard(enrollmentId, range, signal)}
      feesLink={moneyPaths.seatFees(enrollmentId, name, batch)}
      cacheKey={enrollmentId}
    />
  )
}

/**
 * The seat dashboard for any reader: the teacher's view of a student and
 * the family's own view read the same response shape from different
 * endpoints (`DashboardScreen.kt` takes a reader for the same reason).
 */
export function DashboardView({
  title,
  subtitle,
  load,
  feesLink,
  cacheKey,
}: {
  title: string
  subtitle?: string
  load: (range: DashboardRange, signal: AbortSignal) => Promise<Schemas['DashboardResponse']>
  feesLink: string
  /** Re-read when this changes (the seat). */
  cacheKey: string
}) {
  const { t } = useT()
  const [range, setRange] = useState<DashboardRange>('6m')
  const { resource, reload } = useResource(
    (signal) => load(range, signal).then(mapDashboard),
    [cacheKey, range],
  )

  return (
    <>
      <TopBar title={title} subtitle={subtitle} back />
      <div className="chips" role="group" aria-label={title}>
        {RANGES.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className="chip chip-filter"
            aria-pressed={range === value}
            onClick={() => setRange(value)}
          >
            {t(label)}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 12 }}>
        {resource.state === 'loading' ? (
          <Loading rows={4} />
        ) : resource.state === 'failed' ? (
          <ErrorCard title={t('dashboard_load_failed')} error={resource.error} onRetry={reload} />
        ) : (
          <>
            {resource.error ? (
              <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
            ) : null}
            <Body d={resource.data} feesLink={feesLink} />
          </>
        )}
      </div>
    </>
  )
}

function Body({ d, feesLink }: { d: Dashboard; feesLink: string }) {
  const { t, lang } = useT()
  const latest = d.exams[d.exams.length - 1] ?? null
  return (
    <>
      <div className="money-tiles">
        <div className="card">
          <div className="label">{t('dashboard_tile_attendance')}</div>
          <div className="hero-amount">
            {d.attendancePercent === null ? '–' : `${d.attendancePercent}%`}
          </div>
          <div className="meta">{t('dashboard_tile_attendance_of', d.present, d.held)}</div>
        </div>
        <div className="card">
          <div className="label">{t('dashboard_tile_exam')}</div>
          <div className="hero-amount">
            {d.examAveragePercent === null ? '–' : `${d.examAveragePercent}%`}
          </div>
          <div className="meta">
            {d.examAveragePercent === null
              ? t('dashboard_tile_exam_none')
              : t(
                  'dashboard_tile_exam_note',
                  d.exams.length,
                  d.direction ? ARROW[d.direction] : '',
                )}
          </div>
        </div>
        <div className="card">
          <div className="label">{t('dashboard_tile_fees')}</div>
          <div className="hero-amount">{d.owed.format()}</div>
          <div className="meta">{t('dashboard_tile_owed')}</div>
        </div>
      </div>

      <Section title={t('dashboard_attendance_title')}>
        <ul className="card money-bars">
          {d.attendance.map((m) => {
            const month = formatShortMonth(m.period, lang)
            return (
              <li
                key={m.period}
                aria-label={
                  m.percent === null
                    ? t('dashboard_bar_none_desc', month)
                    : t('dashboard_bar_desc', month, m.percent)
                }
              >
                <span aria-hidden="true">{month}</span>
                <span className="money-bar" aria-hidden="true">
                  <span style={{ width: `${m.percent ?? 0}%` }} />
                </span>
                <span aria-hidden="true" className="amount">
                  {m.percent === null ? '–' : `${m.percent}%`}
                </span>
              </li>
            )
          })}
        </ul>
      </Section>

      <Section title={t('dashboard_exams_title')}>
        {d.exams.length === 0 ? (
          <div className="card">
            <div className="title">{t('dashboard_exams_empty_title')}</div>
            <p className="meta">{t('dashboard_exams_empty_body')}</p>
          </div>
        ) : (
          <div className="card">
            {latest ? (
              <div className="money-latest">
                <div className="title">
                  {t('dashboard_latest_title', latest.title, formatShortDate(latest.date, lang))}
                </div>
                <div className="meta">
                  {latest.marks === null ? '–' : formatMark(latest.marks)}
                  {latest.average !== null
                    ? t('dashboard_latest_avg', formatMark(latest.average))
                    : ''}
                  {latest.highest !== null
                    ? t('dashboard_latest_high', formatMark(latest.highest))
                    : ''}
                </div>
              </div>
            ) : null}
            <ul className="money-bars" aria-label={t('dashboard_exam_chart_desc', d.exams.length)}>
              {d.exams.map((e) => (
                <li key={e.examId}>
                  <span>{e.title}</span>
                  <span className="money-bar" aria-hidden="true">
                    <span style={{ width: `${e.percent ?? 0}%` }} />
                  </span>
                  <span className="amount">
                    {e.marks === null ? '–' : formatMark(e.marks)}
                    {t('student_out_of', e.total)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      <Section
        title={t('dashboard_fees_title')}
        aside={
          <Link className="btn btn-text btn-small" to={feesLink}>
            {t('dashboard_fees_history')}
          </Link>
        }
      >
        <MonthStrip months={d.feeMonths} />
      </Section>
    </>
  )
}
