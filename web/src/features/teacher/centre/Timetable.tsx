/**
 * The centre's timetable: a week of classes across every batch, each with
 * its teacher and room. A manager changes one class's teacher or room, or
 * swaps two classes' teachers; the server refuses a double-booking and
 * names the class it clashes with. Rooms are managed from here too.
 */
import { useState } from 'react'
import {
  addRoom,
  assignClass,
  listMembers,
  listRooms,
  readTimetable,
  swapClasses,
  updateRoom,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatClock, formatLongDay } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Section,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import {
  assignable,
  byDay,
  clashOf,
  isoDay,
  liveRooms,
  shiftWeek,
  swapCandidates,
  weekFrom,
  type TimetableClass,
} from './timetable'

type Translate = (k: string, ...a: (string | number)[]) => string

function failureText(e: unknown, t: Translate, message: (k: string) => string): string {
  const clash = clashOf(e)
  if (clash)
    return `${message('schedule.clash')} ${t('timetable_clash_detail', clash.batch, clash.time)}`
  const error = e instanceof ApiError ? e : null
  return error?.offline
    ? t('web_money_offline_nothing_changed')
    : message(error?.messageKey ?? 'error.unexpected')
}

function ClassSheet({
  target,
  all,
  onClose,
  onSaved,
}: {
  target: TimetableClass
  all: TimetableClass[]
  onClose: () => void
  onSaved: () => void
}) {
  const { t, message, lang } = useT()
  const members = useResource((signal) => listMembers(signal), [])
  const rooms = useResource((signal) => listRooms(signal), [])
  const [teacher, setTeacher] = useState(target.teacher_member_id ?? '')
  const [room, setRoom] = useState(target.room_id ?? '')
  const [swapWith, setSwapWith] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const candidates = swapCandidates(target, all)

  async function save() {
    setBusy(true)
    setFailure(null)
    try {
      if (swapWith) await swapClasses(target.session_id, swapWith)
      else
        await assignClass(target.session_id, {
          teacher_member_id: teacher || null,
          room_id: room || null,
        })
      onSaved()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  const loaded = members.resource.state === 'loaded' && rooms.resource.state === 'loaded'
  return (
    <Sheet title={t('timetable_change')} onClose={onClose}>
      <p className="meta" style={{ marginTop: 0 }}>
        {target.batch_name} · {formatLongDay(target.date, lang)} ·{' '}
        {formatClock(target.start_time, lang)}
      </p>
      {!loaded ? <Loading rows={2} /> : null}
      {members.resource.state === 'loaded' && rooms.resource.state === 'loaded' ? (
        <>
          <div className="field">
            <label htmlFor="tt-teacher">{t('timetable_teacher_label')}</label>
            <select
              id="tt-teacher"
              value={teacher}
              disabled={swapWith !== ''}
              onChange={(e) => setTeacher(e.target.value)}
            >
              <option value="">{t('timetable_none_option')}</option>
              {assignable(members.resource.data).map((m) => (
                <option key={m.member_id} value={m.member_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tt-room">{t('timetable_room_label')}</label>
            <select
              id="tt-room"
              value={room}
              disabled={swapWith !== ''}
              onChange={(e) => setRoom(e.target.value)}
            >
              <option value="">{t('timetable_none_option')}</option>
              {liveRooms(rooms.resource.data).map((r) => (
                <option key={r.room_id} value={r.room_id}>
                  {r.name}
                </option>
              ))}
            </select>
            <span className="help">{t('timetable_this_class_only')}</span>
          </div>
          {candidates.length > 0 ? (
            <div className="field">
              <label htmlFor="tt-swap">{t('timetable_swap_label')}</label>
              <select id="tt-swap" value={swapWith} onChange={(e) => setSwapWith(e.target.value)}>
                <option value="">{t('timetable_swap_none')}</option>
                {candidates.map((c) => (
                  <option key={c.session_id} value={c.session_id}>
                    {formatClock(c.start_time, lang)} · {c.batch_name} ·{' '}
                    {c.teacher_name ?? t('timetable_unassigned')}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </>
      ) : null}
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!loaded || busy}
          onClick={() => void save()}
        >
          {swapWith ? t('timetable_swap_submit') : t('staff_save')}
        </button>
      </div>
    </Sheet>
  )
}

function RoomsSheet({ onClose }: { onClose: () => void }) {
  const { t, message } = useT()
  const { resource, reload } = useResource((signal) => listRooms(signal), [])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function act(work: () => Promise<unknown>) {
    setBusy(true)
    setFailure(null)
    try {
      await work()
      reload()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('rooms_title')} onClose={onClose}>
      {resource.state === 'loading' ? <Loading rows={2} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('rooms_title')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' ? (
        resource.data.length === 0 ? (
          <p className="meta">{t('rooms_empty')}</p>
        ) : (
          <ul className="card flush list">
            {resource.data.map((r) => (
              <li key={r.room_id}>
                <div className="row" style={r.archived ? { opacity: 0.6 } : undefined}>
                  <span className="grow">
                    <span className="title">{r.name}</span>
                    {r.archived ? (
                      <>
                        <br />
                        <span className="meta">{t('rooms_archived')}</span>
                      </>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    className="btn btn-text btn-small"
                    disabled={busy}
                    onClick={() => void act(() => updateRoom(r.room_id, { archived: !r.archived }))}
                  >
                    {r.archived ? t('rooms_restore') : t('rooms_archive')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )
      ) : null}
      <div className="field">
        <label htmlFor="rm-name">{t('rooms_name_label')}</label>
        <input id="rm-name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!name.trim() || busy}
          onClick={() =>
            void act(async () => {
              await addRoom(name.trim())
              setName('')
            })
          }
        >
          {t('rooms_add')}
        </button>
      </div>
    </Sheet>
  )
}

export function Timetable() {
  const { t, lang } = useT()
  const [start, setStart] = useState(() => isoDay(new Date()))
  const days = weekFrom(start)
  const { resource, reload } = useResource(
    (signal) => readTimetable(start, weekFrom(start)[6] ?? start, signal),
    [start],
  )
  const [editing, setEditing] = useState<TimetableClass | null>(null)
  const [rooms, setRooms] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  // Open a class only from a read the server just confirmed.
  const fresh = resource.state === 'loaded' && !resource.refreshing && resource.error === null

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('timetable_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = <EmptyState title={t('timetable_title')} body={t('timetable_empty')} />
  else
    body = [
      resource.error ? (
        <StaleBanner key="stale" error={resource.error} loadedAt={resource.loadedAt} />
      ) : null,
      ...byDay(days, resource.data)
        .filter(([, list]) => list.length > 0)
        .map(([day, list]) => (
          <Section key={day} title={formatLongDay(day, lang)}>
            <ul className="card flush list">
              {list.map((c) => {
                const cancelled = c.status === 'cancelled'
                return (
                  <li key={c.session_id}>
                    <button
                      type="button"
                      className="row"
                      disabled={cancelled || !fresh}
                      style={cancelled ? { opacity: 0.55 } : undefined}
                      onClick={() => setEditing(c)}
                    >
                      <span className="meta" style={{ minWidth: 64 }}>
                        {formatClock(c.start_time, lang)}
                      </span>
                      <span className="grow">
                        <span className="title">
                          {c.batch_name}
                          {c.subject ? ` · ${c.subject}` : ''}
                        </span>
                        <br />
                        <span className="meta">
                          {[
                            c.teacher_name ?? t('timetable_unassigned'),
                            c.room_name,
                            cancelled ? t('timetable_cancelled') : null,
                            c.overridden ? t('timetable_overridden') : null,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </Section>
        )),
    ]

  return (
    <>
      <TopBar
        title={t('timetable_title')}
        subtitle={t('timetable_sub')}
        actions={
          <button type="button" className="btn btn-tonal btn-small" onClick={() => setRooms(true)}>
            {t('rooms_title')}
          </button>
        }
      />
      <div className="button-row" style={{ marginTop: 0, marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-text btn-small"
          onClick={() => setStart(shiftWeek(start, -1))}
        >
          ‹ {t('timetable_prev_week')}
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-text btn-small"
          onClick={() => setStart(shiftWeek(start, 1))}
        >
          {t('timetable_next_week')} ›
        </button>
      </div>
      {body}
      {editing && resource.state === 'loaded' ? (
        <ClassSheet
          target={editing}
          all={resource.data}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            setSnack(t('staff_saved'))
            reload()
          }}
        />
      ) : null}
      {rooms ? (
        <RoomsSheet
          onClose={() => {
            setRooms(false)
            reload()
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
