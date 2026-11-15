/**
 * The batches on the owner's public page: each batch's listing state,
 * its server-computed checklist, and an editor sheet.
 *
 * The fee is the server's money string, shown as it arrived; it is never
 * parsed or formatted here, and it is present only while the owner chose
 * to show it. The teachers named are the server's `teacher_names`, which
 * already carries the "Centre faculty" fallback for members who have not
 * agreed to be named.
 */
import { useState } from 'react'
import {
  listBatchListings,
  publishBatchListing,
  saveBatchListing,
  unpublishBatchListing,
} from '../../../api/endpoints'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import {
  batchBody,
  batchDraftOf,
  CLASS_LEVELS,
  CURRICULA,
  levelsLine,
  teacherLine,
  type BatchDraft,
  type BatchListing,
} from './hub.mappers'
import { Checklist, failureText, FailureBanner, StatusChip } from './hubUi'

function BatchEditor({
  batch,
  onClose,
  onChanged,
}: {
  batch: BatchListing
  onClose: () => void
  onChanged: (next: BatchListing, note?: string) => void
}) {
  const { t, message } = useT()
  const [saved, setSaved] = useState(batch)
  const [draft, setDraft] = useState<BatchDraft>(() => batchDraftOf(batch))
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [retry, setRetry] = useState<(() => Promise<void>) | null>(null)
  const suspended = saved.status === 'suspended'
  const set = (patch: Partial<BatchDraft>) => {
    setDirty(true)
    setDraft((d) => ({ ...d, ...patch }))
  }

  /** Run one write; on failure keep the form and offer the same call again. */
  async function run(call: () => Promise<BatchListing>, after: 'saved' | 'state') {
    setBusy(true)
    setFailure(null)
    setRetry(null)
    try {
      const next = await call()
      setSaved(next)
      if (after === 'saved') {
        setDraft(batchDraftOf(next))
        setDirty(false)
      }
      onChanged(next)
    } catch (e) {
      setFailure(failureText(e, t, message))
      setRetry(() => () => run(call, after))
    } finally {
      setBusy(false)
    }
  }

  const save = () => run(() => saveBatchListing(saved.batch_id, batchBody(draft)), 'saved')
  const publish = () => run(() => publishBatchListing(saved.batch_id), 'state')
  const unpublish = () => run(() => unpublishBatchListing(saved.batch_id), 'state')

  const text = (
    id: string,
    label: string,
    key: keyof BatchDraft,
    opts: { multiline?: boolean; help?: string; maxLength?: number } = {},
  ) => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {opts.multiline ? (
        <textarea
          id={id}
          value={draft[key] as string}
          maxLength={opts.maxLength}
          disabled={suspended}
          onChange={(e) => set({ [key]: e.target.value })}
        />
      ) : (
        <input
          id={id}
          value={draft[key] as string}
          maxLength={opts.maxLength}
          disabled={suspended}
          onChange={(e) => set({ [key]: e.target.value })}
        />
      )}
      {opts.help ? <span className="help">{opts.help}</span> : null}
    </div>
  )

  return (
    <Sheet
      title={saved.batch_name}
      subtitle={t('web_hub_batch_edit_title')}
      onClose={onClose}
      dirty={dirty}
    >
      <div className="chips">
        <StatusChip status={saved.status} />
      </div>
      <Checklist items={saved.checklist} />
      <fieldset disabled={suspended} style={{ border: 0, padding: 0, margin: 0 }}>
        {text('bl-title', t('web_hub_batch_field_public_title'), 'publicTitle', {
          help: t('web_hub_batch_public_title_help'),
          maxLength: 120,
        })}
        {text('bl-slug', t('web_hub_field_slug'), 'slug', {
          help: t('web_hub_slug_help'),
          maxLength: 60,
        })}
        {text('bl-desc-en', t('web_hub_batch_field_description_en'), 'descriptionEn', {
          multiline: true,
          maxLength: 4000,
        })}
        {text('bl-desc-bn', t('web_hub_batch_field_description_bn'), 'descriptionBn', {
          multiline: true,
          maxLength: 4000,
        })}
        {text('bl-syl-en', t('web_hub_batch_field_syllabus_en'), 'syllabusEn', {
          multiline: true,
          maxLength: 4000,
        })}
        {text('bl-syl-bn', t('web_hub_batch_field_syllabus_bn'), 'syllabusBn', {
          multiline: true,
          maxLength: 4000,
        })}
        <div className="field">
          <label id="bl-levels-label">{t('web_hub_batch_field_levels')}</label>
          {/* The closed vocabulary as chips: nothing typed, nothing the server refuses. */}
          <div className="chips" role="group" aria-labelledby="bl-levels-label">
            {CLASS_LEVELS.map((l) => {
              const on = draft.levels.includes(l)
              return (
                <button
                  key={l}
                  type="button"
                  className="chip chip-filter"
                  aria-pressed={on}
                  onClick={() =>
                    set({ levels: on ? draft.levels.filter((x) => x !== l) : [...draft.levels, l] })
                  }
                >
                  {t(`web_hub_level_${l}`)}
                </button>
              )
            })}
          </div>
        </div>
        <div className="field">
          <label htmlFor="bl-curriculum">{t('web_hub_batch_field_curriculum')}</label>
          <select
            id="bl-curriculum"
            value={draft.curriculum}
            onChange={(e) => set({ curriculum: e.target.value as BatchDraft['curriculum'] })}
          >
            <option value="">{t('web_hub_batch_curriculum_none')}</option>
            {CURRICULA.map((c) => (
              <option key={c} value={c}>
                {t(`web_hub_curriculum_${c}`)}
              </option>
            ))}
          </select>
        </div>
        {text('bl-tags', t('web_hub_batch_field_tags'), 'tags', {
          help: t('web_hub_batch_tags_help'),
        })}
        <div className="field">
          <label htmlFor="bl-mode">{t('web_hub_batch_field_mode')}</label>
          <select
            id="bl-mode"
            value={draft.mode}
            onChange={(e) => set({ mode: e.target.value as BatchDraft['mode'] })}
          >
            <option value="">{t('web_hub_batch_mode_none')}</option>
            {(['in_person', 'home_visit', 'online'] as const).map((m) => (
              <option key={m} value={m}>
                {t(`web_hub_mode_${m}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="bl-adm">{t('web_hub_batch_field_admissions')}</label>
          <select
            id="bl-adm"
            value={draft.admissions}
            onChange={(e) => set({ admissions: e.target.value as BatchDraft['admissions'] })}
          >
            {(['open', 'waitlist', 'closed'] as const).map((a) => (
              <option key={a} value={a}>
                {t(`web_hub_batch_admissions_${a}`)}
              </option>
            ))}
          </select>
        </div>
        <label className="row" style={{ cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={draft.showFee}
            onChange={(e) => set({ showFee: e.target.checked })}
          />
          <span className="grow">{t('web_hub_batch_show_fee')}</span>
        </label>
        <label className="row" style={{ cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={draft.showSchedule}
            onChange={(e) => set({ showSchedule: e.target.checked })}
          />
          <span className="grow">{t('web_hub_batch_show_schedule')}</span>
        </label>
        {saved.show_fee === null ? <p className="meta">{t('web_hub_batch_flags_help')}</p> : null}
      </fieldset>
      {failure ? (
        <FailureBanner text={failure} onRetry={retry ? () => void retry() : undefined} />
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        {suspended ? null : (
          <>
            <button
              type="button"
              className="btn btn-outline grow"
              disabled={!dirty || busy}
              onClick={() => void save()}
            >
              {t('web_hub_save')}
            </button>
            {saved.status === 'published' ? (
              <button
                type="button"
                className="btn btn-outline"
                disabled={busy || dirty}
                onClick={() => void unpublish()}
              >
                {t('web_hub_unpublish')}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || dirty || !saved.publishable}
                onClick={() => void publish()}
              >
                {t('web_hub_publish')}
              </button>
            )}
          </>
        )}
      </div>
    </Sheet>
  )
}

export function BatchListings() {
  const { t } = useT()
  const { resource, reload } = useResource((signal) => listBatchListings(signal), [])
  const [editing, setEditing] = useState<string | null>(null)
  const [snack, setSnack] = useState<string | null>(null)

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('web_hub_batches_title')} error={resource.error} onRetry={reload} />
  else {
    const rows = resource.data
    const open = rows.find((b) => b.batch_id === editing)
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <p className="meta">{t('web_hub_batches_owner_first')}</p>
        {rows.length === 0 ? <EmptyState title={t('web_hub_batches_empty')} /> : null}
        <ul className="card flush list">
          {rows.map((b) => (
            <li key={b.batch_id}>
              <div className="row">
                <span className="grow">
                  {/* Long Bangla names wrap; nothing here is truncated. */}
                  <span className="title" style={{ overflowWrap: 'anywhere' }}>
                    {b.batch_name}
                  </span>
                  <br />
                  <span className="meta">{b.subjects.join(', ')}</span>
                  {levelsLine(b, t) ? (
                    <>
                      <br />
                      <span className="meta">{levelsLine(b, t)}</span>
                    </>
                  ) : null}
                  <br />
                  <span className="meta">
                    {b.fee !== null ? t('web_hub_batch_fee', b.fee) : t('web_hub_batch_fee_hidden')}
                  </span>
                  {b.teacher_names.length > 0 ? (
                    <>
                      <br />
                      <span className="meta">
                        {t('web_hub_batch_teachers', teacherLine(b.teacher_names, t))}
                      </span>
                    </>
                  ) : null}
                </span>
                <StatusChip status={b.status} />
                <button
                  type="button"
                  className="btn btn-text btn-small"
                  onClick={() => setEditing(b.batch_id)}
                >
                  {t('web_hub_batch_edit')}
                </button>
              </div>
            </li>
          ))}
        </ul>
        {open ? (
          <BatchEditor
            key={open.batch_id}
            batch={open}
            onClose={() => {
              setEditing(null)
              reload()
            }}
            onChanged={(_next, note) => note && setSnack(note)}
          />
        ) : null}
      </>
    )
  }

  return (
    <>
      <TopBar title={t('web_hub_batches_title')} back="/more/hub" />
      {body}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
