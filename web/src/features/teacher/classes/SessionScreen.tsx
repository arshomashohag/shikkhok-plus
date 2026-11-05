/**
 * One class: T2 "Record class" (subject, what was covered, notes and
 * attendance), the plan before it starts, or a read-only view — whichever
 * the server's `recordable` / `plannable` flags call for, as Android's
 * ClassTapRouter decides. Also moving and cancelling a scheduled class.
 *
 * **A write needs a connection** (D-9 for the web): there is no queue. A
 * failed save shows the server's message and Save again resends the same
 * write with the same `client_mutation_id`, so the server replays it
 * rather than applying it twice.
 *
 * **Conflicts are the teacher's call, never silently resolved.** If the
 * topic or the attendance changed elsewhere since this screen loaded, the
 * server refuses with a version conflict and nothing is written; this
 * screen shows what the record says now beside what the teacher entered,
 * and offers "Use what I recorded" or "Keep the current record".
 */
import { useCallback, useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router'
import { listBatches, type Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatClock, formatLongDay } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  ErrorCard,
  Loading,
  Section,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { paths } from '../paths'
import {
  cancelSession,
  mutationId,
  readAttendance,
  readBatchSessions,
  readCalendar,
  readSession,
  rescheduleSession,
  setSessionSubject,
  submitAttendance,
  writeTopic,
} from './api'
import {
  classTarget,
  lastTopic,
  mapMonth,
  mapSeats,
  monthOf,
  parseConflictState,
  type ClassItem,
  type ClassState,
  type Seat,
} from './mappers'

export const TOPIC_CONFLICT = 'TOPIC_VERSION_CONFLICT'
export const ATTENDANCE_CONFLICT = 'ATTENDANCE_VERSION_CONFLICT'
export const CLASS_STARTED = 'CLASS_STARTED'
const TEXT_MAX = 2000

type Subject = Schemas['SubjectOption']

interface Loaded {
  session: Schemas['SessionResponse']
  item: ClassItem
  batchName: string | null
  subjects: Subject[]
  roster: Schemas['SessionRosterResponse'] | null
  suggestion: string | null
}

function stateFromStatus(s: Schemas['SessionResponse']): ClassState {
  if (s.status === 'cancelled') return 'cancelled'
  if (s.status === 'held') return 'taken'
  return 'upcoming'
}

async function load(batchId: string, sessionId: string): Promise<Loaded> {
  const session = await readSession(sessionId)
  const ym = monthOf(session.date)
  const [calendar, batches] = await Promise.all([
    readCalendar(batchId, ym.year, ym.month),
    listBatches(),
  ])
  const batch = batches.find((b) => b.id === batchId)
  // The calendar carries the flags (recordable, plannable) and the notes
  // the class endpoint does not. A class missing from it opens read-only.
  const item: ClassItem = mapMonth(calendar)
    .days.get(session.date)
    ?.classes.find((c) => c.sessionId === sessionId) ?? {
    sessionId,
    date: session.date,
    startTime: session.start_time,
    endTime: session.end_time ?? null,
    subjectName: session.subject_name ?? null,
    state: stateFromStatus(session),
    topic: session.topic ?? null,
    notes: null,
    plannable: false,
    recordable: false,
    topicVersion: session.topic_version,
    attendanceVersion: session.attendance_version,
  }
  let roster: Schemas['SessionRosterResponse'] | null = null
  let suggestion: string | null = null
  if (classTarget(item) === 'record') {
    const [r, sessions] = await Promise.all([readAttendance(sessionId), readBatchSessions(batchId)])
    roster = r
    suggestion = lastTopic(sessions, sessionId)
  }
  return {
    session,
    item,
    batchName: batch?.name ?? null,
    subjects: batch?.subject_options ?? [],
    roster,
    suggestion,
  }
}

export function SessionScreen() {
  const { batchId = '', sessionId = '' } = useParams()
  const { t, lang } = useT()
  const [generation, setGeneration] = useState(0)
  const [snack, setSnack] = useState<string | null>(null)
  const { resource, reload } = useResource(() => load(batchId, sessionId), [batchId, sessionId])
  const back = paths.batch(batchId, 'classes')
  const done = useCallback(
    (text: string) => {
      setSnack(text)
      setGeneration((g) => g + 1)
      reload()
    },
    [reload],
  )

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('classread_title')} back={back} />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('classread_title')} back={back} />
        <ErrorCard title={t('web_classes_not_found')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const data = resource.data
  const { item, session } = data
  const target = classTarget(item)
  const clock = formatClock(item.startTime, lang)
  const when =
    item.state === 'today'
      ? t('student_today_at', clock)
      : `${formatLongDay(item.date, lang)} · ${clock}`
  const subtitle = [item.subjectName, data.batchName, when].filter(Boolean).join(' · ')
  const title =
    target === 'record'
      ? t('record_title')
      : target === 'plan'
        ? item.state === 'today'
          ? t('classday_title_today')
          : t('classplan_topics')
        : t('classread_title')
  // Never decide on stale data: a failed refresh hides the forms' buttons.
  const fresh = resource.error === null
  const key = `${sessionId}:${generation}`

  return (
    <>
      <TopBar title={title} subtitle={subtitle} back={back} />
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      {target === 'record' && data.roster ? (
        <RecordForm key={key} data={data} roster={data.roster} fresh={fresh} onSaved={done} />
      ) : null}
      {target === 'plan' ? <PlanForm key={key} data={data} fresh={fresh} onSaved={done} /> : null}
      {target === 'read' ? (
        <ReadView item={item} cancelled={session.status === 'cancelled'} />
      ) : null}
      {session.status === 'scheduled' && fresh ? (
        <ManageClass session={session} onChanged={done} />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}

// --------------------------------------------------------------- record

type Conflict =
  | { kind: 'topic'; theirs: string; mineTopic: string; mineNotes: string; currentVersion: number }
  | { kind: 'attendance'; theirs: Map<string, boolean>; mine: Seat[]; currentVersion: number }

function SubjectPicker({
  subjects,
  value,
  onChange,
}: {
  subjects: Subject[]
  value: string | null
  onChange: (id: string) => void
}) {
  const { t } = useT()
  if (subjects.length === 0) return null
  if (subjects.length === 1) {
    return <p className="meta">{t('record_only_subject', subjects[0]?.name ?? '')}</p>
  }
  return (
    <fieldset className="field">
      <legend>{t('class_subject_label')}</legend>
      <div className="choice-pills" role="group">
        {subjects.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-pressed={value === s.id}
            onClick={() => onChange(s.id)}
          >
            {s.name}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

function TextArea({
  id,
  label,
  value,
  onChange,
  help,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  help?: string
}) {
  const { t } = useT()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        value={value}
        maxLength={TEXT_MAX}
        onChange={(e) => onChange(e.target.value.slice(0, TEXT_MAX))}
      />
      <span className="help">
        {help ? `${help} · ` : ''}
        {t('class_text_counter', value.length, TEXT_MAX)}
      </span>
    </div>
  )
}

function errorText(e: unknown, message: (k: string) => string, t: (k: string) => string): string {
  return e instanceof ApiError ? message(e.messageKey) : t('error_unexpected')
}

function RecordForm({
  data,
  roster,
  fresh,
  onSaved,
}: {
  data: Loaded
  roster: Schemas['SessionRosterResponse']
  fresh: boolean
  onSaved: (text: string) => void
}) {
  const { t, message } = useT()
  const { item, subjects } = data
  const [subjectId, setSubjectId] = useState<string | null>(
    () => subjects.find((s) => s.name === item.subjectName)?.id ?? null,
  )
  const [topic, setTopic] = useState(item.topic ?? '')
  const [notes, setNotes] = useState(item.notes ?? '')
  const [seats, setSeats] = useState<Seat[]>(() => mapSeats(roster))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState<Conflict | null>(null)
  // Versions and ids that survive a failed attempt, so a retry replays.
  const topicVersion = useRef(item.topicVersion)
  const attendanceVersion = useRef(roster.attendance_version)
  const subjectName = useRef(item.subjectName)
  const topicMid = useRef<string | null>(null)
  const attendanceMid = useRef<string | null>(null)
  const topicDone = useRef(false)

  const editTopic = (v: string) => {
    setTopic(v)
    topicMid.current = null
    topicDone.current = false
  }
  const editNotes = (v: string) => {
    setNotes(v)
    topicMid.current = null
    topicDone.current = false
  }
  const editSeats = (next: Seat[]) => {
    setSeats(next)
    attendanceMid.current = null
  }

  async function sendTopic(base: number, text: string, note: string): Promise<boolean> {
    topicMid.current ??= mutationId()
    try {
      const r = await writeTopic(item.sessionId, {
        base_topic_version: base,
        client_mutation_id: topicMid.current,
        topic: text,
        notes: note,
        plan: false,
      })
      topicVersion.current = r.topic_version
      topicMid.current = null
      topicDone.current = true
      return true
    } catch (e) {
      if (e instanceof ApiError && e.code === TOPIC_CONFLICT) {
        topicMid.current = null
        const now = await readSession(item.sessionId).catch(() => null)
        setConflict({
          kind: 'topic',
          theirs: now?.topic ?? '',
          mineTopic: text,
          mineNotes: note,
          currentVersion: now?.topic_version ?? Number(e.details?.current_version ?? base),
        })
      } else {
        setError(errorText(e, message, t))
      }
      return false
    }
  }

  async function sendAttendance(base: number, marks: Seat[]): Promise<boolean> {
    attendanceMid.current ??= mutationId()
    try {
      const r = await submitAttendance(item.sessionId, {
        base_attendance_version: base,
        client_mutation_id: attendanceMid.current,
        composed_at: new Date().toISOString(),
        seats: marks.map((s) => ({ enrollment_id: s.enrollmentId, present: s.present })),
      })
      attendanceVersion.current = r.attendance_version
      attendanceMid.current = null
      return true
    } catch (e) {
      if (e instanceof ApiError && e.code === ATTENDANCE_CONFLICT) {
        attendanceMid.current = null
        setConflict({
          kind: 'attendance',
          theirs: parseConflictState(e.details?.current_state),
          mine: marks,
          currentVersion: Number(e.details?.current_version ?? base),
        })
      } else {
        setError(errorText(e, message, t))
      }
      return false
    }
  }

  async function save(e?: FormEvent) {
    e?.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    let ok = true
    // 1. The subject, if a different one was chosen (as ClassSubjects.saveIfChanged).
    const chosen = subjects.find((s) => s.id === subjectId)
    if (chosen && chosen.name !== subjectName.current) {
      try {
        await setSessionSubject(item.sessionId, chosen.id)
        subjectName.current = chosen.name
      } catch (err) {
        setError(errorText(err, message, t))
        ok = false
      }
    }
    // 2. The topic, which also marks the class held.
    if (ok && !topicDone.current)
      ok = await sendTopic(topicVersion.current, topic.trim(), notes.trim())
    // 3. Attendance, where the class takes it.
    if (ok && roster.writable) ok = await sendAttendance(attendanceVersion.current, seats)
    setBusy(false)
    if (ok) onSaved(t('web_classes_saved'))
  }

  async function resolve(useMine: boolean) {
    if (!conflict) return
    setBusy(true)
    setError(null)
    const c = conflict
    setConflict(null)
    if (c.kind === 'topic') {
      if (useMine) {
        if (!(await sendTopic(c.currentVersion, c.mineTopic, c.mineNotes))) return setBusy(false)
      } else {
        topicVersion.current = c.currentVersion
        topicDone.current = true
        setTopic(c.theirs)
      }
      // The topic is settled either way; finish with attendance.
      const ok = roster.writable ? await sendAttendance(attendanceVersion.current, seats) : true
      setBusy(false)
      if (ok) onSaved(t('web_classes_saved'))
    } else {
      attendanceVersion.current = c.currentVersion
      if (useMine) {
        const ok = await sendAttendance(c.currentVersion, c.mine)
        setBusy(false)
        if (ok) onSaved(t('classday_attendance_saved'))
      } else {
        setSeats(seats.map((s) => ({ ...s, present: c.theirs.get(s.enrollmentId) ?? s.present })))
        setBusy(false)
        onSaved(t('web_classes_nothing_changed'))
      }
    }
  }

  return (
    <form onSubmit={save} noValidate>
      <div className="card">
        <SubjectPicker subjects={subjects} value={subjectId} onChange={setSubjectId} />
        <TextArea
          id="rc-topic"
          label={t('record_question')}
          value={topic}
          onChange={editTopic}
          help={data.suggestion ? undefined : t('record_help')}
        />
        {data.suggestion && !topic.trim() ? (
          <button
            type="button"
            className="suggestion"
            onClick={() => editTopic(data.suggestion ?? '')}
          >
            {t('record_continue', data.suggestion)}
          </button>
        ) : null}
        <TextArea id="rc-notes" label={t('classday_notes')} value={notes} onChange={editNotes} />
      </div>

      <Section
        title={t('classday_attendance', seats.length)}
        aside={
          roster.writable && seats.some((s) => !s.present) ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              onClick={() => editSeats(seats.map((s) => ({ ...s, present: true })))}
            >
              {t('web_classes_all_present')}
            </button>
          ) : null
        }
      >
        {!roster.writable ? (
          <div className="card meta">{t('attendance_read_only')}</div>
        ) : seats.length === 0 ? (
          <div className="card meta">{t('roster_empty')}</div>
        ) : (
          <ul className="card flush list">
            {seats.map((s, i) => (
              <li key={s.enrollmentId} className="row" style={{ minHeight: 64 }}>
                <span className="meta" style={{ width: 24 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="grow title" id={`seat-${s.enrollmentId}`}>
                  {s.displayName}
                </span>
                <span
                  className="seat-toggle"
                  role="group"
                  aria-labelledby={`seat-${s.enrollmentId}`}
                >
                  {([true, false] as const).map((present) => (
                    <button
                      key={String(present)}
                      type="button"
                      className={present ? 'present' : 'absent'}
                      aria-pressed={s.present === present}
                      onClick={() =>
                        editSeats(
                          seats.map((x) =>
                            x.enrollmentId === s.enrollmentId ? { ...x, present } : x,
                          ),
                        )
                      }
                    >
                      {t(present ? 'attendance_present' : 'attendance_absent')}
                    </button>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {conflict ? (
        <ConflictPanel conflict={conflict} seats={seats} busy={busy} onResolve={resolve} />
      ) : null}
      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}
      {fresh && !conflict ? (
        <div className="action-bar">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {t('classday_save')}
          </button>
        </div>
      ) : null}
    </form>
  )
}

function ConflictPanel({
  conflict,
  seats,
  busy,
  onResolve,
}: {
  conflict: Conflict
  seats: Seat[]
  busy: boolean
  onResolve: (useMine: boolean) => void
}) {
  const { t } = useT()
  const mark = (present: boolean | undefined) =>
    present === undefined
      ? t('conflict_seat_absent')
      : t(present ? 'attendance_present' : 'attendance_absent')
  return (
    <div className="card error" role="alert" style={{ marginTop: 16 }}>
      <div className="title">
        {conflict.kind === 'topic' ? t('topic_version_conflict') : t('attendance_version_conflict')}
      </div>
      {conflict.kind === 'topic' ? (
        <div className="conflict-cols">
          <div className="card">
            <div className="label">{t('web_classes_conflict_topic_mine')}</div>
            <p>{conflict.mineTopic || '—'}</p>
          </div>
          <div className="card">
            <div className="label">{t('web_classes_conflict_topic_theirs')}</div>
            <p>{conflict.theirs || '—'}</p>
          </div>
        </div>
      ) : (
        <table className="conflict-table" style={{ width: '100%', marginTop: 12 }}>
          <thead>
            <tr>
              <th scope="col" />
              <th scope="col" className="label">
                {t('conflict_mine_heading')}
              </th>
              <th scope="col" className="label">
                {t('conflict_theirs_heading')}
              </th>
            </tr>
          </thead>
          <tbody>
            {conflict.mine.map((s) => (
              <tr key={s.enrollmentId}>
                <th scope="row" style={{ textAlign: 'left' }}>
                  {seats.find((x) => x.enrollmentId === s.enrollmentId)?.displayName ??
                    s.displayName}
                </th>
                <td>{mark(s.present)}</td>
                <td>{mark(conflict.theirs.get(s.enrollmentId))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="button-row">
        <button
          type="button"
          className="btn btn-outline"
          disabled={busy}
          onClick={() => onResolve(false)}
        >
          {t('conflict_discard')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={busy}
          onClick={() => onResolve(true)}
        >
          {t('conflict_reapply')}
        </button>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------- plan

function PlanForm({
  data,
  fresh,
  onSaved,
}: {
  data: Loaded
  fresh: boolean
  onSaved: (text: string) => void
}) {
  const { t, message } = useT()
  const { item, subjects } = data
  const [subjectId, setSubjectId] = useState<string | null>(
    () => subjects.find((s) => s.name === item.subjectName)?.id ?? null,
  )
  const [topic, setTopic] = useState(item.topic ?? '')
  const [notes, setNotes] = useState(item.notes ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [started, setStarted] = useState(false)
  const mid = useRef<string | null>(null)

  async function send(plan: boolean) {
    setBusy(true)
    setError(null)
    const chosen = subjects.find((s) => s.id === subjectId)
    try {
      if (chosen && chosen.name !== item.subjectName)
        await setSessionSubject(item.sessionId, chosen.id)
      mid.current ??= mutationId()
      await writeTopic(item.sessionId, {
        base_topic_version: item.topicVersion,
        client_mutation_id: mid.current,
        topic: topic.trim(),
        notes: notes.trim(),
        plan,
      })
      mid.current = null
      setBusy(false)
      onSaved(t(plan ? 'web_classes_plan_saved' : 'web_classes_saved'))
    } catch (e) {
      setBusy(false)
      if (e instanceof ApiError && e.code === CLASS_STARTED) {
        // Refused before anything was written; a covered save is a new write.
        mid.current = null
        setStarted(true)
      } else {
        setError(errorText(e, message, t))
      }
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        void send(true)
      }}
      noValidate
    >
      <div className="card">
        <SubjectPicker subjects={subjects} value={subjectId} onChange={setSubjectId} />
        <TextArea
          id="pc-topic"
          label={t('classplan_topics')}
          value={topic}
          onChange={(v) => {
            setTopic(v)
            mid.current = null
          }}
          help={t('classplan_hint')}
        />
        <TextArea
          id="pc-notes"
          label={t('classday_notes')}
          value={notes}
          onChange={(v) => {
            setNotes(v)
            mid.current = null
          }}
        />
      </div>
      <Section title={t('classplan_attendance_heading')}>
        <div className="card meta">
          {item.state === 'today'
            ? t('classplan_attendance_at_start')
            : t('classplan_attendance_later')}
        </div>
      </Section>
      {started ? (
        <div className="card error" role="alert" style={{ marginTop: 16 }}>
          <div className="title">{t('classplan_started_title')}</div>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-outline"
              disabled={busy}
              onClick={() => onSaved(t('web_classes_nothing_changed'))}
            >
              {t('classplan_discard')}
            </button>
            <button
              type="button"
              className="btn btn-primary grow"
              disabled={busy}
              onClick={() => void send(false)}
            >
              {t('classplan_save_covered')}
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}
      {fresh && !started ? (
        <div className="action-bar">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {t('classplan_save')}
          </button>
        </div>
      ) : null}
    </form>
  )
}

// ------------------------------------------------------------ read only

function ReadView({ item, cancelled }: { item: ClassItem; cancelled: boolean }) {
  const { t } = useT()
  const taken = item.state === 'taken'
  return (
    <>
      {cancelled ? (
        <div className="banner" role="status" style={{ marginBottom: 12 }}>
          {t('teaching_session_cancelled')}
        </div>
      ) : null}
      <Section title={taken ? t('classday_topics_covered') : t('family_planned_topics')}>
        <div className="card">
          {item.topic?.trim() ? (
            <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{item.topic}</p>
          ) : (
            <p className="meta" style={{ margin: 0 }}>
              {taken ? t('session_topic_unlogged') : t('class_no_topics_planned')}
            </p>
          )}
          {item.notes?.trim() ? (
            <p className="meta" style={{ whiteSpace: 'pre-wrap' }}>
              {item.notes}
            </p>
          ) : null}
        </div>
      </Section>
    </>
  )
}

// --------------------------------------------------------- move, cancel

function ManageClass({
  session,
  onChanged,
}: {
  session: Schemas['SessionResponse']
  onChanged: (text: string) => void
}) {
  const { t, message } = useT()
  const [open, setOpen] = useState<'move' | 'cancel' | null>(null)
  const [date, setDate] = useState(session.date)
  const [start, setStart] = useState(session.start_time.slice(0, 5))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>, text: string) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setOpen(null)
      setBusy(false)
      onChanged(text)
    } catch (e) {
      setBusy(false)
      setError(errorText(e, message, t))
    }
  }

  return (
    <Section title={t('web_classes_change')}>
      <div className="button-row" style={{ marginTop: 0 }}>
        <button type="button" className="btn btn-outline" onClick={() => setOpen('move')}>
          {t('web_classes_move')}
        </button>
        <button type="button" className="btn btn-danger" onClick={() => setOpen('cancel')}>
          {t('web_classes_cancel')}
        </button>
      </div>
      {open === 'move' ? (
        <Sheet title={t('web_classes_move_title')} onClose={() => setOpen(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void run(
                () => rescheduleSession(session.session_id, { date, start_time: start }),
                t('web_classes_moved'),
              )
            }}
            noValidate
          >
            <div className="field">
              <label htmlFor="mv-date">{t('web_classes_date')}</label>
              <input
                id="mv-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="mv-start">{t('web_classes_starts')}</label>
              <input
                id="mv-start"
                type="time"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            {error ? (
              <div className="banner error" role="alert" style={{ marginTop: 16 }}>
                {error}
              </div>
            ) : null}
            <div className="button-row">
              <button
                type="submit"
                className="btn btn-primary btn-money"
                disabled={busy || !date || !start}
              >
                {t('web_classes_move_save')}
              </button>
            </div>
          </form>
        </Sheet>
      ) : null}
      {open === 'cancel' ? (
        <Sheet title={t('web_classes_cancel_title')} onClose={() => setOpen(null)}>
          <p className="meta">{t('web_classes_cancel_body')}</p>
          {error ? (
            <div className="banner error" role="alert" style={{ marginTop: 16 }}>
              {error}
            </div>
          ) : null}
          <div className="button-row">
            <button
              type="button"
              className="btn btn-danger btn-money"
              disabled={busy}
              onClick={() =>
                void run(() => cancelSession(session.session_id), t('web_classes_cancelled_done'))
              }
            >
              {t('web_classes_cancel_confirm')}
            </button>
            <button type="button" className="btn btn-text btn-money" onClick={() => setOpen(null)}>
              {t('web_classes_keep')}
            </button>
          </div>
        </Sheet>
      ) : null}
    </Section>
  )
}
