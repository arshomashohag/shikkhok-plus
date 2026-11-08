/**
 * Settings → Password: set a first password (an account made before
 * passwords), or change it (the current one first).
 *
 * The server ends **every** session of the account on either, this one
 * included, and answers with a new token pair; the screen stores that
 * pair at once, so the person stays signed in here while every other
 * device is signed out. The passwords live in this screen's state only
 * and are cleared once sent.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { setMyPassword } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { TopBar } from '../../../ui/components'
import { newPasswordProblem } from '../../auth/identifier'
import { describedBy, Field, HiddenUsername, PasswordInput, useFailureText } from '../../auth/parts'
import { needsPassword } from './PasswordPrompt'
import type { SettingsNotice } from './paths'

/** Refusals that belong under the current-password field. */
const CURRENT_KEYS = new Set(['auth.password.current_wrong', 'auth.password.too_many_attempts'])

/** Refusals that belong under the new-password field. */
const NEW_KEYS = new Set([
  'auth.password.too_short',
  'auth.password.too_long',
  'auth.password.too_common',
])

export function Password() {
  const { t } = useT()
  const failure = useFailureText()
  const navigate = useNavigate()
  const { session, signIn } = useReadySession()
  const first = needsPassword(session.me)
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [currentError, setCurrentError] = useState<string | null>(null)
  const [newError, setNewError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setCurrentError(null)
    setNewError(null)
    setFormError(null)
    if (!first && !current) {
      setCurrentError(t('web_auth_password_required'))
      return
    }
    const problem = newPasswordProblem(password, confirm)
    if (problem) {
      setNewError(t(problem))
      return
    }
    setBusy(true)
    try {
      const tokens = await setMyPassword(first ? null : current, password)
      setCurrent('')
      setPassword('')
      setConfirm('')
      // Every session ended on the server, this one too: keep the new pair.
      signIn(tokens)
      const state: SettingsNotice = {
        notice: t(first ? 'web_password_set_done' : 'web_password_changed_done'),
      }
      navigate('/settings', { replace: true, state })
    } catch (err) {
      setBusy(false)
      const text = failure(err)
      const key = err instanceof ApiError ? err.messageKey : ''
      if (CURRENT_KEYS.has(key)) {
        setCurrent('')
        setCurrentError(text)
      } else if (NEW_KEYS.has(key)) setNewError(text)
      else setFormError(text)
    }
  }

  const title = t(first ? 'web_password_set_title' : 'web_password_change_title')
  return (
    <>
      <TopBar title={title} back="/settings" />
      <form className="card" onSubmit={onSubmit} noValidate>
        <p className="meta" style={{ marginTop: 0 }}>
          {t(first ? 'web_password_set_body' : 'web_password_change_body')}
        </p>
        <HiddenUsername value={session.me.phone ?? session.me.email ?? ''} />
        {first ? null : (
          <Field id="current-password" label={t('web_password_current')} error={currentError}>
            <PasswordInput
              id="current-password"
              value={current}
              onChange={setCurrent}
              autoComplete="current-password"
              invalid={Boolean(currentError)}
              describedBy={describedBy('current-password', false, Boolean(currentError))}
              disabled={busy}
              autoFocus
            />
          </Field>
        )}
        <Field
          id="new-password"
          label={t('web_auth_new_password')}
          help={t('web_auth_password_rule')}
          error={newError}
        >
          <PasswordInput
            id="new-password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            invalid={Boolean(newError)}
            describedBy={describedBy('new-password', true, Boolean(newError))}
            disabled={busy}
            autoFocus={first}
          />
        </Field>
        <Field id="confirm-password" label={t('web_auth_confirm_password')}>
          <PasswordInput
            id="confirm-password"
            value={confirm}
            onChange={setConfirm}
            autoComplete="new-password"
            disabled={busy}
          />
        </Field>
        <p className="help" style={{ margin: '8px 0 0' }}>
          {t('web_password_others_signed_out')}
        </p>
        {formError ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            {formError}
          </div>
        ) : null}
        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? t('web_auth_saving_password') : t('web_password_save')}
          </button>
        </div>
      </form>
    </>
  )
}
