/**
 * Teachers and coaching centres, most recently seen first, as the server
 * orders them. A table on a wide window, a list on a phone. The name
 * filter only hides rows on screen.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { ago, formatDateTime } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useWide } from '../../core/useWide'
import { useT } from '../../i18n/i18n'
import { EmptyState, Loading, StaleBanner } from '../../ui/components'
import { readWorkspaces } from './api'
import { AdminFailure, AdminFrame } from './AdminFrame'
import {
  filterWorkspaces,
  mapWorkspaces,
  PLATFORM_KEY,
  workspaceName,
  type Workspace,
} from './mappers'
import { adminPaths } from './paths'

export function AdminTeachers() {
  const { t } = useT()
  const wide = useWide()
  const [query, setQuery] = useState('')
  const { resource, reload } = useResource(() => readWorkspaces().then(mapWorkspaces), [])

  if (resource.state === 'loading')
    return (
      <AdminFrame tab="teachers">
        <Loading rows={5} />
      </AdminFrame>
    )
  if (resource.state === 'failed')
    return (
      <AdminFailure
        tab="teachers"
        title={t('web_admin_tab_teachers')}
        error={resource.error}
        onRetry={reload}
      />
    )

  const all = resource.data
  const shown = filterWorkspaces(all, query)
  return (
    <AdminFrame tab="teachers" subtitle={t('web_admin_workspaces_count', all.length)}>
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      {all.length === 0 ? (
        <div className="card">
          <EmptyState title={t('web_admin_no_workspaces')} />
        </div>
      ) : (
        <div className="card flush">
          <div className="toolbar admin-toolbar">
            <input
              type="search"
              className="search"
              placeholder={t('web_admin_filter_name')}
              aria-label={t('web_admin_filter_name')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {shown.length === 0 ? (
            <p className="meta admin-empty-line">{t('web_admin_no_match')}</p>
          ) : wide ? (
            <WorkspaceTable list={shown} />
          ) : (
            <ul className="list">
              {shown.map((w) => (
                <WorkspaceRow key={w.id} w={w} />
              ))}
            </ul>
          )}
        </div>
      )}
    </AdminFrame>
  )
}

function Platforms({ w }: { w: Workspace }) {
  const { t } = useT()
  if (w.platforms.length === 0) return <span className="meta">{t('web_admin_no_app')}</span>
  return (
    <span className="chips admin-chips">
      {w.platforms.map((p) => (
        <span key={p} className="chip chip-neutral">
          {t(PLATFORM_KEY[p])}
        </span>
      ))}
    </span>
  )
}

function LastSeen({ at, labelled }: { at: string | null; labelled?: boolean }) {
  const { t, lang } = useT()
  if (!at) return <span className="meta">{t('web_admin_never_seen')}</span>
  const when = ago(at, new Date(), t)
  return (
    <span className="admin-when">
      <span>{labelled ? t('web_admin_last_seen', when) : when}</span>
      <span className="meta">{formatDateTime(at, lang, true)}</span>
    </span>
  )
}

function kindLabel(w: Workspace, t: (key: string) => string): string {
  return t(w.kind === 'centre' ? 'web_admin_kind_centre' : 'web_admin_kind_teacher')
}

function WorkspaceTable({ list }: { list: Workspace[] }) {
  const { t, lang } = useT()
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">{t('web_admin_col_name')}</th>
            <th scope="col">{t('web_admin_col_kind')}</th>
            <th scope="col">{t('web_admin_col_apps')}</th>
            <th scope="col">{t('web_admin_col_joined')}</th>
            <th scope="col">{t('web_admin_col_last_seen')}</th>
            <th scope="col">
              <span className="visually-hidden">{t('web_admin_help_questions')}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {list.map((w) => (
            <tr key={w.id}>
              <td className={w.name ? 'admin-name' : 'admin-name unnamed'}>
                {workspaceName(w, t)}
              </td>
              <td className="admin-nowrap">{kindLabel(w, t)}</td>
              <td>
                <Platforms w={w} />
              </td>
              <td className="admin-nowrap">{formatDateTime(w.joinedAt, lang, true)}</td>
              <td>
                <LastSeen at={w.lastSeenAt} />
              </td>
              <td className="admin-nowrap">
                {w.ref ? (
                  <Link className="btn btn-text btn-small" to={adminPaths.tickets({ ref: w.ref })}>
                    {t('web_admin_help_questions')}
                  </Link>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function WorkspaceRow({ w }: { w: Workspace }) {
  const { t, lang } = useT()
  return (
    <li className="row admin-workspace">
      <div className="grow">
        <span className={w.name ? 'title' : 'title unnamed'}>{workspaceName(w, t)}</span>
        <span className="meta">
          {kindLabel(w, t)} · {t('web_admin_joined_on', formatDateTime(w.joinedAt, lang, true))}
        </span>
        <div className="admin-workspace-foot">
          <Platforms w={w} />
          <LastSeen at={w.lastSeenAt} labelled />
        </div>
        {w.ref ? (
          <Link
            className="btn btn-text btn-small admin-inline-link"
            to={adminPaths.tickets({ ref: w.ref })}
          >
            {t('web_admin_help_questions')}
          </Link>
        ) : null}
      </div>
    </li>
  )
}
