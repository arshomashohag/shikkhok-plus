/**
 * S1 · My batches. The next class, each batch with its last test and this
 * month's fee chip. Paying a fee is in the Android app for this slice; the
 * button is not shown rather than shown disabled.
 */
import { Link } from 'react-router'
import { listMyBatches } from '../../api/endpoints'
import { familyPaths } from '../family/reader'
import { formatMark, formatMonth, formatPhone, howSoon, whenLabel } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useWide } from '../../core/useWide'
import { useT } from '../../i18n/i18n'
import { useReadySession } from '../../session/session'
import { ErrorCard, FeeChip, Loading, StaleBanner, TopBar } from '../../ui/components'
import { mapStudentBatch } from './mappers'

export function MyBatches() {
  const { t, lang } = useT()
  const wide = useWide()
  const { session } = useReadySession()
  const { resource, reload } = useResource(
    (signal) => listMyBatches(signal).then((r) => r.map(mapStudentBatch)),
    [],
  )
  const phone = session.me.phone ? formatPhone(session.me.phone) : null
  const subtitle = [session.me.self_name, phone].filter(Boolean).join(' · ')

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('my_batches_title')} subtitle={subtitle} />
        <Loading rows={3} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('my_batches_title')} subtitle={subtitle} />
        <ErrorCard title={t('my_batches_title')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const batches = resource.data
  if (batches.length === 0) {
    return (
      <>
        <TopBar title={t('my_batches_title')} subtitle={phone ?? undefined} />
        <div className="card">
          <h2 style={{ marginTop: 0, fontSize: '1.125rem' }}>{t('my_batches_empty_title')}</h2>
          <p className="meta">
            {phone ? t('my_batches_empty_lead') : t('my_batches_empty_body_no_phone')}
          </p>
          {phone ? <div className="hero-amount">{phone}</div> : null}
        </div>
      </>
    )
  }

  const next = batches.find((b) => b.isNext && b.nextSession) ?? null
  return (
    <>
      <TopBar
        title={t('my_batches_title')}
        subtitle={subtitle}
        actions={
          wide ? (
            <Link
              className="btn btn-primary"
              to={familyPaths.pay('me', (next ?? batches[0])?.enrollmentId ?? '')}
            >
              {t('pay_open')}
            </Link>
          ) : null
        }
      />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      {next?.nextSession ? (
        <Link
          className="hero"
          to={familyPaths.batch('me', next.enrollmentId)}
          style={{ marginTop: resource.error ? 12 : 0 }}
        >
          <div className="meta">{howSoon(next.nextSession.startsInMinutes, t)}</div>
          <div className="hero-amount">{whenLabel(next.nextSession, lang, t)}</div>
          <div className="meta">
            {[next.batchName, next.teacherName].filter(Boolean).join(' · ')}
          </div>
        </Link>
      ) : null}
      <div className="card-grid" style={{ marginTop: wide ? 24 : 12 }}>
        {batches.map((b) => (
          <Link
            key={b.enrollmentId}
            className="card card-link tile"
            to={familyPaths.batch('me', b.enrollmentId)}
          >
            <div className="title">{b.batchName}</div>
            {b.nextSession?.moved ? (
              <div className="meta accent">
                {t('student_today_moved', whenLabel(b.nextSession, lang, t))}
              </div>
            ) : (
              <div className="meta">
                {[
                  b.teacherName,
                  b.nextSession ? whenLabel(b.nextSession, lang, t) : t('student_no_next_class'),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            )}
            <hr
              style={{ border: 0, borderTop: '1px solid var(--outline-variant)', margin: '12px 0' }}
            />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <div className="meta">{t('student_last_test')}</div>
                {b.lastResult ? (
                  <div>
                    <strong>{formatMark(b.lastResult.marks)}</strong>
                    {t('student_out_of', b.lastResult.totalMarks)}{' '}
                    {b.lastResult.rank !== null ? t('student_rank', b.lastResult.rank) : null}
                  </div>
                ) : (
                  <div>{t('student_none_yet')}</div>
                )}
              </div>
              <div>
                <div className="meta">
                  {b.fee ? t('student_fee_month', formatMonth(b.fee.period, lang)) : null}
                </div>
                {b.fee ? <FeeChip chip={b.fee.chip} /> : null}
              </div>
            </div>
          </Link>
        ))}
      </div>
      {/* S1: one way to pay, at the bottom. It opens on the next class's
          batch (Android opens the first); every batch is selectable there. */}
      {wide ? null : (
        <div className="action-bar">
          <Link
            className="btn btn-primary btn-money"
            to={familyPaths.pay('me', (next ?? batches[0])?.enrollmentId ?? '')}
          >
            {t('pay_open')}
          </Link>
        </div>
      )}
    </>
  )
}
