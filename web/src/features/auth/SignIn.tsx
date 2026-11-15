/**
 * Sign in with a username, a mobile number or an email address, typed in
 * one field, and a password [FR4.1] [FR4.2].
 *
 * The client never classifies what was typed: it checks only that the
 * field is not blank and sends it trimmed, as typed, as `login`; no
 * shape check, no `phone` or `email` key [FR11.3] [NFR1.2]. An
 * `email.invalid` (a login with an `@` that is no address) is shown
 * under the field; every other refusal goes in the banner.
 *
 * Nothing typed is handed to the code flow: its links carry no route
 * state, which the browser would keep in `history.state` [functional-spec
 * § 1 defect 6] [NFR3.3].
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
import { describedBy, Field, PasswordInput, useFailureText } from './parts'

/** The challenge's lifetime when an older server does not say. */
const CHALLENGE_S = 300

/** Refusals after which the code flow is the way in. */
const POINT_TO_CODE = new Set(['auth.password.wrong', 'auth.password.too_many_attempts'])

export function SignIn() {
  const { t } = useT()
  const failure = useFailureText()
  const { signIn } = useSession()
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pointToCode, setPointToCode] = useState(false)
  /** Why the form is showing again, when the second step lapsed. */
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    document.title = `${t('auth_verify')} · ShikkhokPlus`
  }, [t])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setLoginError(null)
    setError(null)
    setPointToCode(false)
    setNotice(null)
    const typed = login.trim()
    // Non-blank is the only condition: no shape check, no classification.
    // Sign in stays disabled until then, as on Android.
    if (!typed) return
    if (!password) {
      setError(t('web_auth_password_required'))
      return
    }
    setBusy(true)
    try {
      const answer = await signInWithPassword(typed, password)
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
      if (err instanceof ApiError && err.messageKey === 'email.invalid') setLoginError(failure(err))
      else {
        setError(failure(err))
        setPointToCode(err instanceof ApiError && POINT_TO_CODE.has(err.messageKey))
      }
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
        <Field id="login" label={t('auth_login_label')} error={loginError}>
          <input
            id="login"
            name="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={login}
            disabled={busy}
            onChange={(e) => setLogin(e.target.value)}
            aria-invalid={loginError ? true : undefined}
            aria-describedby={describedBy('login', false, Boolean(loginError))}
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
                  <Link to="/signin/code">{t('web_auth_get_code')}</Link>
                </>
              ) : null}
            </span>
          </div>
        ) : null}
        <div className="button-row">
          <button
            type="submit"
            className="btn btn-primary btn-money"
            disabled={busy || !login.trim()}
          >
            {busy ? t('web_auth_signing_in') : t('auth_verify')}
          </button>
        </div>
        <p className="meta" style={{ marginTop: 16 }}>
          <Link to="/signin/code">{t('web_auth_forgot_password')}</Link>
        </p>
        <p className="meta">
          {t('web_auth_first_password')} <Link to="/signin/code">{t('web_auth_get_code')}</Link>
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
