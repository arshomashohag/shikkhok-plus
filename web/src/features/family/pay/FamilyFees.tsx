/**
 * Fee history for the family reader: a student's own seat, or a child's.
 *
 * The same screen as the teacher's (Android uses one `FeeHistoryScreen`
 * for all three readers), so it reuses the teacher money area's mapper,
 * strip and payment-line text; only the endpoint differs. Every figure is
 * the server's; the client computes no balance [TC-9].
 */
import { Link, useParams } from 'react-router'
import { formatMonth, formatShortDate } from '../../../core/format'
import { useOnline, useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { mapFeeHistory } from '../../teacher/money/fees'
import { HistoryLineText } from '../../teacher/money/HistoryLineText'
import { MonthStrip } from '../../teacher/money/SeatFees'
import '../../teacher/money/money.css'
import { familyPaths, type Reader } from '../reader'
import { readFamilyFees } from './api'
import './pay.css'

export function FamilyFees({ reader }: { reader: Reader }) {
  const { seat = '' } = useParams()
  const { t, lang } = useT()
  const online = useOnline()
  const { resource, reload } = useResource(
    () => readFamilyFees(reader, seat).then(mapFeeHistory),
    [reader, seat],
  )
  const progress = (
    <Link className="btn btn-text btn-small" to={familyPaths.dashboard(reader, seat)}>
      {t('dashboard_open_progress')}
    </Link>
  )

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('screen_title_fee_history')} back />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('screen_title_fee_history')} back />
        <ErrorCard title={t('screen_title_fee_history')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const history = resource.data
  const canPay = online && resource.error === null
  return (
    <>
      <TopBar title={t('screen_title_fee_history')} back actions={progress} />
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
      <div className="action-bar">
        {canPay ? (
          <Link className="btn btn-primary btn-money" to={familyPaths.pay(reader, seat)}>
            {t('pay_open')}
          </Link>
        ) : (
          <button type="button" className="btn btn-primary btn-money" disabled>
            {t('pay_needs_connection')}
          </button>
        )}
      </div>
    </>
  )
}
