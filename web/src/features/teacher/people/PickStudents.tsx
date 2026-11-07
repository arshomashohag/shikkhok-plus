/**
 * A roster's "add students": the teacher's students NOT already in this
 * batch, chosen with checkboxes, plus "New student" for anyone not on
 * the list yet [0018]. As `PickStudentsScreen.kt`.
 */
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useDebounced, useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, TopBar } from '../../../ui/components'
import { paths } from '../paths'
import { addStudentsToBatch, listStudents } from './api'
import { mapStudent } from './mappers'

export function PickStudents() {
  const { batchId = '' } = useParams()
  const { t, message } = useT()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // One request per pause in typing; the batch name is read once, not
  // again with every search.
  const searched = useDebounced(query)
  const { resource, reload } = useResource(
    (signal) =>
      listStudents({ kind: 'not-in-batch', batchId }, searched, signal).then((students) =>
        students.map(mapStudent),
      ),
    [batchId, searched],
    { keepPreviousOnKeyChange: true },
  )
  const batch = useResource(
    (signal) => listBatches(signal).then((all) => all.find((b) => b.id === batchId)?.name ?? ''),
    [batchId],
  )

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  async function add() {
    if (picked.length === 0) return
    setBusy(true)
    setError(null)
    try {
      await addStudentsToBatch(batchId, picked)
      navigate(paths.batch(batchId, 'students'), { replace: true })
    } catch (e) {
      setError(message(e instanceof ApiError ? e.messageKey : 'error.unexpected'))
      setBusy(false)
    }
  }

  const batchName = batch.resource.state === 'loaded' ? batch.resource.data : ''
  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('students_error_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0) body = <EmptyState title={t('pick_students_empty')} />
  else
    body = (
      <ul className="list card" style={{ padding: 0 }}>
        {resource.data.map((s) => (
          <li key={s.id}>
            <label className="row" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={picked.includes(s.id)}
                onChange={() => toggle(s.id)}
              />
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
            </label>
          </li>
        ))}
      </ul>
    )

  return (
    <>
      <TopBar title={t('pick_students_title', batchName)} back={paths.batch(batchId, 'students')} />
      <div className="field" style={{ marginTop: 8 }}>
        <input
          type="search"
          aria-label={t('students_search')}
          placeholder={t('students_search')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {body}
      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}
      <div className="form-actions">
        <Link to={paths.studentNew(batchId)} className="btn btn-outline">
          {t('pick_students_new')}
        </Link>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={busy || picked.length === 0}
          onClick={() => void add()}
        >
          {t('pick_students_add', String(picked.length))}
        </button>
      </div>
    </>
  )
}
