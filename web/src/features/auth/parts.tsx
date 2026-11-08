/**
 * Pieces the sign-in, sign-up and password screens share: the Phone |
 * Email choice, a password field, the one-time code step, and the hidden
 * username a password manager files a new password under.
 *
 * Nothing here decides anything. A wrong code, a refused password or an
 * unknown account is the server's answer, shown through its `message_key`.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../../api/errors'
import { sixDigits } from '../../core/codes'
import { useT } from '../../i18n/i18n'
import type { IdentifierKind } from './identifier'

/** The seconds before "Send a new code" is offered again. */
export const RESEND_AFTER_S = 60

/** The text for any failure: the server's string, or the generic one. */
export function useFailureText(): (e: unknown) => string {
  const { t, message } = useT()
  return (e: unknown) =>
    e instanceof ApiError ? message(e.messageKey, e.details) : t('error_unexpected')
}

/** Phone | Email, as a two-button segmented control. */
export function KindToggle({
  kind,
  onKind,
  disabled,
}: {
  kind: IdentifierKind
  onKind: (kind: IdentifierKind) => void
  disabled?: boolean
}) {
  const { t } = useT()
  return (
    <div
      className="segmented"
      role="group"
      aria-label={t('web_auth_kind_label')}
      style={{ marginTop: 16 }}
    >
      {(['phone', 'email'] as const).map((k) => (
        <button
          key={k}
          type="button"
          aria-pressed={kind === k}
          disabled={disabled}
          onClick={() => onKind(k)}
        >
          {t(k === 'phone' ? 'web_auth_kind_phone' : 'web_auth_kind_email')}
        </button>
      ))}
    </div>
  )
}

/**
 * The input attributes for a phone number or an email address.
 *
 * @param purpose `username` where it names the account being signed into
 *   or created; `contact` where it is a number or address being added
 */
export function identifierInputProps(kind: IdentifierKind, purpose: 'username' | 'contact') {
  if (kind === 'phone')
    return {
      type: 'tel',
      inputMode: 'tel' as const,
      autoComplete: purpose === 'username' ? 'username' : 'tel-national',
    }
  return {
    type: 'email',
    inputMode: 'email' as const,
    autoComplete: purpose === 'username' ? 'username' : 'email',
    autoCapitalize: 'none',
    spellCheck: false,
  }
}

/** One labelled field with its help and error lines tied to the input. */
export function Field({
  id,
  label,
  help,
  error,
  children,
}: {
  id: string
  label: string
  help?: ReactNode
  error?: string | null
  /** The input; it receives the ids from {@link describedBy}. */
  children: ReactNode
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {help ? (
        <span id={`${id}-help`} className="help">
          {help}
        </span>
      ) : null}
      {error ? (
        <span id={`${id}-error`} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  )
}

/** `aria-describedby` for an input inside {@link Field}. */
export function describedBy(id: string, help: boolean, error: boolean): string | undefined {
  return (
    [help ? `${id}-help` : null, error ? `${id}-error` : null].filter(Boolean).join(' ') ||
    undefined
  )
}

/** A password input. Its value is never logged and never stored. */
export function PasswordInput({
  id,
  value,
  onChange,
  autoComplete,
  invalid,
  describedBy: described,
  disabled,
  autoFocus,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  autoComplete: 'current-password' | 'new-password'
  invalid?: boolean
  describedBy?: string
  disabled?: boolean
  autoFocus?: boolean
}) {
  return (
    <input
      id={id}
      name={id}
      type="password"
      autoComplete={autoComplete}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      aria-invalid={invalid ? true : undefined}
      aria-describedby={described}
      autoFocus={autoFocus}
    />
  )
}

/**
 * The account a new password belongs to, for the browser's password
 * manager: a form that sets a password without a username field is
 * saved under nothing. Hidden from sight and from assistive technology.
 */
export function HiddenUsername({ value }: { value: string }) {
  return (
    <input
      type="text"
      name="username"
      autoComplete="username"
      value={value}
      readOnly
      hidden
      aria-hidden="true"
      tabIndex={-1}
    />
  )
}

/**
 * The six-digit code field, which checks by itself after the sixth digit,
 * with "Send a new code" after a minute.
 *
 * @param verify Spends the code; a rejection is shown and the field cleared.
 *   On success the parent moves on, so this step stays busy.
 * @param resend Asks for a new code
 */
export function CodeEntry({
  verify,
  resend,
  children,
}: {
  verify: (code: string) => Promise<void>
  resend: () => Promise<void>
  /** Extra buttons for the row under the field, such as "Change". */
  children?: ReactNode
}) {
  const { t } = useT()
  const failure = useFailureText()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resendIn, setResendIn] = useState(RESEND_AFTER_S)
  const codeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (resendIn <= 0) return
    const timer = window.setTimeout(() => setResendIn((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [resendIn])

  useEffect(() => {
    if (!busy) codeRef.current?.focus()
  }, [busy])

  async function submit(value: string) {
    setBusy(true)
    setError(null)
    try {
      await verify(value)
    } catch (e) {
      setError(failure(e))
      setCode('')
      setBusy(false)
    }
  }

  async function again() {
    setBusy(true)
    setError(null)
    try {
      await resend()
      setCode('')
      setResendIn(RESEND_AFTER_S)
    } catch (e) {
      setError(failure(e))
    } finally {
      setBusy(false)
    }
  }

  function onCode(value: string) {
    const digits = sixDigits(value)
    setCode(digits)
    // It checks by itself after the sixth digit, as on Android.
    if (digits.length === 6 && !busy) void submit(digits)
  }

  return (
    <>
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
          onClick={() => void again()}
        >
          {resendIn > 0
            ? t('auth_resend_in', `0:${String(resendIn).padStart(2, '0')}`)
            : t('auth_resend')}
        </button>
        {children}
      </div>
    </>
  )
}
