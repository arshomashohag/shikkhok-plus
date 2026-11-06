/**
 * One assigned class: take attendance for the whole roster at once, and
 * write what was taught. Names and marks only; no phone, guardian or fee
 * ever reaches this screen, because the server's schema carries none.
 *
 * A class a manager has moved to another teacher answers CLASS_REASSIGNED,
 * shown as the server's own message; nothing is saved.
 */
import { useState } from 'react'
import { useParams } from 'react-router'
import { readClassRoster, submitClassRoster, writeClassTopic } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Section, Snackbar, TopBar } from '../../ui/components'
import { WarningIcon } from '../../ui/icons'
import { mutationId } from '../teacher/classes/api'
import { absentFrom, marksFrom, type Roster } from './model'

function RosterForm({
  sessionId,
  roster,
  onSaved,
}: {
  sessionId: string
  roster: Roster
  onSaved: () => void
}) {
  const { t, message } = useT()
  const [absent, setAbsent] = useState(() => absentFrom(roster))
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [key] = useState(mutationId)

  async function save() {
    setBusy(true)
    setFailure(null)
    try {
      await submitClassRoster(sessionId, {
        base_attendance_version: roster.attendance_version,
        client_mutation_id: key,
        seats: marksFrom(roster, absent),
      })
      onSaved()
    } catch (e) {
      setFailure(e instanceof ApiError ? message(e.messageKey) : t('error_unexpected'))
    } finally {
      setBusy(false)
    }
  }

  if (roster.seats.length === 0)
    return <EmptyState title={t('my_class_attendance')} body={t('my_class_no_students')} />
  return (
    <>
      <ul className="card flush list">
        {roster.seats.map((seat) => {
          const isAbsent = absent.has(seat.enrollment_id)
          return (
            <li key={seat.enrollment_id}>
              <button
                type="button"
                className="row"
                aria-pressed={!isAbsent}
                disabled={!roster.writable || busy}
                onClick={() =>
                  setAbsent((cur) => {
                    const next = new Set(cur)
                    if (next.has(seat.enrollment_id)) next.delete(seat.enrollment_id)
                    else next.add(seat.enrollment_id)
                    return next
                  })
                }
              >
                <span className="grow">
                  <span className="title">{seat.display_name}</span>
                </span>
                <span className={isAbsent ? 'chip chip-overdue' : 'chip'}>
                  {isAbsent ? t('my_class_absent') : t('my_class_present')}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      {failure ? (
        <div className="banner error" role="alert" style={{ marginTop: 12 }}>
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      {roster.writable ? (
        <div className="button-row">
          <button
            type="button"
            className="btn btn-primary grow"
            disabled={busy}
            onClick={() => void save()}
          >
            {t('my_class_save_attendance')}
          </button>
        </div>
      ) : (
        <p className="meta">{t('my_class_not_writable')}</p>
      )}
    </>
  )
}

function TopicForm({
  sessionId,
  roster,
  onSaved,
}: {
  sessionId: string
  roster: Roster
  onSaved: () => void
}) {
  const { t, message } = useT()
  const [topic, setTopic] = useState(roster.topic ?? '')
  const [version, setVersion] = useState(roster.topic_version)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function save() {
    setBusy(true)
    setFailure(null)
    try {
      const written = await writeClassTopic(sessionId, {
        base_topic_version: version,
        client_mutation_id: mutationId(),
        topic: topic.trim() || null,
        plan: false,
      })
      setVersion(written.topic_version)
      onSaved()
    } catch (e) {
      setFailure(e instanceof ApiError ? message(e.messageKey) : t('error_unexpected'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <div className="field" style={{ marginTop: 0 }}>
        <label htmlFor="mc-topic">{t('my_class_topic_label')}</label>
        <textarea
          id="mc-topic"
          maxLength={2000}
          rows={3}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button
          type="button"
          className="btn btn-tonal grow"
          disabled={busy || !topic.trim()}
          onClick={() => void save()}
        >
          {t('my_class_save_topic')}
        </button>
      </div>
    </div>
  )
}

export function ClassScreen() {
  const { sessionId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(() => readClassRoster(sessionId), [sessionId])
  const [snack, setSnack] = useState<string | null>(null)
  const saved = () => {
    setSnack(t('my_class_saved'))
    reload()
  }

  return (
    <>
      <TopBar title={t('my_class_attendance')} back="/my-classes" />
      {resource.state === 'loading' ? <Loading rows={3} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('my_class_attendance')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' ? (
        <>
          <Section title={t('my_class_attendance')}>
            <RosterForm
              key={resource.data.attendance_version}
              sessionId={sessionId}
              roster={resource.data}
              onSaved={saved}
            />
          </Section>
          <Section title={t('my_class_topic_label')}>
            <TopicForm
              key={resource.data.topic_version}
              sessionId={sessionId}
              roster={resource.data}
              onSaved={saved}
            />
          </Section>
        </>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
