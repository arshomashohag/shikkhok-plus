/**
 * One ticket, as support sees it: who asked (within the administrator
 * boundary: a teacher's name, otherwise a role and a reference), which
 * app it came from, the thread, a reply box and Close or Reopen. Every
 * action is a write and needs a connection; the server's answer replaces
 * what is on screen.
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { formatDateTime } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { Loading, StaleBanner } from '../../ui/components'
import { MessageList, ReplyBox, writeErrorText } from '../help/Conversation'
import { BODY_MAX, STATUS_CHIP } from '../help/mappers'
import { readAdminTicket, replyAsSupport, setTicketStatus } from './api'
import { AdminFailure, AdminFrame } from './AdminFrame'
import {
  ADMIN_STATUS_KEY,
  mapAdminThread,
  PLATFORM_KEY,
  requesterDetail,
  requesterLabel,
  type AdminThread,
} from './mappers'
import { adminPaths } from './paths'

export function AdminTicketView() {
  const { ticketId = '' } = useParams()
  const { t, lang, message } = useT()
  const { resource, reload } = useResource(
    () => readAdminTicket(ticketId).then(mapAdminThread),
    [ticketId],
  )
  // The thread the server returned from the last action, until a re-read.
  const [changed, setChanged] = useState<AdminThread | null>(null)
  const [busy, setBusy] = useState(false)
  const [statusError, setStatusError] = useState<{ text: string; retryable: boolean } | null>(null)
  useEffect(() => setChanged(null), [resource])

  if (resource.state === 'loading')
    return (
      <AdminFrame tab="help" title={t('web_admin_ticket_title')} back={adminPaths.tickets()}>
        <Loading rows={3} />
      </AdminFrame>
    )
  if (resource.state === 'failed')
    return (
      <AdminFailure
        tab="help"
        title={t('web_admin_ticket_title')}
        error={resource.error}
        onRetry={reload}
      />
    )

  const thread = changed ?? resource.data
  const { ticket } = thread
  const label = requesterLabel(ticket.requester, t)
  const detail = requesterDetail(ticket.requester, t)
  const next = ticket.status === 'closed' ? 'open' : 'closed'

  async function reply(body: string) {
    setChanged(mapAdminThread(await replyAsSupport(ticketId, body)))
  }

  async function changeStatus() {
    setBusy(true)
    setStatusError(null)
    try {
      setChanged(mapAdminThread(await setTicketStatus(ticketId, next)))
    } catch (e) {
      setStatusError(writeErrorText(e, t('web_admin_action_offline'), message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AdminFrame tab="help" title={ticket.subject} back={adminPaths.tickets()}>
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      <div className="card admin-ticket-head">
        <dl className="kv">
          <dt>{t('web_admin_asked_by')}</dt>
          <dd>
            <span className="title">{label}</span>
            {detail ? <span className="meta admin-block">{detail}</span> : null}
          </dd>
          <dt>{t('web_admin_asked_from')}</dt>
          <dd>
            {ticket.platform ? t(PLATFORM_KEY[ticket.platform]) : t('web_admin_platform_unknown')}
          </dd>
          <dt>{t('web_admin_col_status')}</dt>
          <dd>
            <span className={`chip ${STATUS_CHIP[ticket.status]}`}>
              {t(ADMIN_STATUS_KEY[ticket.status])}
            </span>
          </dd>
          <dt>{t('web_admin_asked_at')}</dt>
          <dd>{formatDateTime(ticket.createdAt, lang, true)}</dd>
        </dl>
        <div className="button-row">
          <button
            type="button"
            className={next === 'closed' ? 'btn btn-outline btn-small' : 'btn btn-tonal btn-small'}
            disabled={busy}
            onClick={() => void changeStatus()}
          >
            {next === 'closed' ? t('web_admin_close') : t('web_admin_reopen')}
          </button>
        </div>
        {statusError ? (
          <div className="banner error help-error" role="alert">
            <span className="grow">{statusError.text}</span>
            {statusError.retryable ? (
              <button
                type="button"
                className="btn btn-outline btn-small"
                disabled={busy}
                onClick={() => void changeStatus()}
              >
                {t('auth_retry')}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      <MessageList messages={thread.messages} mine="support" requesterLabel={label} />
      <ReplyBox
        label={t('web_admin_reply_label')}
        sendLabel={t('web_admin_reply_send')}
        offlineText={t('web_help_send_offline')}
        max={BODY_MAX}
        onSend={reply}
      />
    </AdminFrame>
  )
}
