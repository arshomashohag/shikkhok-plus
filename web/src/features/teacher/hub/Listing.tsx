/**
 * The owner's public listing: the page parents find on ShikkhokPlus.
 *
 * The screen renders the server's decisions. The checklist and the
 * `publishable` flag arrive computed and are all that enable Publish;
 * the client never decides completeness. A suspended listing is
 * read-only, with the reason it cannot be changed and how to appeal. A
 * failed save keeps everything typed and offers Retry, since there is no
 * offline write queue [TC-8].
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import {
  checkHubSlug,
  listHubAreas,
  publishHubListing,
  readHubListing,
  saveHubListing,
  unpublishHubListing,
  type Schemas,
} from '../../../api/endpoints'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Section, Snackbar, StaleBanner, TopBar } from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { helpPaths } from '../../help/paths'
import { paths } from '../paths'
import {
  divisionOf,
  draftOf,
  TEACHING_MODES,
  updateBody,
  type Draft,
  type Listing as ListingModel,
} from './hub.mappers'
import { Checklist, failureText, FailureBanner, StatusChip } from './hubUi'
import { PublishSheet } from './PublishSheet'

type Area = Schemas['AreaOption']

function AreaSelect({
  id,
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  id: string
  label: string
  value: string
  options: Area[]
  disabled: boolean
  onChange: (code: string) => void
}) {
  const { t, lang } = useT()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('web_hub_area_choose')}</option>
        {options.map((a) => (
          <option key={a.code} value={a.code}>
            {lang === 'bn' ? a.name_bn : a.name_en}
          </option>
        ))}
      </select>
    </div>
  )
}

/** Division → district → upazila, each level read from the server's area list. */
function AreaPickers({
  draft,
  readOnly,
  set,
}: {
  draft: Draft
  readOnly: boolean
  set: (patch: Partial<Draft>) => void
}) {
  const { t } = useT()
  const [divisions, setDivisions] = useState<Area[]>([])
  const [division, setDivision] = useState<string | null>(null)
  const [districts, setDistricts] = useState<Area[]>([])
  const [upazilas, setUpazilas] = useState<Area[]>([])
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  /** Load one level; a failure is shown with Retry, never as an empty list. */
  function load(parent: string | undefined, into: (a: Area[]) => void, signal: AbortSignal) {
    listHubAreas(parent, signal)
      .then((a) => {
        setFailed(false)
        into(a)
      })
      .catch((e: unknown) => {
        if (!(e instanceof DOMException && e.name === 'AbortError')) setFailed(true)
      })
  }

  useEffect(() => {
    const ctl = new AbortController()
    load(undefined, setDivisions, ctl.signal)
    return () => ctl.abort()
  }, [attempt])

  // Until the person picks one, the division is the one the saved district sits in.
  const chosen =
    division ??
    divisionOf(
      draft.districtCode,
      divisions.map((d) => d.code),
    )

  useEffect(() => {
    if (!chosen) {
      setDistricts([])
      return
    }
    const ctl = new AbortController()
    load(chosen, setDistricts, ctl.signal)
    return () => ctl.abort()
  }, [chosen, attempt])

  useEffect(() => {
    if (!draft.districtCode) {
      setUpazilas([])
      return
    }
    const ctl = new AbortController()
    load(draft.districtCode, setUpazilas, ctl.signal)
    return () => ctl.abort()
  }, [draft.districtCode, attempt])

  return (
    <>
      {failed ? (
        <FailureBanner text={t('web_hub_areas_failed')} onRetry={() => setAttempt((n) => n + 1)} />
      ) : null}
      <AreaSelect
        id="hub-division"
        label={t('web_hub_field_division')}
        value={chosen}
        options={divisions}
        disabled={readOnly}
        onChange={(code) => {
          setDivision(code)
          set({ districtCode: '', upazilaCode: '' })
        }}
      />
      <AreaSelect
        id="hub-district"
        label={t('web_hub_field_district')}
        value={draft.districtCode}
        options={districts}
        disabled={readOnly || !chosen}
        onChange={(code) => set({ districtCode: code, upazilaCode: '' })}
      />
      <AreaSelect
        id="hub-upazila"
        label={t('web_hub_field_upazila')}
        value={draft.upazilaCode}
        options={upazilas}
        disabled={readOnly || !draft.districtCode}
        onChange={(code) => set({ upazilaCode: code })}
      />
    </>
  )
}

function Field({
  id,
  label,
  value,
  onChange,
  disabled,
  help,
  multiline,
  maxLength,
  type,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  disabled: boolean
  help?: string
  multiline?: boolean
  maxLength?: number
  type?: string
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          maxLength={maxLength}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          id={id}
          type={type}
          value={value}
          maxLength={maxLength}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {help ? <span className="help">{help}</span> : null}
    </div>
  )
}

function Editor({ listing, onChanged }: { listing: ListingModel; onChanged: () => void }) {
  const { t, message } = useT()
  // What the server holds now; replaced by each save's answer.
  const [saved, setSaved] = useState(listing)
  const [draft, setDraft] = useState<Draft>(() => draftOf(listing))
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [slugNote, setSlugNote] = useState<'available' | 'taken' | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)

  const suspended = saved.status === 'suspended'
  const body = updateBody(draft, saved)
  const dirty = body !== null
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))

  async function save() {
    if (!body) return
    setBusy(true)
    setFailure(null)
    try {
      const next = await saveHubListing(body)
      setSaved(next)
      setDraft(draftOf(next))
      setSnack(t('web_hub_saved'))
      onChanged()
    } catch (e) {
      // The draft stays exactly as typed; Retry sends the same changes.
      setFailure(`${t('web_hub_save_failed')} ${failureText(e, t, message)}`)
    } finally {
      setBusy(false)
    }
  }

  async function checkSlug() {
    setSlugNote(null)
    try {
      const r = await checkHubSlug(draft.slug.trim())
      setSlugNote(r.available ? 'available' : 'taken')
    } catch (e) {
      setFailure(failureText(e, t, message))
    }
  }

  async function publish(version: string) {
    const next = await publishHubListing(version)
    setSaved(next)
    setDraft(draftOf(next))
    setPublishing(false)
    setSnack(t('web_hub_published_snack'))
    onChanged()
  }

  async function unpublish() {
    setBusy(true)
    setFailure(null)
    try {
      const next = await unpublishHubListing()
      setSaved(next)
      setDraft(draftOf(next))
      setSnack(t('web_hub_unpublished'))
      onChanged()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  const canPublish = saved.publishable && !dirty && !suspended && saved.status !== 'published'

  return (
    <>
      <div className="chips" style={{ marginBottom: 12 }}>
        <StatusChip status={saved.status} />
        {saved.runs_classes ? (
          <span className="chip chip-paid">{t('web_hub_badge_runs_classes')}</span>
        ) : null}
      </div>

      {suspended ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <div>
            <strong>{t('web_hub_suspended_title')}</strong>
            <br />
            {t('web_hub_suspended_body')}{' '}
            <Link to={helpPaths.ask()}>{t('web_hub_suspended_appeal')}</Link>
          </div>
        </div>
      ) : null}

      <Section title={t('web_hub_checklist_title')}>
        <div className="card flush">
          <Checklist items={saved.checklist} />
        </div>
      </Section>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <fieldset disabled={suspended} style={{ border: 0, padding: 0, margin: 0 }}>
          <Field
            id="hub-name"
            label={t('web_hub_field_public_name')}
            value={draft.publicName}
            maxLength={120}
            disabled={suspended}
            onChange={(v) => set({ publicName: v })}
          />
          <div className="field">
            <label htmlFor="hub-slug">{t('web_hub_field_slug')}</label>
            <input
              id="hub-slug"
              value={draft.slug}
              maxLength={60}
              disabled={suspended}
              autoCapitalize="none"
              onChange={(e) => {
                setSlugNote(null)
                set({ slug: e.target.value })
              }}
            />
            <span className="help">{t('web_hub_slug_help')}</span>
            {slugNote ? (
              <span className={slugNote === 'taken' ? 'field-error' : 'help'} role="status">
                {slugNote === 'taken' ? t('web_hub_slug_taken') : t('web_hub_slug_available')}
              </span>
            ) : null}
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={suspended || draft.slug.trim() === ''}
              onClick={() => void checkSlug()}
            >
              {t('web_hub_slug_check')}
            </button>
          </div>
          <Field
            id="hub-headline-en"
            label={t('web_hub_field_headline_en')}
            value={draft.headlineEn}
            maxLength={200}
            disabled={suspended}
            onChange={(v) => set({ headlineEn: v })}
          />
          <Field
            id="hub-headline-bn"
            label={t('web_hub_field_headline_bn')}
            value={draft.headlineBn}
            maxLength={200}
            disabled={suspended}
            onChange={(v) => set({ headlineBn: v })}
          />
          <Field
            id="hub-bio-en"
            label={t('web_hub_field_bio_en')}
            value={draft.bioEn}
            maxLength={5000}
            multiline
            disabled={suspended}
            onChange={(v) => set({ bioEn: v })}
          />
          <Field
            id="hub-bio-bn"
            label={t('web_hub_field_bio_bn')}
            value={draft.bioBn}
            maxLength={5000}
            multiline
            disabled={suspended}
            onChange={(v) => set({ bioBn: v })}
          />
          <Field
            id="hub-quals"
            label={t('web_hub_field_qualifications')}
            value={draft.qualifications}
            maxLength={1000}
            multiline
            disabled={suspended}
            onChange={(v) => set({ qualifications: v })}
          />
          <div className="field">
            <label id="hub-mode-label">{t('web_hub_field_mode')}</label>
            <div role="group" aria-labelledby="hub-mode-label">
              {TEACHING_MODES.map((m) => (
                <label key={m} className="row" style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={draft.modes.includes(m)}
                    disabled={suspended}
                    onChange={(e) =>
                      set({
                        modes: e.target.checked
                          ? [...draft.modes, m]
                          : draft.modes.filter((x) => x !== m),
                      })
                    }
                  />
                  <span className="grow">{t(`web_hub_mode_${m}`)}</span>
                </label>
              ))}
            </div>
          </div>
          <AreaPickers draft={draft} readOnly={suspended} set={set} />
          {saved.is_centre ? (
            <Field
              id="hub-street"
              label={t('web_hub_field_street')}
              value={draft.streetAddress}
              maxLength={300}
              disabled={suspended}
              onChange={(v) => set({ streetAddress: v })}
            />
          ) : null}
          <Field
            id="hub-phone"
            label={t('web_hub_field_phone')}
            value={draft.phone}
            maxLength={40}
            type="tel"
            disabled={suspended}
            help={t('web_hub_phone_help')}
            onChange={(v) => set({ phone: v })}
          />
        </fieldset>

        {failure ? <FailureBanner text={failure} onRetry={() => void save()} /> : null}

        {suspended ? null : (
          <div className="button-row" style={{ marginTop: 16 }}>
            <button type="submit" className="btn btn-outline grow" disabled={!dirty || busy}>
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
                className="btn btn-primary grow"
                disabled={!canPublish || busy}
                onClick={() => setPublishing(true)}
              >
                {t('web_hub_publish')}
              </button>
            )}
          </div>
        )}
        {!suspended && dirty && saved.publishable ? (
          <p className="meta">{t('web_hub_save_first')}</p>
        ) : null}
      </form>

      <p>
        <Link className="btn btn-text" to={paths.hubBatches()}>
          {t('web_hub_batches_link')}
        </Link>
      </p>

      {publishing ? (
        <PublishSheet
          consentVersion={saved.consent_version_current}
          onPublish={publish}
          onClose={() => setPublishing(false)}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}

export function HubListing() {
  const { t } = useT()
  const { resource, reload } = useResource((signal) => readHubListing(signal), [])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('web_hub_title')} error={resource.error} onRetry={reload} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <Editor listing={resource.data} onChanged={() => undefined} />
      </>
    )

  return (
    <>
      <TopBar title={t('web_hub_title')} back="/more" />
      {body}
    </>
  )
}
