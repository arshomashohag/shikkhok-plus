/**
 * One batch's month, seat by seat (`BatchMonthScreen.kt`): collected
 * against charged, filters by where each seat stands, and each seat's
 * latest payment line. Previous / next walk the months; next stops at
 * the month Dhaka is in. A seat opens its fee history.
 */
import { useCallback, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { formatMonth } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import {
  CheckCircleIcon,
  ClockIcon,
  CircleIcon,
  HalfCircleIcon,
  WarningIcon,
} from '../../../ui/icons'
import { paths } from '../paths'
import { readBatchMonth } from './api'
import {
  canRecordFor,
  mapBatchMonth,
  visibleSeats,
  type MonthFilter,
  type MonthSeat,
} from './collections'
import { dhakaPeriod, isPeriod, shiftPeriod } from './format'
import { HistoryLineText } from './HistoryLineText'
import { moneyPaths } from './paths'
import { RecordPaymentSheet } from './RecordPaymentSheet'

export function BatchMonthScreen() {
  const { batchId = '', period: rawPeriod = '' } = useParams()
  const period = isPeriod(rawPeriod) ? rawPeriod : undefined
  const { t, lang } = useT()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<MonthFilter>('all')
  const [recording, setRecording] = useState<MonthSeat | null>(null)
  const [snack, setSnack] = useState<string | null>(null)
  const dismissSnack = useCallback(() => setSnack(null), [])
  const { resource, reload } = useResource(
    () =>
      Promise.all([
        readBatchMonth(batchId, period).then(mapBatchMonth),
        listBatches().then((b) => b.find((x) => x.id === batchId)?.name ?? null),
      ]).then(([month, name]) => ({ month, name })),
    [batchId, period],
  )

  const go = (to: string) => navigate(paths.batchMonth(batchId, to), { replace: true })
  const batchName = resource.state === 'loaded' ? (resource.data.name ?? undefined) : undefined

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={5} />
  else if (resource.state === 'failed')
    body = (
      <ErrorCard title={t('screen_title_batch_fees')} error={resource.error} onRetry={reload} />
    )
  else {
    const { month } = resource.data
    const seats = visibleSeats(month.seats, filter)
    const filters: [MonthFilter, string][] = [
      ['all', t('batch_month_filter_all')],
      ['paid', t('batch_month_filter_paid', month.counts.paid)],
      ['checking', t('batch_month_filter_checking', month.counts.checking)],
      ['owed', t('batch_month_filter_owed', month.counts.owed)],
    ]
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <div className="money-month-nav">
          <button
            type="button"
            className="btn btn-text btn-small"
            onClick={() => go(shiftPeriod(month.period, -1))}
          >
            ‹ {t('batch_month_previous')}
          </button>
          <strong>{formatMonth(month.period, lang)}</strong>
          {month.period < dhakaPeriod() ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              onClick={() => go(shiftPeriod(month.period, 1))}
            >
              {t('batch_month_next')} ›
            </button>
          ) : (
            <span />
          )}
        </div>
        <div className="card">
          <div className="hero-amount" style={{ margin: 0 }}>
            {month.collected.format()}
          </div>
          <div className="meta">{t('batch_month_collected_of', month.charged.format())}</div>
        </div>
        <div className="chips" style={{ margin: '12px 0' }}>
          {filters.map(([f, label]) => (
            <button
              key={f}
              type="button"
              className="chip chip-filter"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {label}
            </button>
          ))}
        </div>
        {seats.length === 0 ? (
          <EmptyState title={t('batch_month_no_seats')} />
        ) : (
          <ul className="card flush list">
            {seats.map((s) => (
              <li key={s.enrollmentId}>
                <Link
                  className="row"
                  style={{ alignItems: 'flex-start' }}
                  to={moneyPaths.seatFees(s.enrollmentId, s.displayName, batchName)}
                >
                  <div className="grow">
                    <div className="title">{s.displayName}</div>
                    <SeatLine seat={s} />
                    {s.line ? <HistoryLineText line={s.line} /> : null}
                  </div>
                  <SeatChip seat={s} />
                </Link>
                {canRecordFor(s) ? (
                  <div className="money-record-row">
                    <button
                      type="button"
                      className="btn btn-text btn-small"
                      onClick={() => setRecording(s)}
                    >
                      {t('fees_record_payment')}
                    </button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </>
    )
  }

  return (
    <>
      <TopBar title={t('screen_title_batch_fees')} subtitle={batchName} back />
      {body}
      {recording ? (
        <RecordPaymentSheet
          enrollmentId={recording.enrollmentId}
          name={recording.displayName}
          owed={recording.outstanding}
          onClose={() => setRecording(null)}
          onRecorded={() => {
            setRecording(null)
            setSnack(t('fees_record_done'))
            reload()
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismissSnack} /> : null}
    </>
  )
}

function SeatLine({ seat }: { seat: MonthSeat }) {
  const { t } = useT()
  if (seat.kind === 'checking' && seat.verifying)
    return <div className="meta">{t('batch_month_sending', seat.verifying.format())}</div>
  if (seat.kind === 'overdue' && seat.daysOverdue !== null)
    return (
      <div className="meta danger">
        {t('batch_month_owed_late', seat.outstanding.format(), seat.daysOverdue)}
      </div>
    )
  if (seat.kind === 'partial' || seat.kind === 'due')
    return <div className="meta">{t('batch_month_owed', seat.outstanding.format())}</div>
  return null
}

function SeatChip({ seat }: { seat: MonthSeat }) {
  const { t } = useT()
  switch (seat.kind) {
    case 'paid':
      return (
        <span className="chip chip-paid">
          <CheckCircleIcon size={14} />
          {t('student_chip_paid')}
        </span>
      )
    case 'waived':
      return (
        <span className="chip chip-paid">
          <CheckCircleIcon size={14} />
          {t('student_chip_waived')}
        </span>
      )
    case 'partial':
      return (
        <span className="chip chip-partial">
          <HalfCircleIcon size={14} />
          {t('student_chip_partly_paid')}
        </span>
      )
    case 'due':
      return (
        <span className="chip chip-due">
          <CircleIcon size={14} />
          {t('batch_month_chip_due')}
        </span>
      )
    case 'overdue':
      return (
        <span className="chip chip-overdue">
          <WarningIcon size={14} />
          {t('batch_month_chip_overdue')}
        </span>
      )
    case 'checking':
      return (
        <span className="chip chip-verifying">
          <ClockIcon size={14} />
          {t('student_chip_verifying')}
        </span>
      )
    case 'none':
      return <span className="meta">{t('batch_month_chip_none')}</span>
  }
}
