/**
 * Delete my account: the in-app deletion path [TC-19], release-blocking.
 *
 * As Android's `DeleteAccountScreen`: what is deleted and what is kept,
 * worded per role (a teacher who owns batches sees their footprint: the
 * batches they lose access to, the students who keep their records, and
 * the money still recorded as owed); then the person types their own
 * number, and only a number that matches the one on the account enables
 * Delete. On success the session ends and "Your account is deleted" says
 * what happened.
 *
 * **Stricter than Android in one place, deliberately:** Android falls
 * back to the student and guardian wording when the footprint fails to
 * load, which would show a teacher the wrong account of what they keep.
 * Here the summary must load before anything can be deleted.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { ApiError } from '../../../api/errors'
import { useOnline, useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { useSession } from '../../../session/session'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { deleteMyAccount, readDeletionSummary } from './api'
import { footprintOf, numberMatches, type TeacherFootprint } from './mappers'
import { resetUnreadCount } from './unread'
import { resetNewReplies } from '../../help/newReplies'
import './account.css'

export function DeleteAccount() {
  const { t } = useT()
  const { session } = useSession()
  const [deleted, setDeleted] = useState(false)
  const { resource, reload } = useResource(() => readDeletionSummary().then(footprintOf), [])

  if (deleted) return <DeletedBody />

  const phone = session.state === 'ready' ? session.me.phone : null
  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('delete_title')} error={resource.error} onRetry={reload} />
  else if (resource.error)
    body = <ErrorCard title={t('delete_title')} error={resource.error} onRetry={reload} />
  else
    body = (
      <ConfirmBody footprint={resource.data} phone={phone} onDeleted={() => setDeleted(true)} />
    )

  return (
    <>
      <TopBar title={t('delete_title')} back="/more" />
      {body}
    </>
  )
}

function ConfirmBody({
  footprint,
  phone,
  onDeleted,
}: {
  footprint: TeacherFootprint | null
  phone: string | null | undefined
  onDeleted: () => void
}) {
  const { t, message } = useT()
  const navigate = useNavigate()
  const online = useOnline()
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const matches = numberMatches(typed, phone)

  async function onDelete() {
    if (!numberMatches(typed, phone)) return
    setBusy(true)
    setError(null)
    try {
      await deleteMyAccount()
      onDeleted()
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.offline
            ? t('web_account_delete_offline')
            : message(e.messageKey, e.details)
          : t('error_unexpected'),
      )
      setBusy(false)
    }
  }

  return (
    <>
      <div className="card account-danger">
        <div className="title account-danger-title">{t('delete_cannot_undo')}</div>
        {footprint ? (
          <>
            <p>{t('delete_teacher_summary', footprint.batchCount, footprint.studentCount)}</p>
            <p className="meta">{t('delete_teacher_body')}</p>
          </>
        ) : null}
        <div className="field">
          <label htmlFor="del-number">{t('delete_type_number')}</label>
          <input
            id="del-number"
            type="tel"
            inputMode="tel"
            autoComplete="off"
            placeholder={t('delete_number_field')}
            value={typed}
            disabled={busy}
            onChange={(e) => setTyped(e.target.value)}
          />
        </div>
      </div>

      {footprint ? (
        <>
          <ListCard
            heading={t('delete_deleted_heading')}
            lines={[t('delete_deleted_login'), t('delete_teacher_access', footprint.batchCount)]}
          />
          <ListCard
            heading={t('delete_teacher_kept_heading')}
            lines={[
              t('delete_teacher_students_keep', footprint.studentCount),
              t('delete_teacher_owed', footprint.outstanding.format()),
            ]}
          />
        </>
      ) : (
        <>
          <ListCard
            heading={t('delete_deleted_heading')}
            lines={[t('delete_deleted_login'), t('delete_deleted_payments')]}
          />
          <ListCard
            heading={t('delete_kept_heading')}
            lines={[t('delete_kept_records')]}
            note={t('delete_kept_note')}
          />
        </>
      )}

      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      ) : null}
      {!online ? (
        <p className="meta" style={{ marginTop: 12 }}>
          {t('more_needs_connection')}
        </p>
      ) : null}

      <div className="button-row">
        <button
          type="button"
          className="btn btn-outline grow"
          disabled={busy}
          onClick={() => navigate('/more')}
        >
          {t('delete_keep')}
        </button>
        <button
          type="button"
          className="btn btn-delete grow"
          disabled={!matches || busy || !online}
          onClick={() => void onDelete()}
        >
          {busy ? t('web_account_deleting') : t('delete_confirm')}
        </button>
      </div>
    </>
  )
}

function ListCard({ heading, lines, note }: { heading: string; lines: string[]; note?: string }) {
  return (
    <section className="card account-list-card">
      <h2 className="label">{heading}</h2>
      <ul>
        {lines.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      {note ? <p className="meta">{note}</p> : null}
    </section>
  )
}

/**
 * After deletion. The account is gone on the server, so the session ends:
 * on Close, and on leaving this screen or the page however that happens,
 * so no token outlives the account in this browser.
 */
function DeletedBody() {
  const { t } = useT()
  const { signOut } = useSession()
  const pendingEnd = useRef<number | null>(null)

  useEffect(() => {
    // A remount (React StrictMode runs every effect's cleanup once on
    // mount in development) cancels the sign-out the cleanup scheduled,
    // so this screen stays up until it is really left.
    if (pendingEnd.current !== null) {
      window.clearTimeout(pendingEnd.current)
      pendingEnd.current = null
    }
    resetUnreadCount()
    resetNewReplies()
    const end = () => signOut()
    window.addEventListener('pagehide', end)
    return () => {
      window.removeEventListener('pagehide', end)
      pendingEnd.current = window.setTimeout(signOut, 0)
    }
  }, [signOut])

  return (
    <div className="card account-done" role="status">
      <h1>{t('delete_done_title')}</h1>
      <p>{t('web_account_done_body')}</p>
      <p className="meta">{t('delete_done_kept')}</p>
      <div className="button-row">
        <button type="button" className="btn btn-primary btn-money" onClick={signOut}>
          {t('delete_done_close')}
        </button>
      </div>
    </div>
  )
}
