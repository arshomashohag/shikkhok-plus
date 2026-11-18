/**
 * "Did the hub bring you a student?", opened from its inbox item with the
 * owner and the day (60 or 90) the item named. Three replies; the one
 * drawn pressed is only ever one the server accepted, and answering again
 * overwrites. A failed send leaves the last accepted reply as it was and
 * offers Retry (TC-8). The answer is sent as the item's owner, so a centre
 * manager answers for the centre whichever workspace is open.
 */
import { useState } from 'react'
import { useParams } from 'react-router'
import { answerHubFeedback } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { Section, TopBar } from '../../../ui/components'
import { failureText, FailureBanner } from './hubUi'

type Answer = 'yes' | 'not_yet' | 'not_sure'

const ANSWERS: readonly { answer: Answer; key: string }[] = [
  { answer: 'yes', key: 'hub_feedback_yes' },
  { answer: 'not_yet', key: 'hub_feedback_not_yet' },
  { answer: 'not_sure', key: 'hub_feedback_not_sure' },
]

export function HubFeedback() {
  const { t, message } = useT()
  const { ownerId = '', day: rawDay = '' } = useParams()
  const day = rawDay === '60' ? 60 : rawDay === '90' ? 90 : null
  const [saved, setSaved] = useState<Answer | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<{ text: string; retry: Answer | null } | null>(null)

  async function send(answer: Answer) {
    if (day === null) return
    setBusy(true)
    setFailure(null)
    try {
      await answerHubFeedback(ownerId, day, answer)
      setSaved(answer)
    } catch (e) {
      // Offline can be retried; a refusal only when the server says so.
      const retryable = !(e instanceof ApiError) || e.offline || e.retryable
      setFailure({
        text: `${t('hub_feedback_failed')} ${failureText(e, t, message)}`,
        retry: retryable ? answer : null,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <TopBar title={t('hub_feedback_title')} back />
      <Section title={t('hub_feedback_question')}>
        {day !== null ? <p className="meta">{t('hub_feedback_day', String(day))}</p> : null}
        <div className="button-row" role="group" aria-label={t('hub_feedback_question')}>
          {ANSWERS.map(({ answer, key }) => (
            <button
              key={answer}
              type="button"
              className={`btn grow ${saved === answer ? 'btn-primary' : 'btn-outline'}`}
              aria-pressed={saved === answer}
              disabled={busy || day === null}
              onClick={() => void send(answer)}
            >
              {t(key)}
            </button>
          ))}
        </div>
        {saved && !failure ? (
          <div className="banner info" role="status">
            {t('hub_feedback_thanks')}
          </div>
        ) : null}
        {failure ? (
          <FailureBanner
            text={failure.text}
            onRetry={failure.retry ? () => void send(failure.retry as Answer) : undefined}
          />
        ) : null}
      </Section>
    </>
  )
}
