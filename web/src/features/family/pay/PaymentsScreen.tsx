/**
 * G2 · A child's payments, month by month (Android `PaymentsScreen`).
 *
 * Guardian only: the API has no student twin of
 * `/v1/children/{id}/payments`, so a student opening this path is sent to
 * their fee history, which carries the same payment lines. The headline is
 * the next thing owed as the server ordered it; "Send money" is offered
 * whether or not anything is due, as Android does.
 */
import { Link, Navigate, useParams } from 'react-router'
import { formatMonth, formatShortDate } from '../../../core/format'
import { useOnline, useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { FeeChip, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { CircleIcon } from '../../../ui/icons'
import { familyPaths, type Reader } from '../reader'
import { readChildPayments, readPayables } from './api'
import {
  firstName,
  lineChip,
  mapPayments,
  nextPayable,
  type NextPayable,
  type PaymentLine,
  type PaymentsModel,
} from './mappers'
import './pay.css'

interface Loaded {
  payments: PaymentsModel
  next: NextPayable | null
}

async function load(seat: string, signal?: AbortSignal): Promise<Loaded> {
  const payments = mapPayments(await readChildPayments(seat, signal))
  // The headline is a convenience: the payments still show if payables fail.
  const next = await readPayables('child', seat, signal).then(nextPayable, () => null)
  return { payments, next }
}

export function PaymentsScreen({ reader }: { reader: Reader }) {
  const { seat = '' } = useParams()
  if (reader === 'me') return <Navigate to={familyPaths.fees('me', seat)} replace />
  return <ChildPayments seat={seat} />
}

function ChildPayments({ seat }: { seat: string }) {
  const { t, lang } = useT()
  const online = useOnline()
  const { resource, reload } = useResource((signal) => load(seat, signal), [seat])

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('guardian_open_fees')} back="/children" />
        <Loading rows={4} />
        <div className="action-bar">
          <button type="button" className="btn btn-primary btn-money" disabled>
            {t('payments_waiting')}
          </button>
        </div>
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('guardian_open_fees')} back="/children" />
        {/* Android's own words: don't pay again until this loads. */}
        <div className="card error" role="alert">
          <div className="title">{t('payments_error_title')}</div>
          <p className="meta">{t('payments_error_body')}</p>
          {resource.error.retryable ? (
            <button type="button" className="btn btn-outline" onClick={reload}>
              {t('dues_retry')}
            </button>
          ) : null}
        </div>
      </>
    )
  }

  const { payments, next } = resource.data
  const name = firstName(payments.childName)
  const canPay = online && resource.error === null
  return (
    <>
      <TopBar
        title={t('payments_title', name)}
        subtitle={t('payments_paid_in', payments.year, payments.paidThisYear.format())}
        back="/children"
      />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}

      <div className="side-layout">
        <div className="side-panel">
          <div className="card" style={{ marginTop: resource.error ? 12 : 0 }}>
            {next ? (
              <>
                <div className="label">{t('payments_owed_now')}</div>
                <div className="hero-amount">{next.totalDue.format()}</div>
                <div className="meta">
                  {next.batchName} · {formatMonth(next.period, lang)}
                </div>
              </>
            ) : (
              <div className="title">{t('payments_nothing_due')}</div>
            )}
          </div>
          <div className="action-bar">
            <p className="meta" style={{ textAlign: 'center', margin: '0 0 8px' }}>
              {t('payments_send_hint')}
            </p>
            {canPay ? (
              <Link className="btn btn-primary btn-money" to={familyPaths.pay('child', seat)}>
                {t('payments_send_money')}
              </Link>
            ) : (
              <button type="button" className="btn btn-primary btn-money" disabled>
                {t('pay_needs_connection')}
              </button>
            )}
          </div>
        </div>
        <div className="side-main">
          {payments.months.length === 0 ? (
            <div className="empty">
              <h2>{t('payments_empty_title')}</h2>
              <p>{t('payments_empty_body', name)}</p>
            </div>
          ) : (
            payments.months.map((m) => <Month key={m.period} period={m.period} lines={m.lines} />)
          )}
        </div>
      </div>
    </>
  )
}

function Month({ period, lines }: { period: string; lines: PaymentLine[] }) {
  const { lang } = useT()
  const title = new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'Asia/Dhaka',
  }).format(new Date(`${period.slice(0, 7)}-15T12:00:00Z`))
  return (
    <section className="section" aria-label={title}>
      <div className="section-head">
        <h2>{title}</h2>
      </div>
      <ul className="card flush list">
        {lines.map((line, i) => (
          <Line key={`${line.enrollmentId}-${i}`} line={line} />
        ))}
      </ul>
    </section>
  )
}

function Line({ line }: { line: PaymentLine }) {
  const { t, lang } = useT()
  const channel = line.channel === 'cash' ? t('verify_method_cash') : (line.channel ?? '')
  const detail =
    line.state === 'verifying' && line.sentOn
      ? t('payments_you_sent', formatShortDate(line.sentOn, lang), channel)
      : line.decidedOn
        ? t('payments_approved', formatShortDate(line.decidedOn, lang), channel)
        : line.state === 'waived'
          ? t('student_chip_waived')
          : t('student_due_by', formatShortDate(line.dueDate, lang))
  return (
    <li className="row">
      <div className="grow">
        <div className="title">{line.batchName}</div>
        <div className="meta">{detail}</div>
      </div>
      <div className="end">
        <span className="amount">{line.amount.format()}</span>
        <LineChip line={line} />
      </div>
    </li>
  )
}

function LineChip({ line }: { line: PaymentLine }) {
  const { t } = useT()
  switch (line.state) {
    case 'due':
      return (
        <span className="chip chip-due">
          <CircleIcon size={14} />
          {t('payments_due')}
        </span>
      )
    case 'paid':
      return <FeeChip chip={{ kind: 'paid', label: t('student_chip_paid') }} />
    case 'partly_paid':
      return (
        <FeeChip chip={{ kind: 'partial', left: null, label: t('student_chip_partly_paid') }} />
      )
    default:
      return <FeeChip chip={lineChip(line.state)} />
  }
}
