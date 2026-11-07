/**
 * T5 · Cross-batch dues. Who owes, sorted by how late, across every batch.
 *
 * Membership and grouping are the server's: a row is here because its
 * outstanding balance is not zero, which the server decided, and its
 * bucket is the one the server assigned [PU-7.2]. The filters only hide
 * rows the server already sent.
 *
 * **Who a reminder reaches is the server's too**: "Remind N late students"
 * sends to the seats the server marked `remindable` — whatever filter is
 * on screen — and its count is the server's `summary.remindable`. A
 * reminder needs a connection and a fresh read, so the button is held back
 * offline or while the figures on screen could not be refreshed.
 */
import { useCallback, useMemo, useState } from 'react'
import { readDues } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { ago, formatShortMonth } from '../../core/format'
import { useOnline, useResource } from '../../core/useResource'
import { useWide } from '../../core/useWide'
import { useT } from '../../i18n/i18n'
import {
  ErrorCard,
  FeeChip,
  Loading,
  Section,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../ui/components'
import { BellIcon } from '../../ui/icons'
import { BUCKET_ORDER, duesChip, mapDues, type DuesBucket, type DuesRow } from './mappers'
import { sendReminders } from './students/api'

const BUCKET_LABEL: Record<DuesBucket, string> = {
  over_30: 'dues_group_over_30',
  late: 'dues_group_late',
  not_late: 'dues_group_not_late',
}

const SWATCH: Record<DuesBucket, string> = {
  over_30: 'var(--overdue-fill)',
  late: 'var(--late-swatch)',
  not_late: 'var(--surface)',
}

export function Dues() {
  const { t, message } = useT()
  const { resource, reload } = useResource((signal) => readDues(signal).then(mapDues), [])
  const [lateOnly, setLateOnly] = useState(false)
  const [notReminded, setNotReminded] = useState(false)
  const online = useOnline()
  const wide = useWide()
  const [confirming, setConfirming] = useState(false)
  const [sending, setSending] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  const dismiss = useCallback(() => setSnack(null), [])

  const grouped = useMemo(() => {
    if (resource.state !== 'loaded') return []
    const rows = resource.data.rows.filter(
      (r) => (!lateOnly || r.bucket !== 'not_late') && (!notReminded || r.lastRemindedAt === null),
    )
    return BUCKET_ORDER.map((bucket) => ({
      bucket,
      rows: rows.filter((r) => r.bucket === bucket),
      total: resource.data.groups.find((g) => g.bucket === bucket)?.total ?? null,
    })).filter((g) => g.rows.length > 0)
  }, [resource, lateOnly, notReminded])

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('dues_title')} />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('dues_title')} />
        <ErrorCard title={t('dues_title')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const model = resource.data

  async function remind() {
    // The seats the server marked, not the ones a filter leaves on screen.
    const targets = model.rows.filter((r) => r.remindable).map((r) => r.enrollmentId)
    if (targets.length === 0) return
    setSending(true)
    try {
      const result = await sendReminders(targets)
      setConfirming(false)
      setSnack(t('dues_remind_sent', result.sent))
      reload()
    } catch (e) {
      setConfirming(false)
      setSnack(
        e instanceof ApiError && e.offline
          ? t('web_dues_remind_offline')
          : message(e instanceof ApiError ? e.messageKey : 'error.unexpected'),
      )
    } finally {
      setSending(false)
    }
  }

  if (model.count === 0) {
    return (
      <>
        <TopBar title={t('dues_title')} />
        <div className="card">
          <div className="label">{t('dues_owed_to_you')}</div>
          <div className="hero-amount">{model.total.format()}</div>
          <p className="meta">{t('dues_nobody_owes')}</p>
        </div>
      </>
    )
  }

  return (
    <>
      <TopBar
        title={t('dues_title')}
        subtitle={t(
          'dues_subtitle_updated',
          t('dues_students', model.count),
          ago(resource.loadedAt.toISOString(), new Date(), t),
        )}
      />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}

      <div
        className={wide ? 'card dues-summary' : 'card'}
        style={{ marginTop: resource.error ? 12 : 0 }}
      >
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="label">{t('dues_owed_to_you')}</span>
            <span className="meta">{t('dues_students', model.count)}</span>
          </div>
          <div className="hero-amount">{model.total.format()}</div>
        </div>
        <div>
          <div
            className="progress-bar"
            role="img"
            aria-label={t(
              'dues_bar_description',
              ...BUCKET_ORDER.map((b) => model.groups.find((g) => g.bucket === b)?.count ?? 0),
            )}
          >
            {BUCKET_ORDER.map((b) => {
              const g = model.groups.find((x) => x.bucket === b)
              // `share` is the server's percentage of the total; drawn, not computed.
              return g ? (
                <span key={b} style={{ width: `${g.share}%`, background: SWATCH[b] }} />
              ) : null
            })}
          </div>
          <ul className="legend">
            {BUCKET_ORDER.map((b) => {
              const g = model.groups.find((x) => x.bucket === b)
              if (!g) return null
              return (
                <li key={b}>
                  <span className="swatch" style={{ background: SWATCH[b] }} />
                  <span className="grow">{t('dues_legend', t(BUCKET_LABEL[b]), g.count)}</span>
                  <span className="amount">{g.total.format()}</span>
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      {wide ? (
        <section className="card flush" style={{ marginTop: 24 }}>
          <div className="toolbar">
            <div className="chips">
              <button
                type="button"
                className="chip chip-filter"
                aria-pressed={lateOnly}
                onClick={() => setLateOnly((v) => !v)}
              >
                {t('dues_filter_late')}
              </button>
              <button
                type="button"
                className="chip chip-filter"
                aria-pressed={notReminded}
                onClick={() => setNotReminded((v) => !v)}
              >
                {t('dues_filter_not_reminded')}
              </button>
            </div>
          </div>
          {grouped.length === 0 ? (
            <p className="meta" style={{ padding: '16px 20px', margin: 0 }}>
              {t('dues_filter_empty')}
            </p>
          ) : (
            <DuesTable groups={grouped} />
          )}
          {model.remindable > 0 ? (
            <div className="dues-foot">
              <span className="meta">
                {online ? t('dues_remind_note') : t('web_dues_remind_offline')}
              </span>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!online || sending || resource.error !== null || resource.refreshing}
                onClick={() => setConfirming(true)}
              >
                <BellIcon />
                {t('dues_remind_button', model.remindable)}
              </button>
            </div>
          ) : null}
        </section>
      ) : (
        <>
          <div className="chips" style={{ marginTop: 16 }}>
            <button
              type="button"
              className="chip chip-filter"
              aria-pressed={lateOnly}
              onClick={() => setLateOnly((v) => !v)}
            >
              {t('dues_filter_late')}
            </button>
            <button
              type="button"
              className="chip chip-filter"
              aria-pressed={notReminded}
              onClick={() => setNotReminded((v) => !v)}
            >
              {t('dues_filter_not_reminded')}
            </button>
          </div>

          {grouped.length === 0 ? (
            <p className="meta" style={{ marginTop: 16 }}>
              {t('dues_filter_empty')}
            </p>
          ) : (
            grouped.map((g) => (
              <Section
                key={g.bucket}
                title={t(BUCKET_LABEL[g.bucket])}
                aside={g.total ? <span className="amount">{g.total.format()}</span> : null}
              >
                <ul className="card flush list">
                  {g.rows.map((r) => (
                    <DuesRowItem key={r.enrollmentId} row={r} />
                  ))}
                </ul>
              </Section>
            ))
          )}

          {model.remindable > 0 ? (
            <div className="action-bar">
              <button
                type="button"
                className="btn btn-primary btn-money"
                disabled={!online || sending || resource.error !== null || resource.refreshing}
                onClick={() => setConfirming(true)}
              >
                <BellIcon />
                {t('dues_remind_button', model.remindable)}
              </button>
              <p className="meta" style={{ textAlign: 'center', margin: '8px 0 0' }}>
                {online ? t('dues_remind_note') : t('web_dues_remind_offline')}
              </p>
            </div>
          ) : null}
        </>
      )}
      {confirming ? (
        <Sheet
          title={t('dues_remind_confirm_title', model.remindable)}
          onClose={() => setConfirming(false)}
        >
          <p className="meta">{t('dues_remind_confirm_body')}</p>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-primary btn-money"
              disabled={sending || !online}
              onClick={() => void remind()}
            >
              {t('dues_remind_send')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-money"
              onClick={() => setConfirming(false)}
            >
              {t('dues_remind_cancel')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </>
  )
}

function DuesRowItem({ row }: { row: DuesRow }) {
  const { t, lang } = useT()
  const months =
    row.oldestPeriod && row.latestPeriod && row.oldestPeriod !== row.latestPeriod
      ? `${formatShortMonth(row.oldestPeriod, lang)}–${formatShortMonth(row.latestPeriod, lang)}`
      : row.latestPeriod
        ? formatShortMonth(row.latestPeriod, lang)
        : null
  return (
    <li className="row">
      <div className="grow">
        <div className="title">{row.displayName}</div>
        <div className="meta">{[row.batchName, months].filter(Boolean).join(' · ')}</div>
        {row.lastRemindedAt ? (
          <div className="meta">{t('dues_reminded', ago(row.lastRemindedAt, new Date(), t))}</div>
        ) : row.bucket !== 'not_late' ? (
          <div className="meta danger">{t('dues_never_reminded')}</div>
        ) : null}
      </div>
      <div className="end">
        <span className="amount">{row.outstanding.format()}</span>
        <FeeChip chip={duesChip(row)} />
      </div>
    </li>
  )
}

function monthsOf(row: DuesRow, lang: 'bn' | 'en'): string | null {
  return row.oldestPeriod && row.latestPeriod && row.oldestPeriod !== row.latestPeriod
    ? `${formatShortMonth(row.oldestPeriod, lang)}–${formatShortMonth(row.latestPeriod, lang)}`
    : row.latestPeriod
      ? formatShortMonth(row.latestPeriod, lang)
      : null
}

/**
 * The wide-window form: one table, the server's buckets as group rows,
 * each with the server's total for it.
 */
function DuesTable({
  groups,
}: {
  groups: { bucket: DuesBucket; rows: DuesRow[]; total: import('../../core/money').Money | null }[]
}) {
  const { t, lang } = useT()
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">{t('web_dues_col_student')}</th>
            <th scope="col">{t('web_dues_col_batch')}</th>
            <th scope="col">{t('web_dues_col_months')}</th>
            <th scope="col">{t('web_dues_col_reminded')}</th>
            <th scope="col" className="num">
              {t('web_dues_col_owed')}
            </th>
            <th scope="col">{t('web_dues_col_late')}</th>
          </tr>
        </thead>
        {groups.map((g) => (
          <tbody key={g.bucket}>
            <tr className="group">
              <td colSpan={4}>{t(BUCKET_LABEL[g.bucket])}</td>
              <td className="num">{g.total ? g.total.format() : ''}</td>
              <td />
            </tr>
            {g.rows.map((r) => (
              <tr key={r.enrollmentId}>
                <td className="title">{r.displayName}</td>
                <td>{r.batchName}</td>
                <td>{monthsOf(r, lang) ?? '—'}</td>
                <td>
                  {r.lastRemindedAt ? (
                    <span className="meta">{ago(r.lastRemindedAt, new Date(), t)}</span>
                  ) : r.bucket !== 'not_late' ? (
                    <span className="meta danger">{t('web_dues_never')}</span>
                  ) : (
                    <span className="meta">—</span>
                  )}
                </td>
                <td className="num amount">{r.outstanding.format()}</td>
                <td>
                  <FeeChip chip={duesChip(r)} />
                </td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}
