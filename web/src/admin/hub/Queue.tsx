/**
 * Public-hub moderation: open reports and suspended listings, oldest
 * first as the server sends them.
 *
 * Every act (uphold, dismiss, suspend, lift) asks for an in-page
 * confirmation first and sends nothing until it is confirmed. What may be
 * seen is the server's decision: a reporter is an opaque reference, and
 * nothing about a student or guardian is in the queue [TC-14] [D-6].
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, Loading, Snackbar, StaleBanner } from '../../ui/components'
import { WarningIcon } from '../../ui/icons'
import { decideHubReport, readHubQueue, setHubSuspension } from '../screens/api'
import { AdminFailure, AdminFrame } from '../screens/AdminFrame'
import { ApiError } from '../../api/errors'
import type { Schemas } from '../../api/endpoints'

type Item = Schemas['AdminHubQueueItem']
type Reason = Schemas['AdminHubSuspensionRequest']['reason_code']
type Tab = 'report' | 'listing'

const REASONS: readonly Reason[] = [
  'personal_info',
  'child_safety',
  'abusive',
  'fake',
  'misleading',
  'other',
]
const isReason = (r: string | null): r is Reason => REASONS.some((x) => x === r)

type Act = { kind: 'uphold' | 'dismiss' } | { kind: 'suspend'; reason: Reason } | { kind: 'lift' }

/** The fields the server also sends as the row's `title`. */
const TITLE_KEYS: ReadonlySet<string> = new Set(['public_name', 'public_title'])

const rowKey = (i: Item) => i.report_id ?? `${i.target_kind}:${i.target_id}`

function reasonLabel(t: (k: string) => string, reason: string | null): string {
  return isReason(reason) ? t(`web_admin_hub_reason_${reason}`) : (reason ?? '')
}

function QueueRow({ item, onDone }: { item: Item; onDone: (text: string) => void }) {
  const { t, message } = useT()
  const [act, setAct] = useState<Act | null>(null)
  const [reason, setReason] = useState<Reason>('other')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const confirmButton = useRef<HTMLButtonElement>(null)
  const row = useRef<HTMLLIElement>(null)
  /** Which trigger opened the confirmation, so Cancel can hand focus back to it. */
  const opener = useRef<string | null>(null)

  // Opening a confirmation moves focus to Confirm; closing it without acting
  // returns focus to the button that opened it (which was unmounted meanwhile).
  useEffect(() => {
    if (act) confirmButton.current?.focus()
    else if (opener.current) {
      row.current?.querySelector<HTMLElement>(`[data-act="${opener.current}"]`)?.focus()
      opener.current = null
    }
  }, [act])

  function open(next: Act) {
    opener.current = next.kind
    setAct(next)
  }

  async function confirm() {
    if (!act) return
    setBusy(true)
    setFailure(null)
    try {
      if (act.kind === 'uphold' || act.kind === 'dismiss') {
        if (!item.report_id) return
        await decideHubReport(item.report_id, act.kind === 'uphold' ? 'upheld' : 'dismissed')
      } else if (item.owner_id) {
        await setHubSuspension(item.owner_id, {
          suspended: act.kind === 'suspend',
          reason_code:
            act.kind === 'suspend' ? act.reason : isReason(item.reason) ? item.reason : 'other',
        })
      }
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

  // Owner and batch listings are distinct kinds, so the heading says which.
  const heading = t(`web_admin_hub_kind_${item.target_kind}`)
  // The public name or title is already the row's title; the rest is listed.
  const fields = item.fields.filter((f) => !(TITLE_KEYS.has(f.key) && f.value === item.title))

  return (
    <li ref={row}>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <span className="grow" style={{ minWidth: 0 }}>
          <span className="meta">{heading}</span>
          <br />
          {/* Long titles and text wrap; they are never truncated. */}
          <span className="title" style={{ overflowWrap: 'anywhere' }}>
            {item.title ?? ''}
          </span>
          {/* Everything the owner submitted for display, each under its label. */}
          {fields.length > 0 ? (
            <dl style={{ margin: '4px 0' }}>
              {fields.map((f) => (
                <div key={f.key}>
                  <dt className="meta">{t(`web_admin_hub_field_${f.key}`)}</dt>
                  <dd style={{ margin: 0, overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
                    {f.value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
          <br />
          <span className="meta">{t('web_admin_hub_reason', reasonLabel(t, item.reason))}</span>
          {item.note ? (
            <>
              <br />
              <span className="meta" style={{ overflowWrap: 'anywhere' }}>
                {item.note}
              </span>
            </>
          ) : null}
          <br />
          <span className="meta">
            {[
              item.reporter_ref ? t('web_admin_hub_reporter', item.reporter_ref) : null,
              t('web_admin_hub_waited', item.waited_hours),
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </span>
      </div>

      {act ? (
        <div className="banner" role="group" aria-label={t('web_admin_hub_confirm')}>
          <div className="grow">
            <strong>
              {t(
                act.kind === 'uphold'
                  ? 'web_admin_hub_confirm_uphold'
                  : act.kind === 'dismiss'
                    ? 'web_admin_hub_confirm_dismiss'
                    : act.kind === 'suspend'
                      ? 'web_admin_hub_confirm_suspend'
                      : 'web_admin_hub_confirm_lift',
              )}
            </strong>
            <br />
            <span className="meta">{t('web_admin_hub_confirm_body')}</span>
            {failure ? (
              <span className="field-error" role="alert">
                <WarningIcon /> {failure}
              </span>
            ) : null}
          </div>
          <div className="button-row">
            <button
              ref={confirmButton}
              type="button"
              className="btn btn-primary btn-small"
              disabled={busy}
              onClick={() => void confirm()}
            >
              {t('web_admin_hub_confirm')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={busy}
              onClick={() => setAct(null)}
            >
              {t('web_admin_hub_cancel')}
            </button>
          </div>
        </div>
      ) : (
        <div className="button-row" style={{ padding: '0 16px 12px' }}>
          {item.kind === 'report' ? (
            <>
              <button
                type="button"
                className="btn btn-outline btn-small"
                data-act="uphold"
                onClick={() => open({ kind: 'uphold' })}
              >
                {t('web_admin_hub_uphold')}
              </button>
              <button
                type="button"
                className="btn btn-outline btn-small"
                data-act="dismiss"
                onClick={() => open({ kind: 'dismiss' })}
              >
                {t('web_admin_hub_dismiss')}
              </button>
              {item.owner_id ? (
                <>
                  <label className="visually-hidden" htmlFor={`reason-${rowKey(item)}`}>
                    {t('web_admin_hub_reason_label')}
                  </label>
                  <select
                    id={`reason-${rowKey(item)}`}
                    value={reason}
                    onChange={(e) => setReason(e.target.value as Reason)}
                  >
                    {REASONS.map((r) => (
                      <option key={r} value={r}>
                        {t(`web_admin_hub_reason_${r}`)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn btn-text btn-small"
                    data-act="suspend"
                    onClick={() => open({ kind: 'suspend', reason })}
                  >
                    {t('web_admin_hub_suspend')}
                  </button>
                </>
              ) : null}
            </>
          ) : item.owner_id ? (
            <button
              type="button"
              className="btn btn-outline btn-small"
              data-act="lift"
              onClick={() => open({ kind: 'lift' })}
            >
              {t('web_admin_hub_lift')}
            </button>
          ) : null}
        </div>
      )}
    </li>
  )
}

export function AdminHubQueue() {
  const { t } = useT()
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'listing' ? 'listing' : 'report'
  const { resource, reload } = useResource(() => readHubQueue(tab), [tab])
  const [snack, setSnack] = useState<string | null>(null)

  if (resource.state === 'failed')
    return (
      <AdminFailure
        tab="hub"
        title={t('web_admin_hub_title')}
        error={resource.error}
        onRetry={reload}
      />
    )

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.data.items.length === 0)
    body = (
      <div className="card">
        <EmptyState
          title={t(
            tab === 'report' ? 'web_admin_hub_reports_empty' : 'web_admin_hub_suspended_empty',
          )}
        />
      </div>
    )
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list">
          {resource.data.items.map((i) => (
            <QueueRow
              key={rowKey(i)}
              item={i}
              onDone={(text) => {
                setSnack(text)
                reload()
              }}
            />
          ))}
        </ul>
      </>
    )

  const tabs: { id: Tab; label: string }[] = [
    { id: 'report', label: 'web_admin_hub_tab_reports' },
    { id: 'listing', label: 'web_admin_hub_tab_suspended' },
  ]

  return (
    <AdminFrame tab="hub" title={t('web_admin_hub_title')}>
      <div className="chips admin-views" role="group" aria-label={t('web_admin_hub_title')}>
        {tabs.map((x) => (
          <button
            key={x.id}
            type="button"
            className="chip chip-filter"
            aria-pressed={tab === x.id}
            onClick={() => setParams(x.id === 'report' ? {} : { tab: x.id }, { replace: true })}
          >
            {t(x.label)}
          </button>
        ))}
      </div>
      {body}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </AdminFrame>
  )
}
