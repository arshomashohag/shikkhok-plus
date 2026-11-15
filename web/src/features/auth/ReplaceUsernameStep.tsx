/**
 * Choose another username, after the code was accepted but the name was
 * taken meanwhile (`409 account.username.unavailable`) [FR2.2]
 * [functional-spec W2].
 *
 * Shared by sign-up and the code flow, and rendered by them as a
 * **sibling** of `CodeEntry`: the owning screen holds the step switch,
 * the code (in a ref, memory only) and when it was sent. This step only
 * takes a replacement name and hands it to `submit`, which retries the
 * verify with the same code.
 *
 * It names only the person's own typed username (sign-up), or no name
 * (the code flow), and shows nothing from the response beyond its key
 * [NFR1.4]. A refusal of the name lands under the field; a 429 in the
 * banner with Continue still offered; no connection in the banner with
 * Retry, which resends the same request.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { checkUsername } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { useFailureText } from './parts'
import { UsernameField } from './username/UsernameField'
import { useUsernameAvailability } from './username/useUsernameAvailability'

/** The verify answer that opens this step instead of failing the code. */
export function isNameTakenMeanwhile(e: unknown): boolean {
  return e instanceof ApiError && e.messageKey === 'account.username.unavailable'
}

/**
 * Refusals of the held code on the Replace retry. The owner forgets the
 * code and shows the code step again, with this refusal's message and
 * the original send's Resend pacing [functional-spec W2 step 6].
 */
const SPENT_CODE = new Set(['auth.otp.expired', 'auth.otp.no_tries_left', 'auth.otp.not_valid'])

export function isCodeSpent(e: unknown): e is ApiError {
  return e instanceof ApiError && SPENT_CODE.has(e.messageKey)
}

interface Failure {
  text: string
  field: boolean
  retry: boolean
}

export function ReplaceUsernameStep({
  name,
  submit,
  onBack,
}: {
  /** The username typed at sign-up, or null in the code flow. */
  name: string | null
  /** Retries the verify with the held code and this replacement. */
  submit: (username: string) => Promise<void>
  onBack: () => void
}) {
  const { t } = useT()
  const failure = useFailureText()
  const [username, setUsername] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<Failure | null>(null)
  const sent = useRef<string | null>(null)
  const fieldRef = useRef<HTMLInputElement>(null)
  const mounted = useRef(true)
  const availability = useUsernameAvailability(checkUsername)

  useEffect(() => {
    mounted.current = true
    fieldRef.current?.focus()
    return () => {
      mounted.current = false
    }
  }, [])

  async function send(choice: string) {
    sent.current = choice
    setBusy(true)
    setProblem(null)
    try {
      await submit(choice)
    } catch (e) {
      if (!mounted.current) return
      const key = e instanceof ApiError ? e.messageKey : ''
      setProblem({
        text: failure(e),
        field: key.startsWith('account.username.'),
        retry: e instanceof ApiError && e.offline,
      })
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const choice = username.trim()
    if (!choice) {
      setProblem({ text: t('signup_username_required'), field: true, retry: false })
      return
    }
    void send(choice)
  }

  function onUsernameChange(value: string) {
    setUsername(value)
    availability.edited(value)
    setProblem((p) => (p?.field ? null : p))
  }

  return (
    <form onSubmit={onSubmit} noValidate data-testid="replace-username">
      <h1>{t('auth_replace_username_title')}</h1>
      <p className="meta" data-testid="replace-username-body">
        {name === null
          ? t('web_auth_replace_username_body_plain')
          : t('auth_replace_username_body', name)}
      </p>
      <UsernameField
        id="replace-username"
        inputRef={fieldRef}
        label={t('signup_username_label')}
        help={t('signup_username_help')}
        value={username}
        onChange={onUsernameChange}
        availability={availability.state}
        error={problem?.field ? problem.text : null}
        disabled={busy}
      />
      {problem && !problem.field ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          <span>{problem.text}</span>
          {problem.retry && sent.current !== null ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              onClick={() => void send(sent.current ?? '')}
            >
              {t('auth_retry')}
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="button-row">
        <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
          {t('auth_replace_username_continue')}
        </button>
        <button type="button" className="btn btn-text" disabled={busy} onClick={onBack}>
          {t('web_auth_signup_back')}
        </button>
      </div>
    </form>
  )
}
