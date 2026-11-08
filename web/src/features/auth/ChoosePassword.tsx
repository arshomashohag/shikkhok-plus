/**
 * The end of the code flow: choose a password, and with it, for an
 * account with two-step verification on, a code from the authenticator
 * app or a recovery code. The answer is the token pair; nothing is stored
 * before it.
 *
 * The setup token the code bought lasts ten minutes and works once. When
 * it lapses — on screen, or as the server's 401 `auth.password.setup_expired`
 * — the person starts again with a new code. The call is anonymous, so
 * that 401 never reaches token renewal or sign-out.
 */
import { useEffect, useState, type FormEvent } from 'react'
import {
  setUpPassword,
  type Identifier,
  type Schemas,
  type VerifyResponse,
} from '../../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../../api/errors'
import { sixDigits } from '../../core/codes'
import { useT } from '../../i18n/i18n'
import { newPasswordProblem } from './identifier'
import { describedBy, Field, HiddenUsername, PasswordInput, useFailureText } from './parts'

export interface PasswordSetup {
  token: string
  /** Epoch milliseconds. */
  expiresAt: number
  /** The account has an authenticator app on; its code is needed too. */
  mfaRequired: boolean
  /** The phone or email the code went to, for the password manager. */
  username: string
}

/** The setup token's lifetime when an older server does not say. */
export const SETUP_S = 600

/** Server refusals that belong under the new-password field. */
const PASSWORD_KEYS = new Set([
  'auth.password.too_short',
  'auth.password.too_long',
  'auth.password.too_common',
])

/** Server refusals that belong under the authenticator field. */
const MFA_KEYS = new Set(['mfa.code_required', 'mfa.code_wrong', 'mfa.locked'])

/**
 * The setup a `/verify` answer bought.
 *
 * @throws ApiError `error.unexpected` when the answer carries no token
 */
export function setupFrom(answer: VerifyResponse, identifier: Identifier): PasswordSetup {
  const token = answer.password_setup_token
  if (!token) throw new ApiError(200, 'UNEXPECTED', UNEXPECTED_KEY, false)
  return {
    token,
    expiresAt: Date.now() + (answer.password_setup_expires_in ?? SETUP_S) * 1000,
    mfaRequired: answer.mfa_required,
    username: 'phone' in identifier ? identifier.phone : identifier.email,
  }
}

/** True for an answer that means the setup token can no longer be spent. */
export function setupLapsed(e: unknown): boolean {
  return (
    e instanceof ApiError && (e.status === 401 || e.messageKey === 'auth.password.setup_expired')
  )
}

export function ChoosePassword({
  setup,
  initialError,
  onDone,
  onRestart,
}: {
  setup: PasswordSetup
  /** A refusal already met, e.g. sign-up's first try with its password. */
  initialError?: string | null
  onDone: (tokens: Schemas['TokenResponse']) => void
  /** Back to the start of the code flow; `expired` says why. */
  onRestart: (expired: boolean) => void
}) {
  const { t } = useT()
  const failure = useFailureText()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [recoveryMode, setRecoveryMode] = useState(false)
  const [code, setCode] = useState('')
  const [recovery, setRecovery] = useState('')
  const [busy, setBusy] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(initialError ?? null)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(
      () => onRestart(true),
      Math.max(0, setup.expiresAt - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [setup, onRestart])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setPasswordError(null)
    setMfaError(null)
    setFormError(null)
    const problem = newPasswordProblem(password, confirm)
    if (problem) {
      setPasswordError(t(problem))
      return
    }
    const proof = setup.mfaRequired
      ? recoveryMode
        ? { recovery_code: recovery.trim().toUpperCase() || null }
        : { code: code || null }
      : {}
    setBusy(true)
    try {
      const tokens = await setUpPassword({ token: setup.token, password, ...proof })
      setPassword('')
      setConfirm('')
      onDone(tokens)
    } catch (err) {
      setBusy(false)
      if (setupLapsed(err)) {
        onRestart(true)
        return
      }
      const text = failure(err)
      const key = err instanceof ApiError ? err.messageKey : ''
      if (PASSWORD_KEYS.has(key)) setPasswordError(text)
      else if (MFA_KEYS.has(key)) {
        setMfaError(key === 'mfa.code_wrong' && recoveryMode ? t('web_mfa_recovery_wrong') : text)
        setCode('')
      } else setFormError(text)
    }
  }

  const newHelp = t('web_auth_password_rule')
  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{t('web_auth_choose_title')}</h1>
      <p className="meta">{t('web_auth_choose_body')}</p>
      <HiddenUsername value={setup.username} />
      <Field
        id="new-password"
        label={t('web_auth_new_password')}
        help={newHelp}
        error={passwordError}
      >
        <PasswordInput
          id="new-password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          invalid={Boolean(passwordError)}
          describedBy={describedBy('new-password', true, Boolean(passwordError))}
          disabled={busy}
          autoFocus
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

      {setup.mfaRequired ? (
        recoveryMode ? (
          <Field
            id="setup-recovery"
            label={t('web_mfa_recovery_label')}
            help={t('web_mfa_recovery_help')}
            error={mfaError}
          >
            <input
              id="setup-recovery"
              name="recovery_code"
              className="mono recovery-input"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="ABCDE-FGHJK"
              maxLength={24}
              value={recovery}
              disabled={busy}
              onChange={(e) => setRecovery(e.target.value)}
              aria-invalid={mfaError ? true : undefined}
              aria-describedby={describedBy('setup-recovery', true, Boolean(mfaError))}
            />
          </Field>
        ) : (
          <Field
            id="setup-totp"
            label={t('web_mfa_code_label')}
            help={t('web_auth_setup_mfa_help')}
            error={mfaError}
          >
            <input
              id="setup-totp"
              name="totp"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              disabled={busy}
              onChange={(e) => setCode(sixDigits(e.target.value))}
              aria-invalid={mfaError ? true : undefined}
              aria-describedby={describedBy('setup-totp', true, Boolean(mfaError))}
            />
          </Field>
        )
      ) : null}

      {formError ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {formError}
        </div>
      ) : null}

      <div className="button-row">
        <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
          {busy ? t('web_auth_saving_password') : t('web_auth_save_password')}
        </button>
      </div>
      <div className="button-row">
        {setup.mfaRequired ? (
          <button
            type="button"
            className="btn btn-text"
            disabled={busy}
            onClick={() => {
              setRecoveryMode((r) => !r)
              setMfaError(null)
            }}
          >
            {recoveryMode ? t('web_mfa_use_app') : t('web_mfa_use_recovery')}
          </button>
        ) : null}
        <button
          type="button"
          className="btn btn-text"
          disabled={busy}
          onClick={() => onRestart(false)}
        >
          {t('web_mfa_start_again')}
        </button>
      </div>
    </form>
  )
}
