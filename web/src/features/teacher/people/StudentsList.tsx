/**
 * The Students tab: every student of this teacher, once, with the
 * batches they sit in [0018]. As `StudentsScreen.kt`.
 *
 * The filter chips and the search go to the server, which answers with
 * the matching list; the client never filters a domain list itself.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { useResource } from '../../../core/useResource'
import { useWide } from '../../../core/useWide'
import { useT } from '../../../i18n/i18n'
import { formatPhone, initial } from '../../../core/format'
import { Avatar, EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { PlusIcon } from '../../../ui/icons'
import { paths } from '../paths'
import { listStudents, type StudentFilter } from './api'
import { linkKey, mapStudent, type LinkState, type Student } from './mappers'

/** A phone number with its invitation state under it, or "No phone". */
function PhoneCell({ phone, state }: { phone: string | null; state: LinkState }) {
  const { t } = useT()
  if (!phone) return <span className="meta">{t('web_students_no_phone')}</span>
  return (
    <>
      <div>{formatPhone(phone)}</div>
      <div className="meta">{t(linkKey(state))}</div>
    </>
  )
}

/**
 * The wide-window form of the list: one row per student with the columns
 * a phone has no room for. Every value is the server's, shown as sent.
 */
function StudentsTable({ students }: { students: Student[] }) {
  const { t } = useT()
  const navigate = useNavigate()
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">{t('web_students_col_student')}</th>
            <th scope="col">{t('web_students_col_phone')}</th>
            <th scope="col">{t('web_students_col_guardian')}</th>
            <th scope="col">{t('web_students_col_batches')}</th>
            <th scope="col" className="num">
              {t('web_students_col_owed')}
            </th>
          </tr>
        </thead>
        <tbody>
          {students.map((s) => (
            <tr
              key={s.id}
              className="clickable"
              onClick={() => navigate(paths.studentDetail(s.id))}
            >
              <td>
                <div className="cell-person">
                  <Avatar letter={initial(s.name)} />
                  <Link to={paths.studentDetail(s.id)} onClick={(e) => e.stopPropagation()}>
                    {s.name}
                  </Link>
                </div>
              </td>
              <td>
                <PhoneCell phone={s.studentPhone} state={s.studentState} />
              </td>
              <td>
                <PhoneCell phone={s.guardianPhone} state={s.guardianState} />
              </td>
              <td>
                {s.seats.length === 0 ? (
                  <span className="meta">{t('students_not_in_batch')}</span>
                ) : (
                  <span className="chips" style={{ gap: 6 }}>
                    {s.seats.map((seat) => (
                      <span key={seat.enrollmentId} className="chip chip-neutral">
                        {seat.batchName}
                      </span>
                    ))}
                  </span>
                )}
              </td>
              <td className="num amount">{s.totalOutstanding.format()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StudentsList() {
  const { t } = useT()
  const wide = useWide()
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
        {wide ? (
          <div className="card flush">
            <StudentsTable students={resource.data} />
          </div>
        ) : (
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
        )}
      </>
    )
  }

  const count = resource.state === 'loaded' ? resource.data.length : null
  return (
    <>
      <TopBar
        title={t('students_title')}
        subtitle={count !== null ? t('web_students_count', count) : undefined}
        actions={
          wide ? (
            <Link to={paths.studentNew()} className="btn btn-primary">
              <PlusIcon />
              {t('students_add')}
            </Link>
          ) : null
        }
      />
      <div className="toolbar" style={{ margin: '0 0 16px' }}>
        <div className="chips" role="group">
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
        <input
          type="search"
          className="search"
          aria-label={t('students_search')}
          placeholder={t('students_search')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {body}
      {wide ? null : (
        <Link to={paths.studentNew()} className="btn btn-primary fab">
          <PlusIcon />
          {t('students_add')}
        </Link>
      )}
    </>
  )
}
