/**
 * Sign in with a mobile number or an email address, and a password.
 *
 * A wrong password, an unknown account and an account that has no
 * password yet get the same answer from the server
 * (`auth.password.wrong`) [D-33], and the same words here, with a static
 * pointer to the code flow (`PasswordCode.tsx`), which is also how an
 * account made before passwords gets its first one.
 *
 * For an account with two-step verification on, the password yields a
 * challenge instead of tokens, and an authenticator code follows
 * (`MfaStep.tsx`); the session starts only after that.
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { signInWithPassword, type Schemas, type VerifyResponse } from '../../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { useSession } from '../../session/session'
import { AuthFrame } from './AuthFrame'
import { MfaStep, type Challenge } from './MfaStep'
import { invalidKey, readIdentifier, type IdentifierKind } from './identifier'
import type { CodeFlowEntry } from './PasswordCode'
import {
  describedBy,
  Field,
  identifierInputProps,
  KindToggle,
  PasswordInput,
  useFailureText,
} from './parts'

/** The challenge's lifetime when an older server does not say. */
const CHALLENGE_S = 300

/** Refusals after which the code flow is the way in. */
const POINT_TO_CODE = new Set(['auth.password.wrong', 'auth.password.too_many_attempts'])

export function SignIn() {
  const { t } = useT()
  const failure = useFailureText()
  const { signIn } = useSession()
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [kind, setKind] = useState<IdentifierKind>('phone')
  const [typed, setTyped] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [identifierError, setIdentifierError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pointToCode, setPointToCode] = useState(false)
  /** Why the form is showing again, when the second step lapsed. */
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    document.title = `${t('auth_verify')} · ShikkhokPlus`
  }, [t])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setIdentifierError(null)
    setError(null)
    setPointToCode(false)
    setNotice(null)
    const identifier = readIdentifier(kind, typed)
    if (!identifier) {
      setIdentifierError(t(invalidKey(kind)))
      return
    }
    if (!password) {
      setError(t('web_auth_password_required'))
      return
    }
    setBusy(true)
    try {
      const answer = await signInWithPassword(identifier, password)
      setPassword('')
      if (answer.mfa_required && answer.mfa_challenge) {
        // No token yet: nothing is stored until the second step succeeds.
        const lifetime = answer.mfa_expires_in ?? CHALLENGE_S
        setChallenge({ token: answer.mfa_challenge, expiresAt: Date.now() + lifetime * 1000 })
        setBusy(false)
        return
      }
      signIn(tokensFrom(answer))
    } catch (err) {
      setError(failure(err))
      setPointToCode(err instanceof ApiError && POINT_TO_CODE.has(err.messageKey))
      setPassword('')
      setBusy(false)
    }
  }

  const restart = useCallback(
    (expired: boolean) => {
      setNotice(expired ? t('web_auth_mfa_expired') : null)
      setError(null)
      setChallenge(null)
    },
    [t],
  )

  const codeEntry: CodeFlowEntry = { kind, typed }

  if (challenge)
    return (
      <AuthFrame>
        <MfaStep key={challenge.token} challenge={challenge} onDone={signIn} onRestart={restart} />
      </AuthFrame>
    )

  return (
    <AuthFrame>
      <form onSubmit={onSubmit} noValidate>
        <h1>{t('web_auth_signin_title')}</h1>
        <p className="meta">{t('web_auth_signin_body')}</p>
        {notice ? (
          <div className="banner info" role="status" style={{ marginTop: 16 }}>
            {notice}
          </div>
        ) : null}
        <KindToggle
          kind={kind}
          disabled={busy}
          onKind={(k) => {
            setKind(k)
            setTyped('')
            setIdentifierError(null)
          }}
        />
        <Field
          id="identifier"
          label={t(kind === 'phone' ? 'auth_phone_label' : 'web_auth_email_label')}
          error={identifierError}
        >
          <input
            id="identifier"
            name="username"
            {...identifierInputProps(kind, 'username')}
            placeholder={kind === 'phone' ? t('auth_phone_hint') : undefined}
            value={typed}
            disabled={busy}
            onChange={(e) => setTyped(e.target.value)}
            aria-invalid={identifierError ? true : undefined}
            aria-describedby={describedBy('identifier', false, Boolean(identifierError))}
            autoFocus
          />
        </Field>
        <Field id="password" label={t('web_auth_password_label')}>
          <PasswordInput
            id="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            invalid={Boolean(error)}
            describedBy={error ? 'signin-error' : undefined}
            disabled={busy}
          />
        </Field>
        {error ? (
          <div id="signin-error" className="banner error" role="alert" style={{ marginTop: 16 }}>
            <span>
              {error}
              {pointToCode ? (
                <>
                  <br />
                  {t('web_auth_password_wrong_hint')}{' '}
                  <Link to="/signin/code" state={codeEntry}>
                    {t('web_auth_get_code')}
                  </Link>
                </>
              ) : null}
            </span>
          </div>
        ) : null}
        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {busy ? t('web_auth_signing_in') : t('auth_verify')}
          </button>
        </div>
        <p className="meta" style={{ marginTop: 16 }}>
          <Link to="/signin/code" state={codeEntry}>
            {t('web_auth_forgot_password')}
          </Link>
        </p>
        <p className="meta">
          {t('web_auth_first_password')}{' '}
          <Link to="/signin/code" state={codeEntry}>
            {t('web_auth_get_code')}
          </Link>
        </p>
        <p className="meta" style={{ marginTop: 24 }}>
          {t('auth_new_here')} <Link to="/signup">{t('auth_create_account')}</Link>
        </p>
      </form>
    </AuthFrame>
  )
}

/**
 * The token pair from an answer that needs no second step.
 *
 * @throws ApiError `error.unexpected` when a token is missing, rather
 *   than storing a half session
 */
function tokensFrom(answer: VerifyResponse): Schemas['TokenResponse'] {
  const { access_token, refresh_token, expires_in } = answer
  if (!access_token || !refresh_token || typeof expires_in !== 'number')
    throw new ApiError(200, 'UNEXPECTED', UNEXPECTED_KEY, false)
  return { access_token, refresh_token, expires_in }
}
