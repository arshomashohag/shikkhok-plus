/**
 * Settings → Username: the current name, and changing it [FR7.1]
 * [FR7.2] [FR7.5] [functional-spec W5].
 *
 * The client never decides whether a rename is allowed now [FR11.3]
 * [NFR3.13]: Change is always offered, and the server's answer decides.
 * After a change, or a refusal that says when, the next allowed date is
 * shown, formatted here with `formatDateTime` — never through
 * `MESSAGE_ARGS`, which would insert the raw instant. The hint asks as
 * the signed-in account, so a name this account released reads
 * available. No session ends on a rename [FR7.5]; the session re-reads,
 * so the Settings row shows the new name.
 *
 * The password lives in component state, is cleared on every answer and
 * dropped when the screen unmounts. Retry resends the exact request,
 * which is kept in memory only for that.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { checkMyUsername, setMyUsername } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatDateTime } from '../../../core/format'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { TopBar } from '../../../ui/components'
import { describedBy, Field, PasswordInput, useFailureText } from '../../auth/parts'
import { UsernameField } from '../../auth/username/UsernameField'
import { useUsernameAvailability } from '../../auth/username/useUsernameAvailability'
import { securityPaths } from '../security/paths'

export type UsernameState =
  | { step: 'viewing'; notice: string | null }
  | {
      step: 'editing'
      error: string | null
      field: 'username' | 'password' | null
      retryable: boolean
      /** The banner links to setting a password. */
      needsPassword: boolean
    }
  | { step: 'saving' }

const EDITING: Extract<UsernameState, { step: 'editing' }> = {
  step: 'editing',
  error: null,
  field: null,
  retryable: false,
  needsPassword: false,
}

/**
 * Where a refusal of the change goes [functional-spec W5 step 5].
 *
 * @param text The refusal's own string
 * @param when The formatted `details.next_change_at`, when the server sent one
 */
export function renameRefusal(
  e: unknown,
  text: string,
  when: (iso: string) => string,
  t: (key: string, ...args: string[]) => string,
): Extract<UsernameState, { step: 'editing' }> {
  const error = e instanceof ApiError ? e : null
  const key = error?.messageKey ?? ''
  const base = { step: 'editing' as const, field: null, retryable: false, needsPassword: false }
  if (key === 'account.username.change_too_soon') {
    const at = error?.details?.next_change_at
    return { ...base, error: at ? t('account_username_change_too_soon_on', when(at)) : text }
  }
  if (key === 'account.username.password_required')
    return { ...base, error: text, needsPassword: true }
  if (key === 'auth.password.current_wrong') return { ...base, error: text, field: 'password' }
  if (key.startsWith('account.username.')) return { ...base, error: text, field: 'username' }
  const retryable =
    error !== null && (error.offline || (error.retryable && key !== 'auth.lookup.too_many'))
  return { ...base, error: text, retryable }
}

export function UsernameScreen() {
  const { t, lang } = useT()
  const failure = useFailureText()
  const { session, refresh } = useReadySession()
  const [state, setState] = useState<UsernameState>({ step: 'viewing', notice: null })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  /** The request last sent, for Retry only; memory, never storage. */
  const sent = useRef<{ username: string; password: string } | null>(null)
  const availability = useUsernameAvailability(checkMyUsername)
  const when = (iso: string) => formatDateTime(iso, lang, true)

  useEffect(
    () => () => {
      sent.current = null
    },
    [],
  )

  async function save(request: { username: string; password: string }) {
    sent.current = request
    setState({ step: 'saving' })
    try {
      const changed = await setMyUsername(request.username, request.password)
      sent.current = null
      setPassword('')
      setUsername('')
      refresh()
      setState({
        step: 'viewing',
        notice: changed.next_change_at
          ? t('username_changed_on', when(changed.next_change_at))
          : t('username_changed'),
      })
    } catch (e) {
      setPassword('')
      setState(renameRefusal(e, failure(e), when, t))
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (state.step !== 'editing') return
    const choice = username.trim()
    if (!choice) {
      setState({ ...EDITING, error: t('signup_username_required'), field: 'username' })
      return
    }
    if (!password) {
      setState({ ...EDITING, error: t('web_auth_password_required'), field: 'password' })
      return
    }
    void save({ username: choice, password })
  }

  function cancel() {
    sent.current = null
    setPassword('')
    setUsername('')
    setState({ step: 'viewing', notice: null })
  }

  function onUsernameChange(value: string) {
    setUsername(value)
    availability.edited(value)
  }

  const title = t('username_title')
  const current = session.me.username ?? null

  if (state.step === 'viewing')
    return (
      <>
        <TopBar title={title} back="/settings" />
        {state.notice ? (
          <div className="banner" role="status" style={{ marginBottom: 12 }}>
            {state.notice}
          </div>
        ) : null}
        <div className="card">
          <p className="meta" style={{ marginTop: 0 }}>
            {t('username_current_label')}
          </p>
          <p className="title" data-testid="username-current">
            {current ?? t('more_username_choose')}
          </p>
          <div className="button-row">
            <button type="button" className="btn btn-outline" onClick={() => setState(EDITING)}>
              {t('username_change')}
            </button>
          </div>
        </div>
      </>
    )

  const busy = state.step === 'saving'
  const editing = state.step === 'editing' ? state : null
  const usernameError = editing?.field === 'username' ? editing.error : null
  const passwordError = editing?.field === 'password' ? editing.error : null
  const banner = editing && editing.field === null ? editing.error : null

  return (
    <>
      <TopBar title={title} back="/settings" />
      <form className="card" onSubmit={onSubmit} noValidate>
        <UsernameField
          id="new-username"
          label={t('username_new_label')}
          value={username}
          onChange={onUsernameChange}
          availability={availability.state}
          error={usernameError}
          disabled={busy}
        />
        <Field id="rename-password" label={t('web_password_current')} error={passwordError}>
          <PasswordInput
            id="rename-password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            invalid={Boolean(passwordError)}
            describedBy={describedBy('rename-password', false, Boolean(passwordError))}
            disabled={busy}
          />
        </Field>
        <p className="help">{t('username_rule_note')}</p>
        {banner ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            <span>
              {banner}
              {editing?.needsPassword ? (
                <>
                  {' '}
                  <Link to={securityPaths.password()}>{t('contacts_set_password')}</Link>
                </>
              ) : null}
            </span>
            {editing?.retryable && sent.current ? (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() => sent.current && void save(sent.current)}
              >
                {t('auth_retry')}
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="button-row">
          <button type="button" className="btn btn-outline" disabled={busy} onClick={cancel}>
            {t('action_cancel')}
          </button>
          <button type="submit" className="btn btn-primary grow" disabled={busy}>
            {t('username_save')}
          </button>
        </div>
      </form>
    </>
  )
}
