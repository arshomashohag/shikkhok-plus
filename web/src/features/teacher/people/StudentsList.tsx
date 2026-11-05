/**
 * The Students tab: every student of this teacher, once, with the
 * batches they sit in [0018]. As `StudentsScreen.kt`.
 *
 * The filter chips and the search go to the server, which answers with
 * the matching list; the client never filters a domain list itself.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { PlusIcon } from '../../../ui/icons'
import { paths } from '../paths'
import { listStudents, type StudentFilter } from './api'
import { mapStudent } from './mappers'

export function StudentsList() {
  const { t } = useT()
  const [filter, setFilter] = useState<StudentFilter>({ kind: 'all' })
  const [query, setQuery] = useState('')
  const filterKey = filter.kind === 'in-batch' ? filter.batchId : filter.kind
  const { resource, reload } = useResource(
    () => listStudents(filter, query).then((rows) => rows.map(mapStudent)),
    [filterKey, query],
  )
  const batches = useResource(() => listBatches(), [])
  const batchList = batches.resource.state === 'loaded' ? batches.resource.data : []

  const chip = (label: string, next: StudentFilter, pressed: boolean, key: string) => (
    <button
      key={key}
      type="button"
      className="chip chip-filter"
      aria-pressed={pressed}
      onClick={() => setFilter(next)}
    >
      {label}
    </button>
  )

  let body: React.ReactNode
  if (resource.state === 'loading') {
    body = <Loading rows={5} />
  } else if (resource.state === 'failed') {
    body = <ErrorCard title={t('students_error_title')} error={resource.error} onRetry={reload} />
  } else if (resource.data.length === 0) {
    const narrowed = filter.kind !== 'all' || query.trim() !== ''
    body = narrowed ? (
      <EmptyState title={t('students_empty_filtered')} />
    ) : (
      <EmptyState title={t('students_empty_title')} body={t('students_empty_body')} />
    )
  } else {
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="list card" style={{ padding: 0 }}>
          {resource.data.map((s) => (
            <li key={s.id}>
              <Link to={paths.studentDetail(s.id)} className="row">
                <span className="grow">
                  <span className="title" style={{ display: 'block' }}>
                    {s.name}
                  </span>
                  <span className="meta">
                    {s.seats.length === 0
                      ? t('students_not_in_batch')
                      : s.seats.map((seat) => seat.batchName).join(' · ')}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </>
    )
  }

  return (
    <>
      <TopBar title={t('students_title')} />
      <div className="field" style={{ marginTop: 8 }}>
        <input
          type="search"
          aria-label={t('students_search')}
          placeholder={t('students_search')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="chips" style={{ margin: '8px 0 12px' }} role="group">
        {chip(t('students_filter_all'), { kind: 'all' }, filter.kind === 'all', 'all')}
        {batchList.map((b) =>
          chip(
            b.name,
            { kind: 'in-batch', batchId: b.id },
            filter.kind === 'in-batch' && filter.batchId === b.id,
            b.id,
          ),
        )}
        {chip(
          t('students_filter_unassigned'),
          { kind: 'unassigned' },
          filter.kind === 'unassigned',
          'unassigned',
        )}
      </div>
      {body}
      <Link to={paths.studentNew()} className="btn btn-primary fab">
        <PlusIcon />
        {t('students_add')}
      </Link>
    </>
  )
}
