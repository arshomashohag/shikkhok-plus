/**
 * The code flow: "Forgot password?", and an account made before passwords
 * getting its first one. A phone number or email address, a one-time code
 * sent to it, then a new password (`ChoosePassword.tsx`), and the person
 * is signed in.
 *
 * The confirmation after "Send code" reads the same for every phone or
 * address, registered or not: the server's answer never reveals whether
 * an account exists [D-33], and neither does this screen.
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router'
import { issueCode, verifyCode, type Identifier } from '../../api/endpoints'
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
  useFailureText,
} from './parts'

type Step =
  | { step: 'identifier' }
  | { step: 'code'; identifier: Identifier }
  | { step: 'choose'; setup: PasswordSetup }

/** What the sign-in screen hands over, so nothing is typed twice. */
export interface CodeFlowEntry {
  kind?: IdentifierKind
  typed?: string
}

export function PasswordCode() {
  const { t } = useT()
  const failure = useFailureText()
  const { signIn } = useSession()
  const entry = (useLocation().state as CodeFlowEntry | null) ?? {}
  const [step, setStep] = useState<Step>({ step: 'identifier' })
  const [kind, setKind] = useState<IdentifierKind>(entry.kind ?? 'phone')
  const [typed, setTyped] = useState(entry.typed ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    document.title = `${t('web_auth_code_flow_title')} · ShikkhokPlus`
  }, [t])

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
      setStep({ step: 'code', identifier })
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
  } else if (step.step === 'code') {
    const { identifier } = step
    body = (
      <div>
        <h1>{t('auth_code_label')}</h1>
        <p className="meta">
          {t('phone' in identifier ? 'web_auth_code_sent_phone' : 'web_auth_code_sent_email')}{' '}
          <strong>{shownIdentifier(identifier)}</strong>
        </p>
        <CodeEntry
          verify={async (code) => {
            const answer = await verifyCode(identifier, code)
            setStep({ step: 'choose', setup: setupFrom(answer, identifier) })
          }}
          resend={async () => {
            await issueCode(identifier)
          }}
        >
          <button
            type="button"
            className="btn btn-text"
            onClick={() => {
              setStep({ step: 'identifier' })
              setError(null)
            }}
          >
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
