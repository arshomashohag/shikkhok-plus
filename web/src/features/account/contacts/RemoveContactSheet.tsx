/**
 * Remove the account's phone or email, confirmed with the current
 * password [FR8.3] [functional-spec W6 step 5].
 *
 * It names the contact and says what stays. The client never decides
 * whether this contact may go [NFR3.13]: the server keeps at least one,
 * and its `account.contact.last_one` is shown here with a way to add the
 * other kind first. The parent keys the sheet per opening, so reopening
 * never shows the last sheet's finished state. The password is cleared
 * on every answer; Retry after no connection resends `{kind, password}`
 * from memory.
 */
import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { removeContact } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { Sheet } from '../../../ui/components'
import { describedBy, Field, PasswordInput, useFailureText } from '../../auth/parts'
import { securityPaths } from '../security/paths'
import { otherKind, type ContactKind } from './mappers'

interface Refusal {
  text: string
  field: boolean
  lastOne: boolean
  needsPassword: boolean
  retry: boolean
}

/** Where a refusal of the removal goes [functional-spec § 4]. */
export function removeRefusal(e: unknown, text: string): Refusal {
  const error = e instanceof ApiError ? e : null
  const key = error?.messageKey ?? ''
  return {
    text,
    field: key === 'auth.password.current_wrong',
    lastOne: key === 'account.contact.last_one',
    needsPassword: key === 'account.contact.password_required',
    retry: error !== null && (error.offline || error.retryable),
  }
}

export function RemoveContactSheet({
  kind,
  contact,
  onClose,
  onRemoved,
}: {
  kind: ContactKind
  /** The contact as shown, which the body names. */
  contact: string
  onClose: () => void
  onRemoved: () => void
}) {
  const { t } = useT()
  const failure = useFailureText()
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<Refusal | null>(null)
  /** The request last sent, for Retry only; memory, never storage. */
  const sent = useRef<string | null>(null)

  async function remove(withPassword: string) {
    sent.current = withPassword
    setBusy(true)
    setRefusal(null)
    try {
      await removeContact(kind, withPassword)
      sent.current = null
      onRemoved()
    } catch (e) {
      setPassword('')
      setRefusal(removeRefusal(e, failure(e)))
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    if (!password) {
      setRefusal({
        text: t('web_auth_password_required'),
        field: true,
        lastOne: false,
        needsPassword: false,
        retry: false,
      })
      return
    }
    void remove(password)
  }

  const fieldError = refusal?.field ? refusal.text : null
  return (
    <Sheet title={t('contacts_remove_title')} onClose={onClose} dirty={password !== ''}>
      <form onSubmit={onSubmit} noValidate data-testid="remove-contact-sheet">
        <p style={{ marginTop: 0 }}>{t('contacts_remove_body', contact)}</p>
        <Field id="remove-password" label={t('web_password_current')} error={fieldError}>
          <PasswordInput
            id="remove-password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            invalid={Boolean(fieldError)}
            describedBy={describedBy('remove-password', false, Boolean(fieldError))}
            disabled={busy}
            autofocusInSheet
          />
        </Field>
        {refusal && !refusal.field ? (
          <div className="banner error" role="alert">
            <span>
              {refusal.text}
              {refusal.lastOne ? (
                <>
                  {' '}
                  <Link to={securityPaths.addContact(otherKind(kind))}>
                    {t('contacts_add_other')}
                  </Link>
                </>
              ) : null}
              {refusal.needsPassword ? (
                <>
                  {' '}
                  <Link to={securityPaths.password()}>{t('contacts_set_password')}</Link>
                </>
              ) : null}
            </span>
            {refusal.retry && sent.current !== null ? (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() => void remove(sent.current ?? '')}
              >
                {t('auth_retry')}
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="button-row">
          <button type="button" className="btn btn-outline" disabled={busy} onClick={onClose}>
            {t('action_cancel')}
          </button>
          <button type="submit" className="btn btn-danger grow" disabled={busy}>
            {t('contacts_remove_confirm')}
          </button>
        </div>
      </form>
    </Sheet>
  )
}
