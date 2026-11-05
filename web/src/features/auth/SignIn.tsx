/**
 * Sign in with a mobile number and a 6-digit SMS code.
 *
 * The confirmation after "Send code" reads the same for every number,
 * registered or not: the server's response never reveals whether a
 * number has an account [D-33], and neither does this screen.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router'
import { issueCode, verifyCode } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { formatPhone, normalisePhone } from '../../core/format'
import { toLatinDigits } from '../../core/money'
import { useT } from '../../i18n/i18n'
import { useSession } from '../../session/session'

type Step = { step: 'phone' } | { step: 'code'; phone: string }

const RESEND_AFTER_S = 60

export function SignIn() {
  const { t, message } = useT()
  const { signIn } = useSession()
  const location = useLocation()
  const handedOver = (location.state as { phone?: string } | null)?.phone ?? null
  const [step, setStep] = useState<Step>(
    handedOver ? { step: 'code', phone: handedOver } : { step: 'phone' },
  )
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resendIn, setResendIn] = useState(handedOver ? RESEND_AFTER_S : 0)
  const codeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    document.title = `${t('auth_verify')} · ShikkhokPlus`
  }, [t])

  useEffect(() => {
    if (resendIn <= 0) return
    const timer = window.setTimeout(() => setResendIn((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [resendIn])

  useEffect(() => {
    if (step.step === 'code') codeRef.current?.focus()
  }, [step])

  const failure = (e: unknown) =>
    setError(e instanceof ApiError ? message(e.messageKey) : t('error_unexpected'))

  async function requestCode(target: string) {
    setBusy(true)
    setError(null)
    try {
      await issueCode(target)
      setStep({ step: 'code', phone: target })
      setCode('')
      setResendIn(RESEND_AFTER_S)
    } catch (e) {
      failure(e)
    } finally {
      setBusy(false)
    }
  }

  function onPhone(e: FormEvent) {
    e.preventDefault()
    const normalised = normalisePhone(phone)
    if (!normalised) {
      setError(t('phone_invalid'))
      return
    }
    void requestCode(normalised)
  }

  async function submitCode(value: string, target: string) {
    setBusy(true)
    setError(null)
    try {
      signIn(await verifyCode(target, value))
    } catch (e) {
      failure(e)
      setCode('')
      setBusy(false)
    }
  }

  function onCode(value: string) {
    const digits = toLatinDigits(value).replace(/\D/g, '').slice(0, 6)
    setCode(digits)
    // It checks by itself after the sixth digit, as on Android.
    if (digits.length === 6 && step.step === 'code' && !busy) void submitCode(digits, step.phone)
  }

  return (
    <div className="auth-page">
      <div className="auth-card card">
        <div className="brand">
          <img src={`${import.meta.env.BASE_URL}icons/favicon.svg`} alt="" />
          <span>ShikkhokPlus</span>
        </div>

        {step.step === 'phone' ? (
          <form onSubmit={onPhone} noValidate>
            <h1>{t('auth_headline')}</h1>
            <p className="meta">{t('auth_subhead')}</p>
            <div className="field">
              <label htmlFor="phone">{t('auth_phone_label')}</label>
              <input
                id="phone"
                name="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel-national"
                placeholder={t('auth_phone_hint')}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'phone-error' : undefined}
                autoFocus
              />
              {error ? (
                <span id="phone-error" className="field-error" role="alert">
                  {error}
                </span>
              ) : null}
            </div>
            <div className="button-row">
              <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
                {busy ? t('auth_sending') : t('auth_request_code')}
              </button>
            </div>
            <p className="meta" style={{ marginTop: 24 }}>
              {t('auth_new_here')} <Link to="/signup">{t('auth_create_account')}</Link>
            </p>
          </form>
        ) : (
          <div>
            <h1>{t('auth_code_label')}</h1>
            <p className="meta">
              {t('auth_code_sent')} <strong>{formatPhone(step.phone)}</strong>
            </p>
            <div className="field">
              <label htmlFor="code" className="visually-hidden">
                {t('auth_code_label')}
              </label>
              <input
                ref={codeRef}
                id="code"
                name="code"
                className="otp-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                disabled={busy}
                onChange={(e) => onCode(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby="code-help"
              />
              <span id="code-help" className="help">
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
                onClick={() => void requestCode(step.phone)}
              >
                {resendIn > 0
                  ? t('auth_resend_in', `0:${String(resendIn).padStart(2, '0')}`)
                  : t('auth_resend')}
              </button>
              <button
                type="button"
                className="btn btn-text"
                onClick={() => {
                  setStep({ step: 'phone' })
                  setError(null)
                }}
              >
                {t('auth_change_number')}
              </button>
            </div>
            <p className="meta" style={{ marginTop: 24 }}>
              {t('auth_no_code_hint')} <Link to="/signup">{t('auth_create_account')}</Link>
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
