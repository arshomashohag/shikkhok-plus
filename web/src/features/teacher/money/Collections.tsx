/**
 * Collections (`CollectionsScreen.kt`): what was collected against what
 * was charged, over the last six months, and by batch for the month in
 * view. Pick batches to narrow the report; pick a month to see it by batch.
 *
 * A batch whose month could not load shows its own Try again rather than
 * blanking the report.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../../../api/errors'
import { formatMonth, formatShortMonth } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Section, StaleBanner, TopBar } from '../../../ui/components'
import { ChevronIcon } from '../../../ui/icons'
import { paths } from '../paths'
import { readBatchMonth, readCollections } from './api'
import {
  headlineMonth,
  mapBatchMonth,
  mapCollections,
  type BatchMonth,
  type CollectionsReport,
  type MonthBar,
} from './collections'

type BatchRow =
  | { batchId: string; name: string; ok: true; month: BatchMonth }
  | { batchId: string; name: string; ok: false; error: ApiError }

interface Loaded {
  batches: { id: string; name: string }[]
  report: CollectionsReport
  headline: MonthBar | null
  rows: BatchRow[]
}

async function rowFor(batch: { id: string; name: string }, period: string): Promise<BatchRow> {
  try {
    return {
      batchId: batch.id,
      name: batch.name,
      ok: true,
      month: mapBatchMonth(await readBatchMonth(batch.id, period)),
    }
  } catch (e) {
    const error = e instanceof ApiError ? e : new ApiError(0, 'UNEXPECTED', UNEXPECTED_KEY, true)
    return { batchId: batch.id, name: batch.name, ok: false, error }
  }
}

async function load(selected: string[], chosen: string | null): Promise<Loaded> {
  const [all, report] = await Promise.all([
    listBatches().then((b) => b.map((x) => ({ id: x.id, name: x.name }))),
    readCollections(selected).then(mapCollections),
  ])
  const headline = headlineMonth(report.months, chosen)
  const inView = all.filter((b) => selected.length === 0 || selected.includes(b.id))
  const rows = headline ? await Promise.all(inView.map((b) => rowFor(b, headline.period))) : []
  return { batches: all, report, headline, rows }
}

export function Collections() {
  const { t, lang } = useT()
  const [selected, setSelected] = useState<string[]>([])
  const [chosen, setChosen] = useState<string | null>(null)
  const [retried, setRetried] = useState<Record<string, BatchRow>>({})
  const { resource, reload } = useResource(() => {
    setRetried({})
    return load(selected, chosen)
  }, [selected.join(','), chosen])

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  async function retryRow(row: BatchRow, period: string) {
    const fresh = await rowFor({ id: row.batchId, name: row.name }, period)
    setRetried((r) => ({ ...r, [row.batchId]: fresh }))
  }

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('collections_title')} error={resource.error} onRetry={reload} />
  else {
    const { batches, report, headline, rows } = resource.data
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        {batches.length > 1 ? (
          <div className="chips" style={{ marginBottom: 12 }}>
            <button
              type="button"
              className="chip chip-filter"
              aria-pressed={selected.length === 0}
              onClick={() => setSelected([])}
            >
              {t('dues_filter_all_batches')}
            </button>
            {batches.map((b) => (
              <button
                key={b.id}
                type="button"
                className="chip chip-filter"
                aria-pressed={selected.includes(b.id)}
                onClick={() => toggle(b.id)}
              >
                {b.name}
              </button>
            ))}
          </div>
        ) : null}
        {report.months.length === 0 ? (
          <div className="card meta">{t('collections_empty')}</div>
        ) : (
          <>
            <Tiles report={report} headline={headline} />
            <Chart months={report.months} headline={headline} onPick={setChosen} />
            {headline ? (
              <Section title={t('collections_by_batch', formatMonth(headline.period, lang))}>
                <ul className="card flush list">
                  {rows.map((r0) => {
                    const r = retried[r0.batchId] ?? r0
                    return r.ok ? (
                      <li key={r.batchId}>
                        <Link className="row" to={paths.batchMonth(r.batchId, r.month.period)}>
                          <div className="grow">
                            <div className="title">{r.name}</div>
                            <div className="meta">
                              {t(
                                'collections_batch_counts',
                                r.month.counts.paid,
                                r.month.counts.checking,
                                r.month.counts.owed,
                              )}
                            </div>
                          </div>
                          <span className="amount">
                            {t(
                              'collections_batch_amounts',
                              r.month.collected.format(),
                              r.month.charged.format(),
                            )}
                          </span>
                          <ChevronIcon />
                        </Link>
                      </li>
                    ) : (
                      <li key={r.batchId} className="row">
                        <div className="grow">
                          <div className="title">{r.name}</div>
                          <div className="meta danger">
                            {r.error.offline
                              ? t('error_network_unreachable')
                              : t('error_unexpected')}
                          </div>
                        </div>
                        {r.error.retryable ? (
                          <button
                            type="button"
                            className="btn btn-outline btn-small"
                            onClick={() => void retryRow(r, headline.period)}
                          >
                            {t('dues_retry')}
                          </button>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              </Section>
            ) : null}
          </>
        )}
      </>
    )
  }

  return (
    <>
      <TopBar title={t('collections_title')} subtitle={t('more_collections_sub')} back="/more" />
      {body}
    </>
  )
}

function Tiles({ report, headline }: { report: CollectionsReport; headline: MonthBar | null }) {
  const { t, lang } = useT()
  return (
    <div className="money-tiles money-tiles-2">
      {headline ? (
        <div className="card">
          <div className="label">
            {t('collections_collected_in', formatMonth(headline.period, lang))}
          </div>
          <div className="hero-amount">{headline.collected.format()}</div>
          <div className="meta">{t('collections_of_charged', headline.charged.format())}</div>
        </div>
      ) : null}
      <div className="card">
        <div className="label">{t('collections_still_owed')}</div>
        <div className="hero-amount">{report.outstanding.format()}</div>
        <div className="meta">{t('collections_students_owing', report.owingStudents)}</div>
      </div>
    </div>
  )
}

function Chart({
  months,
  headline,
  onPick,
}: {
  months: MonthBar[]
  headline: MonthBar | null
  onPick: (period: string) => void
}) {
  const { t, lang } = useT()
  const running = months.find((m) => m.inProgress)
  return (
    <section className="card" style={{ marginTop: 12 }} aria-labelledby="collections-chart">
      <div className="label" id="collections-chart">
        {t('collections_last_months')}
      </div>
      <div className="money-chart" role="group">
        {months.map((m) => {
          const name = formatMonth(m.period, lang)
          return (
            <button
              key={m.period}
              type="button"
              className="money-chart-col"
              aria-pressed={headline?.period === m.period}
              aria-label={`${m.inProgress ? t('collections_in_progress_desc', name) : name}: ${t(
                'collections_batch_amounts',
                m.collected.format(),
                m.charged.format(),
              )}`}
              onClick={() => onPick(m.period)}
            >
              <span className="money-chart-bars" aria-hidden="true">
                <span className="charged" style={{ height: `${m.chargedBar}%` }} />
                <span className="collected" style={{ height: `${m.collectedBar}%` }} />
              </span>
              <span aria-hidden="true">
                {formatShortMonth(m.period, lang)}
                {m.inProgress ? '*' : ''}
              </span>
            </button>
          )
        })}
      </div>
      <ul className="legend" style={{ display: 'flex', gap: 16 }}>
        <li>
          <span className="swatch" style={{ background: 'var(--primary)' }} />
          {t('collections_legend_collected')}
        </li>
        <li>
          <span className="swatch" style={{ background: 'var(--outline-variant)' }} />
          {t('collections_legend_charged')}
        </li>
      </ul>
      {running ? (
        <p className="meta" style={{ margin: '8px 0 0' }}>
          * {t('collections_in_progress_note', formatMonth(running.period, lang))}
        </p>
      ) : null}
    </section>
  )
}
