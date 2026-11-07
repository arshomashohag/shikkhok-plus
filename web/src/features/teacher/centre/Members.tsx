/**
 * A centre's managers and teachers: who is in, who was invited, who left.
 *
 * Every rule is the server's: an invitation grants nothing until accepted,
 * a removal takes effect on the member's next request, and the last
 * manager cannot be removed. This screen asks and shows the answer.
 */
import { useState } from 'react'
import { inviteMember, listMembers, revokeMember, type Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatPhone, normalisePhone } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { PlusIcon, WarningIcon } from '../../../ui/icons'

type Member = Schemas['MemberResponse']
type Role = Member['role']

/** The state line under a member's name. */
export function memberState(m: Member): string {
  if (m.revoked) return 'centre_member_revoked'
  if (m.decision === 'pending') return 'centre_member_pending'
  if (m.decision === 'declined') return 'centre_member_declined'
  return 'centre_member_accepted'
}

/** The invitation body, or null while the form is not yet sendable. */
export function inviteBody(
  name: string,
  phone: string,
  role: Role,
): Schemas['MemberInviteRequest'] | null {
  const normal = normalisePhone(phone)
  if (!name.trim() || !normal) return null
  return { display_name: name.trim(), phone: normal, role }
}

function failureText(e: unknown, t: (k: string) => string, message: (k: string) => string) {
  const error = e instanceof ApiError ? e : null
  return error?.offline
    ? t('web_money_offline_nothing_changed')
    : message(error?.messageKey ?? 'error.unexpected')
}

function InviteSheet({ onClose, onSent }: { onClose: () => void; onSent: (name: string) => void }) {
  const { t, message } = useT()
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState<Role>('teacher')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const body = inviteBody(name, phone, role)

  async function send() {
    if (!body) return
    setBusy(true)
    setFailure(null)
    try {
      await inviteMember(body)
      onSent(body.display_name)
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('centre_invite_title')} onClose={onClose}>
      <div className="field" style={{ marginTop: 0 }}>
        <label htmlFor="cm-name">{t('centre_invite_name_label')}</label>
        <input
          id="cm-name"
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="cm-phone">{t('centre_invite_phone_label')}</label>
        <input
          id="cm-phone"
          type="tel"
          inputMode="tel"
          placeholder={t('auth_phone_hint')}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="cm-role">{t('centre_invite_role_label')}</label>
        <select id="cm-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          <option value="teacher">{t('centre_member_role_teacher')}</option>
          <option value="manager">{t('centre_member_role_manager')}</option>
        </select>
        <span className="help">{t('centre_invite_help')}</span>
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
          disabled={!body || busy}
          onClick={() => void send()}
        >
          {t('centre_invite_submit')}
        </button>
      </div>
    </Sheet>
  )
}

function RemoveSheet({
  member,
  onClose,
  onRemoved,
}: {
  member: Member
  onClose: () => void
  onRemoved: () => void
}) {
  const { t, message } = useT()
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function confirm() {
    setBusy(true)
    setFailure(null)
    try {
      await revokeMember(member.member_id)
      onRemoved()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('centre_member_remove')} onClose={onClose}>
      <p style={{ marginTop: 0 }}>{t('centre_member_remove_confirm', member.display_name)}</p>
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
          disabled={busy}
          onClick={() => void confirm()}
        >
          {t('centre_member_remove')}
        </button>
      </div>
    </Sheet>
  )
}

export function Members() {
  const { t } = useT()
  const { resource, reload } = useResource((signal) => listMembers(signal), [])
  const [inviting, setInviting] = useState(false)
  const [removing, setRemoving] = useState<Member | null>(null)
  const [snack, setSnack] = useState<string | null>(null)
  // Remove a member only from a read the server just confirmed.
  const fresh = resource.state === 'loaded' && !resource.refreshing && resource.error === null

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('centre_members_title')} error={resource.error} onRetry={reload} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        {resource.data.length <= 1 ? (
          <EmptyState title={t('centre_members_title')} body={t('centre_members_empty')} />
        ) : null}
        <ul className="card flush list">
          {resource.data.map((m) => (
            <li key={m.member_id}>
              <div className="row" style={m.revoked ? { opacity: 0.55 } : undefined}>
                <span className="grow">
                  <span className="title">
                    {m.display_name}
                    {m.is_you ? ` · ${t('centre_member_you')}` : ''}
                  </span>
                  <br />
                  <span className="meta">
                    {[
                      t(`centre_member_role_${m.role}`),
                      formatPhone(m.phone),
                      t(memberState(m)),
                    ].join(' · ')}
                  </span>
                </span>
                {m.revoked ? null : (
                  <button
                    type="button"
                    className="btn btn-text btn-small"
                    disabled={!fresh}
                    onClick={() => setRemoving(m)}
                  >
                    {t('centre_member_remove')}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </>
    )

  return (
    <>
      <TopBar
        title={t('centre_members_title')}
        actions={
          <button
            type="button"
            className="btn btn-primary btn-small"
            onClick={() => setInviting(true)}
          >
            <PlusIcon size={18} />
            {t('centre_invite_title')}
          </button>
        }
      />
      {body}
      {inviting ? (
        <InviteSheet
          onClose={() => setInviting(false)}
          onSent={(name) => {
            setInviting(false)
            setSnack(t('centre_invite_sent', name))
            reload()
          }}
        />
      ) : null}
      {removing ? (
        <RemoveSheet
          member={removing}
          onClose={() => setRemoving(null)}
          onRemoved={() => {
            setSnack(t('centre_member_removed', removing.display_name))
            setRemoving(null)
            reload()
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
