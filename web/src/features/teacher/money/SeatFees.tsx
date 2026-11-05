/**
 * One student's fee history, as their teacher reads it
 * (`FeeHistoryScreen.kt`, teacher reader): what is outstanding in all,
 * the last six months as a strip, and each month's cycle with its latest
 * payment line. "Progress" opens the seat's dashboard.
 *
 * Every figure is the server's; the strip's states are the server's.
 */
import { Link, useParams, useSearchParams } from 'react-router'
import { formatMonth, formatShortDate, formatShortMonth } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { readSeatFees } from './api'
import { mapFeeHistory, STRIP_GLYPH, STRIP_WORD, type MonthCell } from './fees'
import { HistoryLineText } from './HistoryLineText'
import { moneyPaths } from './paths'

export function SeatFees() {
  const { enrollmentId = '' } = useParams()
  const [search] = useSearchParams()
  const name = search.get('name') ?? undefined
  const batch = search.get('batch') ?? undefined
  const { t, lang } = useT()
  const { resource, reload } = useResource(
    () => readSeatFees(enrollmentId).then(mapFeeHistory),
    [enrollmentId],
  )
  const subtitle = [name, batch].filter(Boolean).join(' · ') || undefined
  const progress = (
    <Link
      className="btn btn-text btn-small"
      to={moneyPaths.seatProgress(enrollmentId, name, batch)}
    >
      {t('dashboard_open_progress')}
    </Link>
  )

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('screen_title_fee_history')} subtitle={subtitle} back />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('screen_title_fee_history')} subtitle={subtitle} back />
        <ErrorCard title={t('screen_title_fee_history')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const history = resource.data
  return (
    <>
      <TopBar title={t('screen_title_fee_history')} subtitle={subtitle} back actions={progress} />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      {history.kind === 'empty' ? (
        <div className="card meta">{t('fees_empty')}</div>
      ) : (
        <>
          <div className="card">
            <div className="hero-amount" style={{ margin: 0 }}>
              {t('fees_total_outstanding', history.totalOutstanding.format())}
            </div>
          </div>
          {history.months.length > 0 ? <MonthStrip months={history.months} /> : null}
          <ul className="card flush list" style={{ marginTop: 12 }}>
            {history.rows.map((row) => {
              const line = history.months.find((m) => m.period === row.period)?.line ?? null
              return (
                <li key={row.period} className="row" style={{ alignItems: 'flex-start' }}>
                  <div className="grow">
                    <div className="title">{formatMonth(row.period, lang)}</div>
                    <div className={row.settled ? 'meta' : 'meta danger'}>
                      {t(`fees_status_${row.status}`)}
                    </div>
                    <div className="meta">
                      {t(
                        'fees_outstanding_of_charged',
                        row.outstanding.format(),
                        row.charged.format(),
                      )}
                    </div>
                    <div className="meta">
                      {t('fees_due_on', formatShortDate(row.dueDate, lang))}
                    </div>
                    {line ? <HistoryLineText line={line} /> : null}
                  </div>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </>
  )
}

/** The last six months, one cell each: glyph, month, and the state in words for a reader. */
export function MonthStrip({ months }: { months: MonthCell[] }) {
  const { t, lang } = useT()
  return (
    <section className="card" style={{ marginTop: 12 }} aria-labelledby="fee-strip-title">
      <div className="label" id="fee-strip-title">
        {t('fee_strip_title')}
      </div>
      <ul className="money-strip">
        {months.map((m) => {
          const word = t(STRIP_WORD[m.kind])
          return (
            <li
              key={m.period}
              className={`money-strip-cell strip-${m.kind}`}
              aria-label={t('fee_strip_cell_desc', formatMonth(m.period, lang), word)}
              title={word}
            >
              <span className="money-strip-glyph" aria-hidden="true">
                {STRIP_GLYPH[m.kind]}
              </span>
              <span aria-hidden="true">{formatShortMonth(m.period, lang)}</span>
            </li>
          )
        })}
      </ul>
      <p className="meta" style={{ margin: 0 }}>
        {t('fee_strip_legend')}
      </p>
    </section>
  )
}
