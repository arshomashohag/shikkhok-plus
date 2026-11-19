/**
 * One review or reply waiting for a decision: the author as a reference and
 * a role, the tenure, the rating and the words; for a reply, the review it
 * answers above it. Then the checklist line, and approve or reject with a
 * closed code.
 *
 * The row reads the item's own detail, as a photo row does. Nothing here
 * names the author: the server sends a role and an opaque reference, never
 * a name, a phone number, a seat or a time [TC-14] [D-6] [Call 14].
 */
import { useState } from 'react'
import type { Schemas } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { decideHubReview, readHubReview } from '../screens/api'
import { ConfirmBanner, reasonLabel, useConfirmFocus } from './shared'

type Item = Schemas['AdminHubQueueItem']
type Target = Schemas['AdminHubReviewDecisionRequest']['target']
type Code = NonNullable<Schemas['AdminHubReviewDecisionRequest']['code']>

const CODES: readonly Code[] = [
  'identifiable_child',
  'personal_info',
  'abusive',
  'off_topic',
  'other',
]

type Act = { kind: 'approve' } | { kind: 'reject'; code: Code }

const textStyle = { margin: 0, overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' } as const

export function ReviewRow({ item, onDone }: { item: Item; onDone: (text: string) => void }) {
  const { t, message } = useT()
  const target: Target = item.target_kind === 'reply' ? 'reply' : 'review'
  const { resource } = useResource(
    () => readHubReview(item.target_id, target),
    [item.target_id, target],
  )
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
      await decideHubReview(
        item.target_id,
        act.kind === 'approve'
          ? { target, decision: 'approve' }
          : { target, decision: 'reject', code: act.code },
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
  const key = `${target}-${item.target_id}`
  const checkId = `review-check-${key}`
  const codeId = `review-code-${key}`

  let words: React.ReactNode
  if (resource.state === 'failed')
    words = (
      <span className="field-error" role="alert">
        {resource.error.offline ? t('web_offline_shell') : message(resource.error.messageKey)}
      </span>
    )
  else if (!detail) words = <span className="meta">{t('web_admin_hub_review_loading')}</span>
  else
    words = (
      <dl style={{ margin: '4px 0' }}>
        <div>
          <dt className="meta">
            {target === 'reply'
              ? t('web_admin_hub_review_answers')
              : t('web_admin_hub_field_review_body')}
          </dt>
          <dd style={textStyle}>
            {t('web_admin_hub_review_rating', detail.rating)}
            {detail.body ? (
              <>
                <br />
                {detail.body}
              </>
            ) : null}
          </dd>
        </div>
        {target === 'reply' && detail.reply_body ? (
          <div>
            <dt className="meta">{t('web_admin_hub_review_reply')}</dt>
            <dd style={textStyle}>{detail.reply_body}</dd>
          </div>
        ) : null}
      </dl>
    )

  return (
    <li ref={row}>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <span className="grow" style={{ minWidth: 0 }}>
          <span className="meta">{t(`web_admin_hub_kind_${target}`)}</span>
          <br />
          <span className="title" style={{ overflowWrap: 'anywhere' }}>
            {item.title ?? ''}
          </span>
          <br />
          <span className="meta">
            {[
              item.author_ref && item.author_role
                ? t(
                    'web_admin_hub_review_author',
                    item.author_ref,
                    t(`web_admin_hub_review_role_${item.author_role}`),
                  )
                : null,
              detail ? t(`web_admin_hub_review_tenure_${detail.tenure}`) : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
          {words}
          {detail?.status === 'held' ? (
            <>
              <strong>{t('web_admin_hub_review_held')}</strong>
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
              detail && detail.open_reports > 0
                ? t('web_admin_hub_review_reports', detail.open_reports)
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
          question={t(`web_admin_hub_confirm_${act.kind}_${target}`)}
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
            {t('web_admin_hub_review_check')}
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
