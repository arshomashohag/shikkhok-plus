/**
 * T7 · Notices tab. As `NoticesTab.kt`: the batch's notices in the
 * server's order, each with Edit and Remove, and a composer at the bottom.
 * A notice reaches every student and guardian in the batch.
 *
 * The API returns notices the teacher wrote. It does not mark the
 * schedule-change notices the design draws, nor how many families have
 * seen one, so neither is drawn here.
 */
import { useCallback, useState } from 'react'
import { ApiError } from '../../../api/errors'
import { ago } from '../../../core/format'
import { useOnline, useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Sheet, Snackbar } from '../../../ui/components'
import type { BatchTabProps } from '../area'
import { editAnnouncement, listAnnouncements, postAnnouncement, removeAnnouncement } from './api'
import { mapNotices, type Notice } from './mappers'

/** The server's limit on a notice body. */
const NOTICE_MAX = 4000

type Dialog = { kind: 'edit'; notice: Notice } | { kind: 'remove'; notice: Notice } | null

export function NoticesTab({ batchId }: BatchTabProps) {
  const { t, message } = useT()
  const online = useOnline()
  const { resource, reload } = useResource(
    (signal) => listAnnouncements(batchId, signal).then(mapNotices),
    [batchId],
  )
  const [draft, setDraft] = useState('')
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  const dismiss = useCallback(() => setSnack(null), [])

  async function write(action: () => Promise<unknown>, done: string): Promise<boolean> {
    setBusy(true)
    try {
      await action()
      setSnack(done)
      reload()
      return true
    } catch (e) {
      setSnack(message(e instanceof ApiError ? e.messageKey : 'error.unexpected'))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function post() {
    const body = draft.trim()
    if (!body) return
    if (await write(() => postAnnouncement(batchId, body), t('web_notices_sent'))) setDraft('')
  }

  let list: React.ReactNode
  if (resource.state === 'loading') list = <Loading rows={3} />
  else if (resource.state === 'failed')
    list = <ErrorCard title={t('batch_tab_notices')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    list = <EmptyState title={t('batch_notices_empty')} body={t('batch_notices_empty_body')} />
  else {
    const actionable = resource.error === null && !resource.refreshing && online
    list = (
      <div className="notices">
        {resource.data.map((n) => (
          <article key={n.id} className="card">
            <p className="notice-body">{n.body}</p>
            <div className="meta">
              {ago(n.postedAt, new Date(), t)}
              {n.edited ? ` · ${t('batch_notice_edited')}` : ''}
            </div>
            {actionable ? (
              <div className="seat-actions" style={{ padding: '8px 0 0', marginLeft: -12 }}>
                <button
                  type="button"
                  className="btn btn-text btn-small"
                  onClick={() => setDialog({ kind: 'edit', notice: n })}
                >
                  {t('batch_notice_edit')}
                </button>
                <button
                  type="button"
                  className="btn btn-text btn-small danger"
                  onClick={() => setDialog({ kind: 'remove', notice: n })}
                >
                  {t('batch_remove')}
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    )
  }

  const canPost = online && !busy && draft.trim() !== ''
  return (
    <>
      {list}
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          void post()
        }}
      >
        <label htmlFor="notice-draft" className="visually-hidden">
          {t('batch_write_notice')}
        </label>
        <textarea
          id="notice-draft"
          placeholder={t('batch_write_notice')}
          value={draft}
          maxLength={NOTICE_MAX}
          onChange={(e) => setDraft(e.target.value)}
          aria-describedby="notice-help"
        />
        <button type="submit" className="btn btn-primary" disabled={!canPost}>
          {t('batch_notice_send')}
        </button>
      </form>
      <p id="notice-help" className="meta" style={{ marginTop: 4 }}>
        {online ? t('batch_notice_help') : t('more_needs_connection')}
      </p>

      {dialog?.kind === 'edit' ? (
        <EditSheet
          notice={dialog.notice}
          busy={busy}
          onClose={() => setDialog(null)}
          onSave={(body) =>
            void write(
              () => editAnnouncement(dialog.notice.id, body),
              t('web_notices_updated'),
            ).then((ok) => ok && setDialog(null))
          }
        />
      ) : null}
      {dialog?.kind === 'remove' ? (
        <Sheet title={t('batch_notice_remove_title')} onClose={() => setDialog(null)}>
          <p className="meta">{t('batch_notice_remove_body')}</p>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-danger btn-money"
              disabled={busy}
              onClick={() =>
                void write(
                  () => removeAnnouncement(dialog.notice.id),
                  t('web_notices_removed'),
                ).then(() => setDialog(null))
              }
            >
              {t('batch_remove')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-money"
              onClick={() => setDialog(null)}
            >
              {t('action_cancel')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </>
  )
}

function EditSheet({
  notice,
  busy,
  onClose,
  onSave,
}: {
  notice: Notice
  busy: boolean
  onClose: () => void
  onSave: (body: string) => void
}) {
  const { t } = useT()
  const [text, setText] = useState(notice.body)
  return (
    <Sheet title={t('web_notices_edit_title')} onClose={onClose}>
      <div className="field">
        <label htmlFor="notice-edit">{t('batch_notice_label')}</label>
        <textarea
          id="notice-edit"
          value={text}
          maxLength={NOTICE_MAX}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="help">{t('batch_notice_help')}</span>
      </div>
      <div className="button-row">
        <button
          type="button"
          className="btn btn-primary btn-money"
          disabled={busy || text.trim() === '' || text.trim() === notice.body}
          onClick={() => onSave(text.trim())}
        >
          {t('batch_notice_send')}
        </button>
        <button type="button" className="btn btn-text btn-money" onClick={onClose}>
          {t('action_cancel')}
        </button>
      </div>
    </Sheet>
  )
}
