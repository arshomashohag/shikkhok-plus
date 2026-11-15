/**
 * Replace the account's phone or email with a new one [FR8.2]
 * [functional-spec W6 step 4].
 *
 * Entering → Sending → AwaitingCode → Checking → Replaced. The new value
 * and the current password go to `POST /v1/me/contact`; a code goes to
 * the new value, and the old one is removed only once that code comes
 * back. The password is dropped as soon as the code request succeeds, so
 * a new code needs it again: Resend and Change return to the entry step
 * with the new value kept, as on Android.
 *
 * Refusals of the request stay on the entry step, each where it belongs;
 * refusals of the code stay on the code step (`CodeEntry`). Every rule is
 * the server's [FR11.3]; the client checks format only.
 */
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { requestContactCode, verifyContact, type Identifier } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { TopBar } from '../../../ui/components'
import { invalidKey, readIdentifier, shownIdentifier } from '../../auth/identifier'
import {
  CodeEntry,
  describedBy,
  Field,
  identifierInputProps,
  PasswordInput,
  useFailureText,
} from '../../auth/parts'
import { securityPaths, type SettingsNotice } from '../security/paths'
import type { ContactKind } from './mappers'

export function ReplacePhone() {
  return <ReplaceContact kind="phone" />
}

export function ReplaceEmail() {
  return <ReplaceContact kind="email" />
}

type Where = 'value' | 'password' | 'banner'

interface Refusal {
  text: string
  where: Where
  needsPassword: boolean
  retry: boolean
}

const UNDER_VALUE = new Set(['account.contact.already_set', 'email.invalid', 'phone.invalid'])

/** Where a refusal of the code request goes [functional-spec § 4]. */
export function replaceRefusal(e: unknown, text: string): Refusal {
  const error = e instanceof ApiError ? e : null
  const key = error?.messageKey ?? ''
  let where: Where = 'banner'
  if (UNDER_VALUE.has(key)) where = 'value'
  else if (key === 'auth.password.current_wrong') where = 'password'
  return {
    text,
    where,
    needsPassword: key === 'account.contact.password_required',
    retry: error !== null && error.offline,
  }
}

export function ReplaceContact({ kind }: { kind: ContactKind }) {
  const { t } = useT()
  const failure = useFailureText()
  const navigate = useNavigate()
  const { refresh } = useReadySession()
  const [typed, setTyped] = useState('')
  const [password, setPassword] = useState('')
  const [sentTo, setSentTo] = useState<Identifier | null>(null)
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<Refusal | null>(null)
  /** The request last sent, for Retry after no connection; dropped once it succeeds. */
  const sent = useRef<{ identifier: Identifier; password: string } | null>(null)
  const phone = kind === 'phone'

  async function request(identifier: Identifier, withPassword: string) {
    sent.current = { identifier, password: withPassword }
    setBusy(true)
    setRefusal(null)
    try {
      await requestContactCode(identifier, withPassword)
      // The password has done its job: it is not kept for the code step.
      sent.current = null
      setPassword('')
      setSentTo(identifier)
    } catch (e) {
      const routed = replaceRefusal(e, failure(e))
      if (routed.where === 'password') setPassword('')
      setRefusal(routed)
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const identifier = readIdentifier(kind, typed)
    if (!identifier) {
      setRefusal({ text: t(invalidKey(kind)), where: 'value', needsPassword: false, retry: false })
      return
    }
    if (!password) {
      setRefusal({
        text: t('web_auth_password_required'),
        where: 'password',
        needsPassword: false,
        retry: false,
      })
      return
    }
    void request(identifier, password)
  }

  async function verify(identifier: Identifier, code: string) {
    await verifyContact(identifier, code)
    refresh()
    const state: SettingsNotice = {
      notice: t(phone ? 'contacts_replaced_phone' : 'contacts_replaced_email'),
    }
    navigate(securityPaths.contacts(), { replace: true, state })
  }

  /** Back to the entry step, the new value kept; a new code needs the password. */
  function change() {
    setSentTo(null)
    setRefusal(null)
  }

  const title = t(phone ? 'contacts_replace_phone_title' : 'contacts_replace_email_title')
  if (sentTo)
    return (
      <>
        <TopBar title={title} back={securityPaths.contacts()} />
        <div className="card">
          <h2 style={{ marginTop: 0 }}>{t('auth_code_label')}</h2>
          <p className="meta">
            {t(phone ? 'contacts_code_sent_new_phone' : 'contacts_code_sent_new_email')}{' '}
            <strong>{shownIdentifier(sentTo)}</strong>
          </p>
          <CodeEntry verify={(code) => verify(sentTo, code)} resend={async () => change()}>
            <button type="button" className="btn btn-text" onClick={change}>
              {t('auth_change')}
            </button>
          </CodeEntry>
        </div>
      </>
    )

  const valueError = refusal?.where === 'value' ? refusal.text : null
  const passwordError = refusal?.where === 'password' ? refusal.text : null
  return (
    <>
      <TopBar title={title} back={securityPaths.contacts()} />
      <form className="card" onSubmit={onSubmit} noValidate>
        <Field
          id="replace-contact"
          label={t(phone ? 'contacts_new_phone_label' : 'contacts_new_email_label')}
          error={valueError}
        >
          <input
            id="replace-contact"
            name={kind}
            {...identifierInputProps(kind, 'contact')}
            placeholder={phone ? t('auth_phone_hint') : undefined}
            value={typed}
            disabled={busy}
            onChange={(e) => setTyped(e.target.value)}
            aria-invalid={valueError ? true : undefined}
            aria-describedby={describedBy('replace-contact', false, Boolean(valueError))}
            autoFocus
          />
        </Field>
        <Field id="replace-password" label={t('web_password_current')} error={passwordError}>
          <PasswordInput
            id="replace-password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            invalid={Boolean(passwordError)}
            describedBy={describedBy('replace-password', false, Boolean(passwordError))}
            disabled={busy}
          />
        </Field>
        {refusal?.where === 'banner' ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            <span>
              {refusal.text}
              {refusal.needsPassword ? (
                <>
                  {' '}
                  <Link to={securityPaths.password()}>{t('contacts_set_password')}</Link>
                </>
              ) : null}
            </span>
            {refusal.retry && sent.current ? (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() =>
                  sent.current && void request(sent.current.identifier, sent.current.password)
                }
              >
                {t('auth_retry')}
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? t('auth_sending') : t('auth_request_code')}
          </button>
        </div>
      </form>
    </>
  )
}
