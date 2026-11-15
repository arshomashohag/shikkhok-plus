/**
 * Choose a username before anything else [FR5.2] [FR5.3] [FR5.4].
 *
 * `App` renders this in place of every route while the session is
 * `username-required`: it is not a route, so no typed URL or history
 * entry reaches a screen behind it. It lifts **only on a read**: after a
 * 200, or after `account.username.password_required` (another tab or
 * device chose first), it waits on the session's `reread()` and is
 * unmounted when that read says false. A read still saying true brings
 * it back to Editing with a re-read Retry; a failed read leaves it for
 * the session's blocking error card, which offers Sign out.
 *
 * A changed `me` is acted on only in Rereading [functional-spec W4
 * step 9]: in Saving the gate waits for its own `PUT`, whatever a read
 * started earlier says. The tab-visibility re-read is attached only in
 * Editing [NFR8.6].
 *
 * The client holds no username rule but non-blank [FR11.3]; everything
 * else is the server's answer, shown through its `message_key`.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { checkMyUsername, setMyUsername, type Me } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { useSession } from '../../../session/session'
import { AuthFrame } from '../../auth/AuthFrame'
import { useFailureText } from '../../auth/parts'
import { UsernameField } from '../../auth/username/UsernameField'
import { useUsernameAvailability } from '../../auth/username/useUsernameAvailability'

export type GateState =
  | {
      step: 'editing'
      error: string | null
      field: 'username' | null
      retry: 'save' | 'reread' | null
    }
  | { step: 'saving' }
  | { step: 'rereading' }

const EDITING: GateState = { step: 'editing', error: null, field: null, retry: null }

/** Where a refusal of the choice goes, and whether Retry is offered. */
export function gateRefusal(
  e: unknown,
  text: string,
): { next: 'reread' } | { next: 'editing'; state: GateState } {
  const key = e instanceof ApiError ? e.messageKey : ''
  if (key === 'account.username.password_required') return { next: 'reread' }
  if (key.startsWith('account.username.'))
    return {
      next: 'editing',
      state: { step: 'editing', error: text, field: 'username', retry: null },
    }
  const retryable = e instanceof ApiError && (e.retryable || e.offline)
  return {
    next: 'editing',
    state: { step: 'editing', error: text, field: null, retry: retryable ? 'save' : null },
  }
}

export function ChooseUsernameGate(_props: { me: Me }) {
  const { t } = useT()
  const failure = useFailureText()
  const { reread, signOut } = useSession()
  const [state, setState] = useState<GateState>(EDITING)
  const [username, setUsername] = useState('')
  // Asked as the signed-in account, so a name it released reads available.
  const availability = useUsernameAvailability(checkMyUsername)
  /** The choice last sent, so Retry resends exactly it. */
  const sent = useRef<string | null>(null)
  const mounted = useRef(true)
  const fieldRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    mounted.current = true
    fieldRef.current?.focus()
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    document.title = `${t('choose_username_title')} · ShikkhokPlus`
  }, [t])

  // One quiet re-read per return to the tab, and only while editing: a
  // name chosen in another tab or on Android lifts this tab's gate.
  const editing = state.step === 'editing'
  useEffect(() => {
    if (!editing) return
    const onVisible = () => {
      if (document.visibilityState === 'visible') void reread()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [editing, reread])

  async function rereadAndSee() {
    setState({ step: 'rereading' })
    await reread()
    // Still here: the read said the account still needs a username. Had
    // it said false, or failed, the session has unmounted this gate.
    if (mounted.current)
      setState({ step: 'editing', error: t('error_unexpected'), field: null, retry: 'reread' })
  }

  async function save(choice: string) {
    sent.current = choice
    setState({ step: 'saving' })
    try {
      await setMyUsername(choice, null)
    } catch (e) {
      if (!mounted.current) return
      const outcome = gateRefusal(e, failure(e))
      if (outcome.next === 'editing') {
        setState(outcome.state)
        return
      }
    }
    if (mounted.current) await rereadAndSee()
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (state.step !== 'editing') return
    const choice = username.trim()
    if (!choice) {
      setState({
        step: 'editing',
        error: t('signup_username_required'),
        field: 'username',
        retry: null,
      })
      return
    }
    void save(choice)
  }

  function onUsernameChange(value: string) {
    setUsername(value)
    availability.edited(value)
    // An edit ends the field's refusal; a banner stays until the next try.
    setState((s) => (s.step === 'editing' && s.field === 'username' ? EDITING : s))
  }

  function retry() {
    if (state.step !== 'editing') return
    if (state.retry === 'reread') void rereadAndSee()
    else if (state.retry === 'save' && sent.current !== null) void save(sent.current)
  }

  const busy = state.step !== 'editing'
  const fieldError = state.step === 'editing' && state.field === 'username' ? state.error : null
  const banner = state.step === 'editing' && state.field === null ? state.error : null

  return (
    <AuthFrame>
      <form onSubmit={onSubmit} noValidate data-testid="choose-username-gate">
        <h1>{t('choose_username_title')}</h1>
        <p className="meta">{t('choose_username_body')}</p>
        <UsernameField
          id="gate-username"
          inputRef={fieldRef}
          label={t('signup_username_label')}
          help={t('signup_username_help')}
          value={username}
          onChange={onUsernameChange}
          availability={availability.state}
          error={fieldError}
        />
        {banner ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            <span>{banner}</span>
            {state.step === 'editing' && state.retry ? (
              <button type="button" className="btn btn-text btn-small" onClick={retry}>
                {t('auth_retry')}
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {t('choose_username_continue')}
          </button>
        </div>
        <div className="button-row">
          <button type="button" className="btn btn-text" onClick={signOut}>
            {t('choose_username_sign_out')}
          </button>
        </div>
      </form>
    </AuthFrame>
  )
}
