/**
 * One photo waiting for a decision: signed previews, its alt text, the
 * checklist line, and approve or reject with a closed code.
 *
 * The previews are five-minute signed GETs the browser loads straight from
 * the photo bucket, whose regional endpoint the admin CSP admits in
 * `img-src`; the row reads them afresh each time the queue loads. Nothing
 * here names the account that uploaded the photo: the server sends only
 * the page's public name or title [TC-14] [D-6].
 */
import { useState } from 'react'
import type { Schemas } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { decideHubMedia, readHubMedia } from '../screens/api'
import { ConfirmBanner, reasonLabel, useConfirmFocus } from './shared'

type Item = Schemas['AdminHubQueueItem']
type Preview = Schemas['AdminHubMediaPreview']
type Code = NonNullable<Schemas['AdminHubMediaDecisionRequest']['code']>

const CODES: readonly Code[] = [
  'identifiable_child',
  'personal_info',
  'not_relevant',
  'low_quality',
  'other',
]

type Act = { kind: 'approve' } | { kind: 'reject'; code: Code }

/** The widest preview no wider than 960 px, else the narrowest. */
function mainPreview(previews: readonly Preview[]): Preview | undefined {
  const sorted = [...previews].sort((a, b) => a.width - b.width)
  return sorted.filter((p) => p.width <= 960).pop() ?? sorted[0]
}

export function MediaRow({ item, onDone }: { item: Item; onDone: (text: string) => void }) {
  const { t, message } = useT()
  const { resource } = useResource(() => readHubMedia(item.target_id), [item.target_id])
  const [checked, setChecked] = useState(false)
  const [code, setCode] = useState<Code>('identifiable_child')
  const [act, setAct] = useState<Act | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const { confirmButton, row, opener } = useConfirmFocus(act?.kind ?? null)

  function open(next: Act) {
    opener.current = next.kind
    setAct(next)
  }

  async function confirm() {
    if (!act) return
    setBusy(true)
    setFailure(null)
    try {
      await decideHubMedia(
        item.target_id,
        act.kind === 'approve' ? { decision: 'approve' } : { decision: 'reject', code: act.code },
      )
      setAct(null)
      onDone(t('web_admin_hub_done'))
    } catch (e) {
      setFailure(
        e instanceof ApiError && !e.offline ? message(e.messageKey) : t('web_offline_shell'),
      )
    } finally {
      setBusy(false)
    }
  }

  const detail = resource.state === 'loaded' ? resource.data : null
  const main = detail ? mainPreview(detail.previews) : undefined
  const checkId = `media-check-${item.target_id}`
  const codeId = `media-code-${item.target_id}`

  let picture: React.ReactNode
  if (resource.state === 'failed')
    picture = (
      <span className="field-error" role="alert">
        {resource.error.offline ? t('web_offline_shell') : message(resource.error.messageKey)}
      </span>
    )
  else if (!detail) picture = <span className="meta">{t('web_admin_hub_media_loading')}</span>
  else if (main)
    picture = (
      <img
        src={main.url}
        srcSet={detail.previews.map((p) => `${p.url} ${p.width}w`).join(', ')}
        sizes="(max-width: 600px) 100vw, 480px"
        alt={detail.alt_en ?? ''}
        width={detail.width ?? undefined}
        height={detail.height ?? undefined}
        style={{ display: 'block', maxWidth: '100%', height: 'auto', margin: '8px 0' }}
      />
    )

  return (
    <li ref={row}>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <span className="grow" style={{ minWidth: 0 }}>
          <span className="meta">{t('web_admin_hub_kind_media')}</span>
          <br />
          <span className="title" style={{ overflowWrap: 'anywhere' }}>
            {item.title ?? ''}
          </span>
          {picture}
          {item.fields.length > 0 ? (
            <dl style={{ margin: '4px 0' }}>
              {item.fields.map((f) => (
                <div key={f.key}>
                  <dt className="meta">{t(`web_admin_hub_field_${f.key}`)}</dt>
                  <dd style={{ margin: 0, overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
                    {f.value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
          {detail?.status === 'held' ? (
            <>
              <strong>{t('web_admin_hub_media_held')}</strong>
              <br />
            </>
          ) : null}
          {item.reason ? (
            <>
              <span className="meta">{t('web_admin_hub_reason', reasonLabel(t, item.reason))}</span>
              <br />
            </>
          ) : null}
          <span className="meta">
            {[
              detail && detail.report_count > 0
                ? t('web_admin_hub_media_reports', detail.report_count)
                : null,
              t('web_admin_hub_waited', item.waited_hours),
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </span>
      </div>

      {act ? (
        <ConfirmBanner
          question={t(`web_admin_hub_confirm_${act.kind}`)}
          failure={failure}
          busy={busy}
          confirmButton={confirmButton}
          onConfirm={() => void confirm()}
          onCancel={() => setAct(null)}
        />
      ) : (
        <div className="button-row" style={{ padding: '0 16px 12px', flexWrap: 'wrap' }}>
          <label htmlFor={checkId} className="row" style={{ gap: 8, padding: 0 }}>
            <input
              id={checkId}
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            {t('web_admin_hub_media_check')}
          </label>
          <button
            type="button"
            className="btn btn-outline btn-small"
            data-act="approve"
            disabled={!checked || !detail}
            onClick={() => open({ kind: 'approve' })}
          >
            {t('web_admin_hub_approve')}
          </button>
          <label className="visually-hidden" htmlFor={codeId}>
            {t('web_admin_hub_rejection_label')}
          </label>
          <select id={codeId} value={code} onChange={(e) => setCode(e.target.value as Code)}>
            {CODES.map((c) => (
              <option key={c} value={c}>
                {t(`web_admin_hub_rejection_${c}`)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-text btn-small"
            data-act="reject"
            onClick={() => open({ kind: 'reject', code })}
          >
            {t('web_admin_hub_reject')}
          </button>
        </div>
      )}
    </li>
  )
}
