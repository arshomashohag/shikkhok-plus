/**
 * Settings → Add phone number / Add email: give the account the way of
 * reaching it that it lacks. A code goes to the new number or address,
 * and the account gains it only once that code comes back.
 *
 * Adding a phone matters beyond signing in: teachers find students and
 * guardians by their number, so the seats and invitations a teacher has
 * already recorded for it appear once it is verified. That is the
 * server's linking, not this screen's; the session simply re-reads
 * `/v1/me` afterwards, lenses included.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { requestContactCode, verifyContact, type Identifier } from '../../../api/endpoints'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { TopBar } from '../../../ui/components'
import {
  invalidKey,
  readIdentifier,
  shownIdentifier,
  type IdentifierKind,
} from '../../auth/identifier'
import {
  CodeEntry,
  describedBy,
  Field,
  identifierInputProps,
  useFailureText,
} from '../../auth/parts'
import type { SettingsNotice } from './paths'

export function AddPhone() {
  return <AddContact kind="phone" />
}

export function AddEmail() {
  return <AddContact kind="email" />
}

function AddContact({ kind }: { kind: IdentifierKind }) {
  const { t } = useT()
  const failure = useFailureText()
  const navigate = useNavigate()
  const { refresh } = useReadySession()
  const [typed, setTyped] = useState('')
  const [sentTo, setSentTo] = useState<Identifier | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const phone = kind === 'phone'

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const identifier = readIdentifier(kind, typed)
    if (!identifier) {
      setError(t(invalidKey(kind)))
      return
    }
    setBusy(true)
    try {
      await requestContactCode(identifier)
      setSentTo(identifier)
    } catch (err) {
      setError(failure(err))
    } finally {
      setBusy(false)
    }
  }

  async function verify(identifier: Identifier, code: string) {
    await verifyContact(identifier, code)
    // A new phone can link seats and invitations: re-read the account and
    // its lenses. The invitations screen reads afresh each time it opens.
    refresh()
    const state: SettingsNotice = {
      notice: t(phone ? 'web_contact_phone_added' : 'web_contact_email_added'),
    }
    navigate('/settings', { replace: true, state })
  }

  const title = t(phone ? 'web_contact_add_phone' : 'web_contact_add_email')
  if (sentTo)
    return (
      <>
        <TopBar title={title} back="/settings" />
        <div className="card">
          <h2 style={{ marginTop: 0 }}>{t('auth_code_label')}</h2>
          <p className="meta">
            {t(phone ? 'web_contact_code_sent_phone' : 'web_contact_code_sent_email')}{' '}
            <strong>{shownIdentifier(sentTo)}</strong>
          </p>
          <CodeEntry
            verify={(code) => verify(sentTo, code)}
            resend={async () => {
              await requestContactCode(sentTo)
            }}
          >
            <button type="button" className="btn btn-text" onClick={() => setSentTo(null)}>
              {t('auth_change')}
            </button>
          </CodeEntry>
        </div>
      </>
    )

  const help = t(phone ? 'web_contact_add_phone_why' : 'web_contact_add_email_why')
  return (
    <>
      <TopBar title={title} back="/settings" />
      <form className="card" onSubmit={onSubmit} noValidate>
        <Field
          id="contact"
          label={t(phone ? 'auth_phone_label' : 'web_auth_email_label')}
          help={help}
          error={error}
        >
          <input
            id="contact"
            name={kind}
            {...identifierInputProps(kind, 'contact')}
            placeholder={phone ? t('auth_phone_hint') : undefined}
            value={typed}
            disabled={busy}
            onChange={(e) => setTyped(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy('contact', true, Boolean(error))}
            autoFocus
          />
        </Field>
        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? t('auth_sending') : t('auth_request_code')}
          </button>
        </div>
      </form>
    </>
  )
}
