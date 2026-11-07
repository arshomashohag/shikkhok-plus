/**
 * Ask a question: a subject and the question itself, each showing its
 * limit, under a reminder to leave children's details out. Sending needs
 * a connection; a failure keeps what was typed and offers Try again when
 * the server says it can help (asking too many questions in a day does
 * not).
 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useT } from '../../i18n/i18n'
import { TopBar } from '../../ui/components'
import { WarningIcon } from '../../ui/icons'
import { askQuestion } from './api'
import { CountedField, writeErrorText } from './Conversation'
import { BODY_MAX, fieldProblem, newQuestion, SUBJECT_MAX } from './mappers'
import { helpPaths } from './paths'
import './help.css'

export function NewQuestion() {
  const { t, message } = useT()
  const navigate = useNavigate()
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ text: string; retryable: boolean } | null>(null)

  async function send() {
    setTried(true)
    if (fieldProblem(subject, SUBJECT_MAX) || fieldProblem(body, BODY_MAX)) return
    setBusy(true)
    setError(null)
    try {
      const created = await askQuestion(newQuestion(subject, body))
      navigate(helpPaths.ticket(created.ticket.ticket_id), {
        replace: true,
        state: { sent: true },
      })
    } catch (e) {
      setError(writeErrorText(e, t('web_help_send_offline'), message))
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send()
  }

  return (
    <>
      <TopBar title={t('help_ask')} back={helpPaths.list()} />
      <form className="card form-page" onSubmit={onSubmit} noValidate>
        <div className="banner" role="note">
          <WarningIcon />
          <span>{t('help_privacy_hint')}</span>
        </div>
        <CountedField
          label={t('help_subject_label')}
          help={t('help_subject_placeholder')}
          value={subject}
          onChange={setSubject}
          max={SUBJECT_MAX}
          showError={tried}
          autoFocus
        />
        <CountedField
          label={t('help_body_label')}
          help={t('web_help_body_help')}
          value={body}
          onChange={setBody}
          max={BODY_MAX}
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
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {busy ? t('help_sending') : t('help_send')}
          </button>
        </div>
      </form>
    </>
  )
}
