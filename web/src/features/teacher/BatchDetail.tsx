/**
 * T7 · Single batch: the header (name, fee, days, time, subjects) and four
 * tabs. Each tab belongs to an area (students/, classes/, exams/) and
 * loads its own data, so one tab failing never blanks another.
 *
 * The open tab is in the URL (`?tab=exams`), so a screen that finishes —
 * creating an exam, recording a class — can return to the tab it came from.
 */
import { Link, useParams, useSearchParams } from 'react-router'
import { listBatches } from '../../api/endpoints'
import { formatClock } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { ErrorCard, Loading, TopBar } from '../../ui/components'
import { mapBatch, sortedDays } from './mappers'
import { WEEKDAY_KEYS } from './Batches'
import { ClassesTab } from './classes'
import { ExamsTab } from './exams'
import { NoticesTab, StudentsTab } from './students'
import { paths, type BatchTab } from './paths'
import { EditIcon } from '../../ui/icons'

const TABS: readonly BatchTab[] = ['students', 'classes', 'exams', 'notices']

export function BatchDetail() {
  const { batchId = '' } = useParams()
  const { t, lang } = useT()
  const [search, setSearch] = useSearchParams()
  const requested = search.get('tab') as BatchTab | null
  const tab: BatchTab = requested && TABS.includes(requested) ? requested : 'students'
  const { resource, reload } = useResource(
    () => listBatches().then((all) => all.map(mapBatch).find((b) => b.id === batchId) ?? null),
    [batchId],
  )

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

  const batch = resource.data
  const first = batch?.schedule[0]
  const subtitle = batch?.defaultFee
    ? batch.feeDueDay
      ? t('batch_fee_due', batch.defaultFee.format(), batch.feeDueDay)
      : t('batch_fee_monthly', batch.defaultFee.format())
    : undefined
  const tabProps = { batchId, batch, reloadBatch: reload }

  return (
    <>
      <TopBar
        title={batch?.name ?? t('roster_title_fallback')}
        subtitle={subtitle}
        back="/batches"
        actions={
          batch ? (
            <Link
              className="icon-btn"
              to={paths.batchEdit(batchId)}
              aria-label={t('batch_edit_title')}
            >
              <EditIcon size={22} />
            </Link>
          ) : null
        }
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
          <Link className="chip chip-filter" to={paths.batchSchedule(batchId)}>
            {t('roster_open_schedule')}
          </Link>
        </div>
      ) : null}

      <div className="tabs" role="tablist">
        {TABS.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setSearch(k === 'students' ? {} : { tab: k }, { replace: true })}
          >
            {t(`batch_tab_${k}`)}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="batch-tabpanel">
        {tab === 'students' ? <StudentsTab {...tabProps} /> : null}
        {tab === 'classes' ? <ClassesTab {...tabProps} /> : null}
        {tab === 'exams' ? <ExamsTab {...tabProps} /> : null}
        {tab === 'notices' ? <NoticesTab {...tabProps} /> : null}
      </div>
    </>
  )
}
