/**
 * Admin log-in: a mobile number or an email address, the code, then the
 * authenticator.
 *
 *  1. **Number or address.** The server answers everyone the same way and
 *     sends a code -- by SMS to a number, by email to an address -- only
 *     to an administrator, so this screen's confirmation reads the same
 *     for anyone [D-33]. One field: an `@` says it is an address.
 *  2. **Code.** Spending it returns a five-minute challenge and says
 *     which step comes next.
 *  3. **Set up** (first log-in): a QR code and the key, then a code from
 *     the app; the server answers with the session and ten recovery
 *     codes, shown once, before the dashboard opens.
 *     **Verify** (every other log-in): a code from the app, or a
 *     recovery code.
 *
 * Nothing on these screens is stored: the challenge, the secret and the
 * recovery codes live in this component's state and go with it. Only the
 * final token is kept (`../session.ts`).
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Identifier, Schemas } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { readIdentifier, shownIdentifier } from '../../features/auth/identifier'
import { useT } from '../../i18n/i18n'
import { AdminAuthFrame } from '../AdminChrome'
import { lastEndReason, saveAdminSession } from '../session'
import { finishAdminSignIn, sendAdminCode, verifyAdminCode } from './api'
import { isUnavailable } from '../errors'
import {
  AuthenticatorSetup,
  RecoveryCodeList,
  useWarnBeforeUnload,
  type CopyLabels,
} from '../../ui/authenticator'
import { sixDigits } from '../../core/codes'

const RESEND_AFTER_S = 60

interface Challenge {
  token: string
  /** Epoch milliseconds. */
  expiresAt: number
}

type Step =
  | { step: 'phone' }
  | { step: 'sms'; identifier: Identifier }
  | { step: 'enroll'; challenge: Challenge; secret: string; uri: string }
  | { step: 'verify'; challenge: Challenge }
  | { step: 'codes'; session: Schemas['AdminSessionResponse']; codes: string[] }

/** Why the phone step is showing a notice. */
type Notice = 'session-ended' | 'signed-out' | 'challenge-expired' | null

function initialNotice(): Notice {
  const reason = lastEndReason()
  if (reason === 'expired') return 'session-ended'
  if (reason === 'signed-out') return 'signed-out'
  return null
}

const NOTICE_KEY: Record<Exclude<Notice, null>, string> = {
  'session-ended': 'web_admin_session_ended',
  'signed-out': 'web_admin_signed_out',
  'challenge-expired': 'web_admin_challenge_expired',
}

export function AdminSignIn() {
  const { t, message } = useT()
  const [step, setStep] = useState<Step>({ step: 'phone' })
  const [notice, setNotice] = useState<Notice>(initialNotice)

  useEffect(() => {
    document.title = `${t('web_admin_title')} · ShikkhokPlus`
  }, [t])

  // A challenge lasts five minutes; when it lapses, start again.
  const challenge = step.step === 'enroll' || step.step === 'verify' ? step.challenge : null
  useEffect(() => {
    if (!challenge) return
    const timer = window.setTimeout(
      () => {
        setNotice('challenge-expired')
        setStep({ step: 'phone' })
      },
      Math.max(0, challenge.expiresAt - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [challenge])

  function restart(why: Notice) {
    setNotice(why)
    setStep({ step: 'phone' })
  }

  /** The text for a failure every step words the same way. */
  function commonFailure(e: unknown): string {
    if (!(e instanceof ApiError)) return t('error_unexpected')
    if (isUnavailable(e)) return t('web_admin_unavailable')
    if (e.status === 403) return t('web_admin_signin_not_admin')
    return message(e.messageKey, e.details)
  }

  function challengeFrom(r: Schemas['AdminChallengeResponse']): Step {
    const c = { token: r.challenge, expiresAt: Date.now() + r.expires_in * 1000 }
    if (r.stage === 'enroll' && r.enrollment)
      return {
        step: 'enroll',
        challenge: c,
        secret: r.enrollment.secret,
        uri: r.enrollment.otpauth_uri,
      }
    return { step: 'verify', challenge: c }
  }

  function signedIn(r: Schemas['AdminSessionResponse']) {
    if (r.recovery_codes?.length) setStep({ step: 'codes', session: r, codes: r.recovery_codes })
    else saveAdminSession(r)
  }

  let body
  switch (step.step) {
    case 'phone':
      body = (
        <PhoneStep
          notice={notice ? t(NOTICE_KEY[notice]) : null}
          onSent={(identifier) => {
            setNotice(null)
            setStep({ step: 'sms', identifier })
          }}
          failure={commonFailure}
        />
      )
      break
    case 'sms':
      body = (
        <SmsStep
          identifier={step.identifier}
          onVerified={(r) => setStep(challengeFrom(r))}
          onChangeNumber={() => restart(null)}
          failure={commonFailure}
        />
      )
      break
    case 'enroll':
    case 'verify':
      body = (
        <MfaStep
          key={step.challenge.token}
          step={step}
          onDone={signedIn}
          onRestart={(why) => restart(why)}
          failure={commonFailure}
        />
      )
      break
    case 'codes':
      body = <RecoveryCodes codes={step.codes} onSaved={() => saveAdminSession(step.session)} />
      break
  }

  return <AdminAuthFrame>{body}</AdminAuthFrame>
}

// ------------------------------------------------------------------ phone

function PhoneStep({
  notice,
  onSent,
  failure,
}: {
  notice: string | null
  onSent: (identifier: Identifier) => void
  failure: (e: unknown) => string
}) {
  const { t } = useT()
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const isEmail = typed.includes('@')
    const identifier = readIdentifier(isEmail ? 'email' : 'phone', typed)
    if (!identifier) {
      setError(t(isEmail ? 'web_admin_email_invalid' : 'phone_invalid'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await sendAdminCode(identifier)
      onSent(identifier)
    } catch (err) {
      setError(failure(err))
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate>
      <h1>{t('web_admin_signin_title')}</h1>
      <p className="meta">{t('web_admin_signin_sub')}</p>
      {notice ? (
        <div className="banner info admin-notice" role="status">
          {notice}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="admin-phone">{t('web_admin_identifier_label')}</label>
        <input
          id="admin-phone"
          name="username"
          type="text"
          autoComplete="username"
          placeholder={t('web_admin_identifier_hint')}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'admin-phone-error' : undefined}
          autoFocus
        />
        {error ? (
          <span id="admin-phone-error" className="field-error" role="alert">
            {error}
          </span>
        ) : null}
      </div>
      <div className="button-row">
        <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
          {busy ? t('auth_sending') : t('auth_request_code')}
        </button>
      </div>
    </form>
  )
}

// -------------------------------------------------------------------- sms

function SmsStep({
  identifier,
  onVerified,
  onChangeNumber,
  failure,
}: {
  identifier: Identifier
  onVerified: (r: Schemas['AdminChallengeResponse']) => void
  onChangeNumber: () => void
  failure: (e: unknown) => string
}) {
  const { t } = useT()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resendIn, setResendIn] = useState(RESEND_AFTER_S)
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (resendIn <= 0) return
    const timer = window.setTimeout(() => setResendIn((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [resendIn])

  useEffect(() => {
    if (!busy) ref.current?.focus()
  }, [busy])

  async function check(value: string) {
    setBusy(true)
    setError(null)
    try {
      onVerified(await verifyAdminCode(identifier, value))
    } catch (e) {
      setError(failure(e))
      setCode('')
      setBusy(false)
    }
  }

  async function resend() {
    setBusy(true)
    setError(null)
    try {
      await sendAdminCode(identifier)
      setCode('')
      setResendIn(RESEND_AFTER_S)
    } catch (e) {
      setError(failure(e))
    } finally {
      setBusy(false)
    }
  }

  function onChange(value: string) {
    const digits = sixDigits(value)
    setCode(digits)
    if (digits.length === 6 && !busy) void check(digits)
  }

  return (
    <div>
      <h1>{t('auth_code_label')}</h1>
      <p className="meta">
        {t('web_admin_signin_code_sent')} <strong>{shownIdentifier(identifier)}</strong>
      </p>
      <div className="field">
        <label htmlFor="admin-sms" className="visually-hidden">
          {t('auth_code_label')}
        </label>
        <input
          ref={ref}
          id="admin-sms"
          name="code"
          className="otp-input"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          disabled={busy}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby="admin-sms-help"
        />
        <span id="admin-sms-help" className="help">
          {busy ? t('auth_checking_code') : t('auth_code_auto_checks')}
        </span>
        {error ? (
          <span className="field-error" role="alert">
            {error}
          </span>
        ) : null}
      </div>
      <div className="button-row">
        <button
          type="button"
          className="btn btn-outline"
          disabled={busy || resendIn > 0}
          onClick={() => void resend()}
        >
          {resendIn > 0
            ? t('auth_resend_in', `0:${String(resendIn).padStart(2, '0')}`)
            : t('auth_resend')}
        </button>
        <button type="button" className="btn btn-text" onClick={onChangeNumber}>
          {t('auth_change_number')}
        </button>
      </div>
    </div>
  )
}

// -------------------------------------------------------- authenticator

function MfaStep({
  step,
  onDone,
  onRestart,
  failure,
}: {
  step: Extract<Step, { step: 'enroll' | 'verify' }>
  onDone: (r: Schemas['AdminSessionResponse']) => void
  onRestart: (why: Notice) => void
  failure: (e: unknown) => string
}) {
  const { t } = useT()
  const enrolling = step.step === 'enroll'
  const [recoveryMode, setRecoveryMode] = useState(false)
  const [code, setCode] = useState('')
  const [recovery, setRecovery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [locked, setLocked] = useState(false)
  const codeRef = useRef<HTMLInputElement>(null)
  const recoveryRef = useRef<HTMLInputElement>(null)

  // Keep the cursor in the field the person is typing into, including
  // after a wrong code re-enables it.
  useEffect(() => {
    if (busy || locked) return
    if (recoveryMode) recoveryRef.current?.focus()
    else codeRef.current?.focus()
  }, [busy, locked, recoveryMode])

  async function submit(proof: { code: string } | { recovery_code: string }) {
    setBusy(true)
    setError(null)
    try {
      onDone(await finishAdminSignIn(step.challenge.token, proof))
    } catch (e) {
      setBusy(false)
      if (e instanceof ApiError && e.status === 401) {
        onRestart('challenge-expired')
        return
      }
      if (e instanceof ApiError && (e.code === 'ADMIN_MFA_LOCKED' || e.status === 409)) {
        setLocked(true)
        return
      }
      if (e instanceof ApiError && e.code === 'ADMIN_MFA_WRONG') {
        if ('code' in proof) {
          setCode('')
          setError(t('web_admin_wrong_code'))
        } else {
          setError(t('web_admin_wrong_recovery'))
        }
        return
      }
      setError(failure(e))
    }
  }

  function onCode(value: string) {
    const digits = sixDigits(value)
    setCode(digits)
    if (digits.length === 6 && !busy) void submit({ code: digits })
  }

  function onRecovery(e: FormEvent) {
    e.preventDefault()
    const typed = recovery.trim().toUpperCase()
    if (!typed) return
    void submit({ recovery_code: typed })
  }

  if (locked)
    return (
      <div>
        <h1>{t(enrolling ? 'web_admin_enroll_title' : 'web_admin_verify_title')}</h1>
        <div className="banner error admin-notice" role="alert">
          {t('web_admin_locked')}
        </div>
        <div className="button-row">
          <button type="button" className="btn btn-outline" onClick={() => onRestart(null)}>
            {t('web_admin_start_again')}
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
      <h1>{t(enrolling ? 'web_admin_enroll_title' : 'web_admin_verify_title')}</h1>
      {recoveryMode ? null : (
        <p className="meta">{t(enrolling ? 'web_admin_enroll_body' : 'web_admin_verify_body')}</p>
      )}
      {step.step === 'enroll' ? <Enrollment secret={step.secret} uri={step.uri} /> : null}

      {recoveryMode ? (
        <form onSubmit={onRecovery} noValidate>
          <div className="field">
            <label htmlFor="admin-recovery">{t('web_admin_recovery_label')}</label>
            <input
              ref={recoveryRef}
              id="admin-recovery"
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
              aria-describedby="admin-recovery-help"
            />
            <span id="admin-recovery-help" className="help">
              {t('web_admin_recovery_help')}
            </span>
            {errorLine}
          </div>
          <div className="button-row">
            <button type="submit" className="btn btn-primary" disabled={busy || !recovery.trim()}>
              {busy ? t('web_admin_checking') : t('web_admin_recovery_submit')}
            </button>
          </div>
        </form>
      ) : (
        <div className="field">
          <label htmlFor="admin-totp">
            {t(enrolling ? 'web_admin_enroll_code_label' : 'web_admin_verify_code_label')}
          </label>
          <input
            ref={codeRef}
            id="admin-totp"
            name="totp"
            className="otp-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            disabled={busy}
            onChange={(e) => onCode(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby="admin-totp-help"
          />
          <span id="admin-totp-help" className="help">
            {busy ? t('web_admin_checking') : t('auth_code_auto_checks')}
          </span>
          {errorLine}
        </div>
      )}

      <p className="help admin-time">{t('web_admin_challenge_time')}</p>
      <div className="button-row">
        {!enrolling ? (
          <button
            type="button"
            className="btn btn-text"
            disabled={busy}
            onClick={() => {
              setRecoveryMode((r) => !r)
              setError(null)
            }}
          >
            {recoveryMode ? t('web_admin_use_app') : t('web_admin_use_recovery')}
          </button>
        ) : null}
        <button type="button" className="btn btn-text" onClick={() => onRestart(null)}>
          {t('web_admin_start_again')}
        </button>
      </div>
    </div>
  )
}

function useCopyLabels(copy: string): CopyLabels {
  const { t } = useT()
  return { copy, copied: t('web_admin_copied'), failed: t('web_admin_copy_failed') }
}

function Enrollment({ secret, uri }: { secret: string; uri: string }) {
  const { t } = useT()
  const copy = useCopyLabels(t('web_admin_copy'))
  return (
    <AuthenticatorSetup
      secret={secret}
      uri={uri}
      secretTestId="admin-secret"
      labels={{
        ...copy,
        qr: t('web_admin_enroll_qr_label'),
        openApp: t('web_admin_enroll_open_app'),
        keyLabel: t('web_admin_enroll_key_label'),
      }}
    />
  )
}

// ---------------------------------------------------------- recovery codes

function RecoveryCodes({ codes, onSaved }: { codes: string[]; onSaved: () => void }) {
  const { t } = useT()
  const copy = useCopyLabels(t('web_admin_copy_all'))
  // Shown once: warn before a reload or a closed tab loses them.
  useWarnBeforeUnload(true)

  return (
    <div>
      <h1>{t('web_admin_codes_title')}</h1>
      <div className="banner error admin-notice admin-codes-warning" role="alert">
        {t('web_admin_codes_warning')}
      </div>
      <p className="meta">{t('web_admin_codes_where')}</p>
      <RecoveryCodeList codes={codes} label={t('web_admin_codes_label')} copy={copy} />
      <div className="button-row">
        <button type="button" className="btn btn-primary btn-money" onClick={onSaved}>
          {t('web_admin_codes_saved')}
        </button>
      </div>
    </div>
  )
}
