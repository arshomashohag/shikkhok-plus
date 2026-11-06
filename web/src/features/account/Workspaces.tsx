/**
 * Which workspace the teacher screens act on, and opening a coaching centre.
 *
 * The list is what `/v1/me` reports — the server's own answer to which
 * workspaces this account manages — so the switcher can offer nothing the
 * server would then refuse. Opening a centre makes this account its first
 * manager; the session re-reads `/v1/me` and moves into it.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { openCentre, type Schemas } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { useReadySession } from '../../session/session'
import { Section, Sheet } from '../../ui/components'
import {
  CheckIcon,
  ChevronIcon,
  LayersIcon,
  PlusIcon,
  UsersIcon,
  WarningIcon,
} from '../../ui/icons'
import { paths } from '../teacher/paths'

type Workspace = Schemas['WorkspaceResponse']

/** How a workspace is named in the switcher. */
export function workspaceLabel(w: Workspace, solo: string): string {
  return w.kind === 'centre' ? (w.name ?? '') : solo
}

function OpenCentreSheet({ onClose }: { onClose: () => void }) {
  const { t, message } = useT()
  const { session, chooseWorkspace, chooseLens, refresh } = useReadySession()
  const [name, setName] = useState('')
  const [managerName, setManagerName] = useState(session.me.self_name ?? '')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const ready = name.trim() !== '' && managerName.trim() !== ''

  async function open() {
    if (!ready) return
    setBusy(true)
    setFailure(null)
    try {
      const centre = await openCentre({ name: name.trim(), manager_name: managerName.trim() })
      chooseWorkspace(centre.owner_id)
      chooseLens('teacher')
      refresh()
      onClose()
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setFailure(
        error?.offline
          ? t('web_money_offline_nothing_changed')
          : message(error?.messageKey ?? 'error.unexpected'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('centre_open_title')} onClose={onClose}>
      <p className="meta" style={{ marginTop: 0 }}>
        {t('centre_open_sub')}
      </p>
      <div className="field">
        <label htmlFor="oc-name">{t('centre_name_label')}</label>
        <input
          id="oc-name"
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="oc-manager">{t('centre_manager_name_label')}</label>
        <input
          id="oc-manager"
          maxLength={120}
          value={managerName}
          onChange={(e) => setManagerName(e.target.value)}
        />
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!ready || busy}
          onClick={() => void open()}
        >
          {t('centre_open_submit')}
        </button>
      </div>
    </Sheet>
  )
}

export function WorkspaceSection({ online }: { online: boolean }) {
  const { t } = useT()
  const navigate = useNavigate()
  const { session, chooseWorkspace } = useReadySession()
  const [opening, setOpening] = useState(false)
  const workspaces = session.me.workspaces ?? []
  const teacher = session.lens === 'teacher'
  const current = workspaces.find((w) => w.owner_id === session.workspace) ?? workspaces[0]

  return (
    <Section title={t('workspace_section')}>
      <ul className="card flush list">
        {teacher && workspaces.length > 1
          ? workspaces.map((w) => {
              const here = w.owner_id === current?.owner_id
              return (
                <li key={w.owner_id}>
                  <button
                    type="button"
                    className="row"
                    aria-pressed={here}
                    onClick={() => {
                      if (here) return
                      chooseWorkspace(w.owner_id)
                      navigate(paths.today())
                    }}
                  >
                    <LayersIcon />
                    <span className="grow">
                      <span className="title">{workspaceLabel(w, t('workspace_solo'))}</span>
                      <br />
                      <span className="meta">
                        {here ? t('workspace_current') : t('workspace_switch')}
                      </span>
                    </span>
                    {here ? <CheckIcon /> : <ChevronIcon />}
                  </button>
                </li>
              )
            })
          : null}
        {teacher && current?.kind === 'centre' ? (
          <li>
            <button
              type="button"
              className="row"
              disabled={!online}
              onClick={() => navigate(paths.centreMembers())}
            >
              <UsersIcon />
              <span className="grow">
                <span className="title">{t('centre_members_title')}</span>
                <br />
                <span className="meta">
                  {online ? t('centre_members_sub') : t('more_needs_connection')}
                </span>
              </span>
              <ChevronIcon />
            </button>
          </li>
        ) : null}
        <li>
          <button type="button" className="row" disabled={!online} onClick={() => setOpening(true)}>
            <PlusIcon />
            <span className="grow">
              <span className="title">{t('centre_open_title')}</span>
              <br />
              <span className="meta">
                {online ? t('centre_open_sub') : t('more_needs_connection')}
              </span>
            </span>
            <ChevronIcon />
          </button>
        </li>
      </ul>
      {opening ? <OpenCentreSheet onClose={() => setOpening(false)} /> : null}
    </Section>
  )
}
