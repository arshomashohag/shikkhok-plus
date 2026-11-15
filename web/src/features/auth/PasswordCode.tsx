/**
 * The code flow: "Forgot password?", and an account made before passwords
 * getting its first one. A phone number or email address, a one-time code
 * sent to it, then a new password (`ChoosePassword.tsx`), and the person
 * is signed in.
 *
 * The confirmation after "Send code" reads the same for every phone or
 * address, registered or not: the server's answer never reveals whether
 * an account exists [D-33], and neither does this screen.
 *
 * A code sent here also completes a pending sign-up for that number or
 * address, so verify can answer `409 account.username.unavailable` here
 * too. As on sign-up, this screen holds the code in a ref (memory only),
 * shows the Replace step with the plain body — no name was typed here —
 * and retries with the same code [FR2.2] [functional-spec W2].
 */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { issueCode, verifyCode, type Identifier, type VerifyResponse } from '../../api/endpoints'
import { useT } from '../../i18n/i18n'
import { useSession } from '../../session/session'
import { AuthFrame } from './AuthFrame'
import { ChoosePassword, setupFrom, type PasswordSetup } from './ChoosePassword'
import { invalidKey, readIdentifier, shownIdentifier, type IdentifierKind } from './identifier'
import {
  CodeEntry,
  describedBy,
  Field,
  identifierInputProps,
  KindToggle,
  RESEND_AFTER_S,
  useFailureText,
} from './parts'
import { isCodeSpent, isNameTakenMeanwhile, ReplaceUsernameStep } from './ReplaceUsernameStep'

type Step =
  | { step: 'identifier' }
  | {
      step: 'code'
      identifier: Identifier
      /** When the current code was sent (epoch ms), for Resend's pacing. */
      sentAt: number
      /** Bumped when the step is shown again, so the field starts fresh. */
      round: number
      /** Why the step is showing again, after a Replace retry spent the code. */
      error: string | null
    }
  | { step: 'replace'; identifier: Identifier; sentAt: number }
  | { step: 'choose'; setup: PasswordSetup }

export function PasswordCode() {
  const { t } = useT()
  const failure = useFailureText()
  const { signIn } = useSession()
  const [step, setStep] = useState<Step>({ step: 'identifier' })
  // Starts empty: nothing typed on sign-in is handed over in route state,
  // which the browser keeps in history [functional-spec § 1 defect 6].
  const [kind, setKind] = useState<IdentifierKind>('phone')
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  /** The code verify accepted before saying the name was taken. Memory only. */
  const heldCode = useRef<string | null>(null)

  useEffect(() => {
    document.title = `${t('web_auth_code_flow_title')} · ShikkhokPlus`
  }, [t])

  useEffect(
    () => () => {
      heldCode.current = null
    },
    [],
  )

  /** Spend the code; a name taken meanwhile opens Replace instead of failing. */
  async function verify(identifier: Identifier, sentAt: number, code: string) {
    let answer: VerifyResponse
    try {
      answer = await verifyCode(identifier, code)
    } catch (err) {
      if (!isNameTakenMeanwhile(err)) throw err
      heldCode.current = code
      setStep({ step: 'replace', identifier, sentAt })
      return
    }
    setStep({ step: 'choose', setup: setupFrom(answer, identifier) })
  }

  /** The Replace retry: the held code with the new name [W2 steps 5–6]. */
  async function verifyWithReplacement(identifier: Identifier, sentAt: number, username: string) {
    let answer: VerifyResponse
    try {
      answer = await verifyCode(identifier, heldCode.current ?? '', username)
    } catch (err) {
      if (!isCodeSpent(err)) throw err
      heldCode.current = null
      setStep({ step: 'code', identifier, sentAt, round: Date.now(), error: failure(err) })
      return
    }
    heldCode.current = null
    setStep({ step: 'choose', setup: setupFrom(answer, identifier, username) })
  }

  /** Back forgets the held code [W2 step 7]. */
  function backToIdentifier() {
    heldCode.current = null
    setStep({ step: 'identifier' })
    setError(null)
  }

  async function onIdentifier(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNotice(null)
    const identifier = readIdentifier(kind, typed)
    if (!identifier) {
      setError(t(invalidKey(kind)))
      return
    }
    setBusy(true)
    try {
      await issueCode(identifier)
      setStep({ step: 'code', identifier, sentAt: Date.now(), round: 0, error: null })
    } catch (err) {
      setError(failure(err))
    } finally {
      setBusy(false)
    }
  }

  const restart = useCallback(
    (expired: boolean) => {
      setNotice(expired ? t('web_auth_setup_expired_restart') : null)
      setError(null)
      setStep({ step: 'identifier' })
    },
    [t],
  )

  let body
  if (step.step === 'choose') {
    body = (
      <ChoosePassword
        key={step.setup.token}
        setup={step.setup}
        onDone={signIn}
        onRestart={restart}
      />
    )
  } else if (step.step === 'replace') {
    const { identifier, sentAt } = step
    body = (
      <ReplaceUsernameStep
        name={null}
        submit={(username) => verifyWithReplacement(identifier, sentAt, username)}
        onBack={backToIdentifier}
      />
    )
  } else if (step.step === 'code') {
    const { identifier, sentAt, round, error: codeError } = step
    body = (
      <div>
        <h1>{t('auth_code_label')}</h1>
        <p className="meta">
          {t('phone' in identifier ? 'web_auth_code_sent_phone' : 'web_auth_code_sent_email')}{' '}
          <strong>{shownIdentifier(identifier)}</strong>
        </p>
        <CodeEntry
          key={round}
          initialError={codeError}
          resendAvailableAt={sentAt + RESEND_AFTER_S * 1000}
          verify={(code) => verify(identifier, sentAt, code)}
          resend={async () => {
            await issueCode(identifier)
            setStep((s) => (s.step === 'code' ? { ...s, sentAt: Date.now() } : s))
          }}
        >
          <button type="button" className="btn btn-text" onClick={backToIdentifier}>
            {t('auth_change')}
          </button>
        </CodeEntry>
      </div>
    )
  } else {
    body = (
      <form onSubmit={onIdentifier} noValidate>
        <h1>{t('web_auth_code_flow_title')}</h1>
        <p className="meta">{t('web_auth_code_flow_body')}</p>
        {notice ? (
          <div className="banner info" role="status" style={{ marginTop: 16 }}>
            {notice}
          </div>
        ) : null}
        <KindToggle
          kind={kind}
          onKind={(k) => {
            setKind(k)
            setTyped('')
            setError(null)
          }}
        />
        <Field
          id="identifier"
          label={t(kind === 'phone' ? 'auth_phone_label' : 'web_auth_email_label')}
          error={error}
        >
          <input
            id="identifier"
            name="username"
            {...identifierInputProps(kind, 'username')}
            placeholder={kind === 'phone' ? t('auth_phone_hint') : undefined}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy('identifier', false, Boolean(error))}
            autoFocus
          />
        </Field>
        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {busy ? t('auth_sending') : t('auth_request_code')}
          </button>
        </div>
        <p className="meta" style={{ marginTop: 24 }}>
          <Link to="/signin">{t('web_auth_back_to_signin')}</Link>
        </p>
      </form>
    )
  }
  return <AuthFrame>{body}</AuthFrame>
}
