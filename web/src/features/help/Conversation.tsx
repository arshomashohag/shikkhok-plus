/**
 * The pieces a help thread is drawn from, shared by the person who asked
 * (`HelpThread`) and by support (the admin app, `src/admin`): the messages as
 * bubbles, a text field that shows its limit, and the reply box.
 *
 * A reply is a write, so it needs a connection [D-9]: a failed send keeps
 * what was typed, says why, and offers Try again when the server says
 * trying again can help.
 */
import { useId, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/errors'
import { ago, formatDateTime } from '../../core/format'
import { useT } from '../../i18n/i18n'
import { fieldProblem, textLength, type HelpMessage } from './mappers'
import './help.css'

/** The words for a failed write: offline, or the message the server named. */
export function writeErrorText(
  e: unknown,
  offlineText: string,
  message: (key: string) => string,
): { text: string; retryable: boolean } {
  if (e instanceof ApiError) {
    return e.offline
      ? { text: offlineText, retryable: true }
      : { text: message(e.messageKey), retryable: e.retryable }
  }
  return { text: message('error.unexpected'), retryable: true }
}

/**
 * The thread, oldest first. The viewer's own messages sit on the right.
 *
 * @param mine Whose messages are the viewer's own
 * @param requesterLabel What to call the person who asked
 */
export function MessageList({
  messages,
  mine,
  requesterLabel,
}: {
  messages: HelpMessage[]
  mine: 'requester' | 'support'
  requesterLabel: string
}) {
  const { t, lang } = useT()
  const now = new Date()
  return (
    <ol className="help-thread" aria-label={t('web_help_messages')}>
      {messages.map((m) => {
        const own = m.fromSupport === (mine === 'support')
        return (
          <li key={m.id} className={own ? 'help-bubble own' : 'help-bubble'}>
            <span className={m.fromSupport ? 'help-author support' : 'help-author'}>
              {m.fromSupport ? t('help_from_support') : requesterLabel}
            </span>
            <p className="help-body">{m.body}</p>
            <time className="meta" dateTime={m.sentAt} title={formatDateTime(m.sentAt, lang, true)}>
              {ago(m.sentAt, now, t)} · {formatDateTime(m.sentAt, lang)}
            </time>
          </li>
        )
      })}
    </ol>
  )
}

/** A text field that shows how much of its limit is used, and why it is refused. */
export function CountedField({
  label,
  help,
  value,
  onChange,
  max,
  showError,
  multiline,
  autoFocus,
}: {
  label: string
  help?: string
  value: string
  onChange: (value: string) => void
  max: number
  showError: boolean
  multiline?: boolean
  autoFocus?: boolean
}) {
  const { t } = useT()
  const id = useId()
  const problem = showError ? fieldProblem(value, max) : null
  const used = textLength(value)
  const errorText =
    problem === 'required'
      ? t('web_help_required')
      : problem === 'too_long'
        ? t('web_help_too_long', max)
        : null
  const describedBy = [help ? `${id}-help` : '', `${id}-count`, errorText ? `${id}-error` : '']
    .filter(Boolean)
    .join(' ')
  const common = {
    id,
    value,
    autoFocus,
    onChange: (e: { target: { value: string } }) => onChange(e.target.value),
    'aria-invalid': errorText ? true : undefined,
    'aria-describedby': describedBy,
  }
  return (
    <div className="field help-field">
      <label htmlFor={id}>{label}</label>
      {multiline ? <textarea rows={6} {...common} /> : <input {...common} />}
      <div className="help-field-foot">
        {help ? (
          <span id={`${id}-help`} className="help grow">
            {help}
          </span>
        ) : (
          <span className="grow" />
        )}
        <span
          id={`${id}-count`}
          className={used > max ? 'help-count over' : 'help-count'}
          aria-live="off"
        >
          {t('help_char_count', used, max)}
        </span>
      </div>
      {errorText ? (
        <span id={`${id}-error`} className="field-error">
          {errorText}
        </span>
      ) : null}
    </div>
  )
}

/**
 * Write and send a reply. What was typed stays until the server accepts
 * it; `onSend` throws on failure.
 */
export function ReplyBox({
  label,
  sendLabel,
  offlineText,
  max,
  onSend,
}: {
  label: string
  sendLabel: string
  offlineText: string
  max: number
  onSend: (body: string) => Promise<void>
}) {
  const { t, message } = useT()
  const [text, setText] = useState('')
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ text: string; retryable: boolean } | null>(null)

  async function send() {
    setTried(true)
    if (fieldProblem(text, max)) return
    setBusy(true)
    setError(null)
    try {
      await onSend(text.trim())
      setText('')
      setTried(false)
    } catch (e) {
      setError(writeErrorText(e, offlineText, message))
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send()
  }

  return (
    <form className="card help-reply" onSubmit={onSubmit} noValidate>
      <CountedField
        label={label}
        value={text}
        onChange={setText}
        max={max}
        showError={tried}
        multiline
      />
      {error ? (
        <div className="banner error help-error" role="alert">
          <span className="grow">{error.text}</span>
          {error.retryable ? (
            <button
              type="button"
              className="btn btn-outline btn-small"
              disabled={busy}
              onClick={() => void send()}
            >
              {t('auth_retry')}
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="button-row help-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? t('help_sending') : sendLabel}
        </button>
      </div>
    </form>
  )
}
