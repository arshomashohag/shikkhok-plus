/**
 * T7 · Single batch. The Students tab is built; the other three tabs say
 * plainly that they are in the Android app for now, rather than showing
 * a half-built screen.
 *
 * **Fee chips load separately from names**, as the design's Loading/Error
 * board draws: a roster that loaded with fees that did not still shows
 * the names, and hides fee status rather than showing it out of date.
 */
import { useState } from 'react'
import { useParams } from 'react-router'
import { listBatches, readBatchFees, readRoster } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { formatClock, formatPhone } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, FeeChip, Loading, TopBar } from '../../ui/components'
import { mapBatch, mapRoster, sortedDays, type BatchSummary, type RosterSeat } from './mappers'
import { WEEKDAY_KEYS } from './Batches'
import { NotOnWebYet } from '../common/NotOnWebYet'

type Tab = 'students' | 'classes' | 'exams' | 'notices'

interface Loaded {
  batch: BatchSummary | null
  seats: RosterSeat[]
  feesError: ApiError | null
}

async function load(batchId: string): Promise<Loaded> {
  const [batches, roster, fees] = await Promise.all([
    listBatches(),
    readRoster(batchId),
    readBatchFees(batchId).then(
      (f) => ({ ok: true as const, f }),
      (e: unknown) => ({ ok: false as const, e }),
    ),
  ])
  const found = batches.find((b) => b.id === batchId)
  const feesError = fees.ok ? null : fees.e instanceof ApiError ? fees.e : null
  if (!fees.ok && !(fees.e instanceof ApiError)) throw fees.e
  return {
    batch: found ? mapBatch(found) : null,
    seats: mapRoster(roster, fees.ok ? fees.f : null),
    feesError,
  }
}

export function BatchDetail() {
  const { batchId = '' } = useParams()
  const { t, lang } = useT()
  const [tab, setTab] = useState<Tab>('students')
  const { resource, reload } = useResource(() => load(batchId), [batchId])

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('roster_title_fallback')} back="/batches" />
        <Loading rows={5} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('roster_title_fallback')} back="/batches" />
        <ErrorCard title={t('batch_not_found')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const { batch, seats, feesError } = resource.data
  const first = batch?.schedule[0]
  const subtitle = batch?.defaultFee
    ? batch.feeDueDay
      ? t('batch_fee_due', batch.defaultFee.format(), batch.feeDueDay)
      : t('batch_fee_monthly', batch.defaultFee.format())
    : undefined

  return (
    <>
      <TopBar
        title={batch?.name ?? t('roster_title_fallback')}
        subtitle={subtitle}
        back="/batches"
      />
      {batch ? (
        <div className="chips" style={{ marginBottom: 12 }}>
          {sortedDays(batch.schedule).length > 0 ? (
            <span className="chip chip-neutral">
              {sortedDays(batch.schedule)
                .map((d) => t(WEEKDAY_KEYS[d] ?? 'weekday_mon'))
                .join(' · ')}
            </span>
          ) : null}
          {first ? (
            <span className="chip chip-neutral">
              {formatClock(first.startTime, lang)}–{formatClock(first.endTime, lang)}
            </span>
          ) : null}
          {batch.subjects.map((s) => (
            <span key={s} className="chip chip-neutral">
              {s}
            </span>
          ))}
        </div>
      ) : null}

      <div className="tabs" role="tablist">
        {(['students', 'classes', 'exams', 'notices'] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
          >
            {t(`batch_tab_${k}`)}
          </button>
        ))}
      </div>

      {tab !== 'students' ? (
        <NotOnWebYet />
      ) : seats.length === 0 ? (
        <EmptyState title={t('roster_empty')} />
      ) : (
        <>
          {feesError ? (
            <div className="card error" role="status" style={{ marginBottom: 12 }}>
              <div className="title">{t('batch_fees_failed')}</div>
              <p className="meta">{t('batch_fees_failed_body')}</p>
              <button type="button" className="btn btn-outline" onClick={reload}>
                {t('auth_retry')}
              </button>
            </div>
          ) : null}
          <ul className="card flush list">
            {seats.map((s) => (
              <li key={s.enrollmentId} className="row">
                <div className="grow">
                  <div className="title">{s.displayName}</div>
                  <div className="meta">
                    {s.guardianPhone
                      ? `${t('roster_link_guardian')} ${formatPhone(s.guardianPhone)}`
                      : t('roster_link_absent')}
                    {s.status === 'inactive' ? ` · ${t('roster_status_inactive')}` : ''}
                  </div>
                </div>
                {s.chip && !feesError ? <FeeChip chip={s.chip} /> : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
