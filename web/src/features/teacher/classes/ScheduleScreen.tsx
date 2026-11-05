/**
 * The batch's weekly schedule: which days, one time range for all of them,
 * as Android's ScheduleEditor shapes it. Saving replaces the slots; classes
 * already listed stay as they are, which the screen says.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatClock } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { WEEKDAY_KEYS } from '../Batches'
import { WEEK_ORDER } from '../mappers'
import { paths } from '../paths'
import { readSchedule, writeSchedule } from './api'
import { draftFromSlots, slotsFromDraft, type ScheduleDraft } from './mappers'

export function ScheduleScreen() {
  const { batchId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(
    () => readSchedule(batchId).then(draftFromSlots),
    [batchId],
  )
  const back = paths.batch(batchId, 'classes')

  return (
    <>
      <TopBar title={t('screen_title_schedule')} back={back} />
      {resource.state === 'loading' ? <Loading rows={2} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('screen_title_schedule')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' ? (
        <ScheduleForm batchId={batchId} initial={resource.data} fresh={resource.error === null} />
      ) : null}
    </>
  )
}

function ScheduleForm({
  batchId,
  initial,
  fresh,
}: {
  batchId: string
  initial: ScheduleDraft
  fresh: boolean
}) {
  const { t, lang, message } = useT()
  const navigate = useNavigate()
  const [draft, setDraft] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (draft.days.length > 0 && draft.end <= draft.start) {
      setError(t('schedule_end_before_start'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await writeSchedule(batchId, slotsFromDraft(draft))
      navigate(paths.batch(batchId, 'classes'))
    } catch (err) {
      setError(err instanceof ApiError ? message(err.messageKey) : t('error_unexpected'))
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={onSubmit} noValidate>
      <fieldset className="field" style={{ marginTop: 0 }}>
        <legend>{t('schedule_days')}</legend>
        <div className="chips">
          {WEEK_ORDER.map((d) => (
            <button
              key={d}
              type="button"
              className="chip chip-filter"
              aria-pressed={draft.days.includes(d)}
              onClick={() =>
                setDraft((cur) => ({
                  ...cur,
                  days: cur.days.includes(d) ? cur.days.filter((x) => x !== d) : [...cur.days, d],
                }))
              }
            >
              {t(WEEKDAY_KEYS[d] ?? 'weekday_mon')}
            </button>
          ))}
        </div>
      </fieldset>
      {draft.days.length > 0 ? (
        <div style={{ display: 'flex', gap: 12 }}>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="sc-start">{t('schedule_start', formatClock(draft.start, lang))}</label>
            <input
              id="sc-start"
              type="time"
              value={draft.start}
              onChange={(e) => setDraft((cur) => ({ ...cur, start: e.target.value }))}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="sc-end">{t('schedule_end', formatClock(draft.end, lang))}</label>
            <input
              id="sc-end"
              type="time"
              value={draft.end}
              onChange={(e) => setDraft((cur) => ({ ...cur, end: e.target.value }))}
            />
          </div>
        </div>
      ) : (
        <p className="meta">{t('schedule_none')}</p>
      )}
      <p className="meta">{t('schedule_keeps_sessions')}</p>
      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}
      {fresh ? (
        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {t('schedule_save')}
          </button>
        </div>
      ) : null}
    </form>
  )
}
