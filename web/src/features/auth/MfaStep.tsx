/**
 * Signing in, second step: a code from the authenticator app, or a
 * recovery code instead, for an account with two-step verification on.
 *
 * The password has already been checked; what it bought is a five-minute
 * challenge that grants nothing by itself. **No token exists until this
 * step succeeds**, so nothing is stored before then, and a 401 here means
 * only that the challenge lapsed: the person starts again from the
 * sign-in form. The call is anonymous (`finishSignIn`), so that 401 never
 * reaches token renewal or sign-out. (The code flow's own authenticator
 * field is on its password step, `ChoosePassword.tsx`.)
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { finishSignIn, type Schemas } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { sixDigits } from '../../core/codes'

export interface Challenge {
  token: string
  /** Epoch milliseconds. */
  expiresAt: number
}

export function MfaStep({
  challenge,
  onDone,
  onRestart,
}: {
  challenge: Challenge
  onDone: (tokens: Schemas['TokenResponse']) => void
  /** Back to the sign-in form; `expired` says why, for the notice there. */
  onRestart: (expired: boolean) => void
}) {
  const { t, message } = useT()
  const [recoveryMode, setRecoveryMode] = useState(false)
  const [code, setCode] = useState('')
  const [recovery, setRecovery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [locked, setLocked] = useState<string | null>(null)
  const codeRef = useRef<HTMLInputElement>(null)
  const recoveryRef = useRef<HTMLInputElement>(null)

  // The challenge lasts five minutes; when it lapses on screen, start again.
  useEffect(() => {
    const timer = window.setTimeout(
      () => onRestart(true),
      Math.max(0, challenge.expiresAt - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [challenge, onRestart])

  // Keep the cursor in the field being typed into, including after a
  // wrong code re-enables it.
  useEffect(() => {
    if (busy || locked) return
    if (recoveryMode) recoveryRef.current?.focus()
    else codeRef.current?.focus()
  }, [busy, locked, recoveryMode])

  async function submit(proof: { code: string } | { recovery_code: string }) {
    setBusy(true)
    setError(null)
    try {
      onDone(await finishSignIn(challenge.token, proof))
    } catch (e) {
      setBusy(false)
      if (!(e instanceof ApiError)) {
        setError(t('error_unexpected'))
        return
      }
      if (e.status === 401 || e.messageKey === 'mfa.challenge_expired') {
        onRestart(true)
        return
      }
      if (e.messageKey === 'mfa.locked') {
        setLocked(message(e.messageKey, e.details))
        return
      }
      if (e.messageKey === 'mfa.code_wrong' && 'recovery_code' in proof) {
        setError(t('web_mfa_recovery_wrong'))
        return
      }
      if ('code' in proof) setCode('')
      setError(message(e.messageKey, e.details))
    }
  }

  function onCode(value: string) {
    const digits = sixDigits(value)
    setCode(digits)
    // It checks by itself after the sixth digit, as the code steps do.
    if (digits.length === 6 && !busy) void submit({ code: digits })
  }

  function onRecovery(e: FormEvent) {
    e.preventDefault()
    const typed = recovery.trim().toUpperCase()
    if (typed) void submit({ recovery_code: typed })
  }

  if (locked)
    return (
      <div>
        <h1>{t('web_mfa_signin_title')}</h1>
        <div className="banner error" role="alert" style={{ margin: '16px 0' }}>
          {locked}
        </div>
        <div className="button-row">
          <button type="button" className="btn btn-outline" onClick={() => onRestart(false)}>
            {t('web_mfa_start_again')}
          </button>
        </div>
      </div>
    )

  const errorLine = error ? (
    <span className="field-error" role="alert">
      {error}
    </span>
  ) : null

  return (
    <div>
      <h1>{t('web_mfa_signin_title')}</h1>
      {recoveryMode ? null : <p className="meta">{t('web_mfa_signin_body')}</p>}
      {recoveryMode ? (
        <form onSubmit={onRecovery} noValidate>
          <div className="field">
            <label htmlFor="mfa-recovery">{t('web_mfa_recovery_label')}</label>
            <input
              ref={recoveryRef}
              id="mfa-recovery"
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
              aria-invalid={error ? true : undefined}
              aria-describedby="mfa-recovery-help"
            />
            <span id="mfa-recovery-help" className="help">
              {t('web_mfa_recovery_help')}
            </span>
            {errorLine}
          </div>
          <div className="button-row">
            <button type="submit" className="btn btn-primary" disabled={busy || !recovery.trim()}>
              {busy ? t('auth_checking_code') : t('auth_verify')}
            </button>
          </div>
        </form>
      ) : (
        <div className="field">
          <label htmlFor="mfa-code">{t('web_mfa_code_label')}</label>
          <input
            ref={codeRef}
            id="mfa-code"
            name="totp"
            className="otp-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            disabled={busy}
            onChange={(e) => onCode(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby="mfa-code-help"
          />
          <span id="mfa-code-help" className="help">
            {busy ? t('auth_checking_code') : t('auth_code_auto_checks')}
          </span>
          {errorLine}
        </div>
      )}
      <p className="help" style={{ margin: '8px 0 0' }}>
        {t('web_mfa_challenge_time')}
      </p>
      <div className="button-row">
        <button
          type="button"
          className="btn btn-text"
          disabled={busy}
          onClick={() => {
            setRecoveryMode((r) => !r)
            setError(null)
          }}
        >
          {recoveryMode ? t('web_mfa_use_app') : t('web_mfa_use_recovery')}
        </button>
        <button type="button" className="btn btn-text" onClick={() => onRestart(false)}>
          {t('web_mfa_start_again')}
        </button>
      </div>
    </div>
  )
}
