/**
 * One question and its answers. Opening it marks support's replies seen
 * (the server does that on read); More re-reads its badge when it is
 * next drawn, so nothing here asks again. A closed question can still be answered, which reopens it, and the page
 * says so before anyone types.
 */
import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router'
import { formatDateTime } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { ErrorCard, Loading, StaleBanner, TopBar } from '../../ui/components'
import { readTicket, replyToTicket } from './api'
import { MessageList, ReplyBox } from './Conversation'
import { BODY_MAX, mapThread, STATUS_CHIP, STATUS_KEY, type HelpThread as Thread } from './mappers'
import { helpPaths } from './paths'
import './help.css'

export function HelpThread() {
  const { ticketId = '' } = useParams()
  const { t, lang } = useT()
  const location = useLocation()
  const sent = (location.state as { sent?: boolean } | null)?.sent === true
  const { resource, reload } = useResource(() => readTicket(ticketId).then(mapThread), [ticketId])
  // The thread the server returned from the last reply, until a re-read.
  const [replied, setReplied] = useState<Thread | null>(null)

  useEffect(() => setReplied(null), [resource])

  async function reply(body: string) {
    setReplied(mapThread(await replyToTicket(ticketId, body)))
  }

  let content: React.ReactNode
  let title = t('help_thread_title')
  if (resource.state === 'loading') content = <Loading rows={3} />
  else if (resource.state === 'failed')
    content = <ErrorCard title={t('help_thread_title')} error={resource.error} onRetry={reload} />
  else {
    const thread = replied ?? resource.data
    const { ticket } = thread
    title = ticket.subject
    content = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        {sent ? (
          <div className="banner" role="status" style={{ marginBottom: 12 }}>
            {t('web_help_sent')}
          </div>
        ) : null}
        <div className="help-head chips">
          <span className={`chip ${STATUS_CHIP[ticket.status]}`}>
            {t(STATUS_KEY[ticket.status])}
          </span>
          <span className="meta">
            {t('web_help_asked_on', formatDateTime(ticket.createdAt, lang, true))}
          </span>
        </div>
        <MessageList
          messages={thread.messages}
          mine="requester"
          requesterLabel={t('help_from_you')}
        />
        {ticket.status === 'closed' ? (
          <div className="banner help-closed" role="note">
            {t('help_closed_notice')}
          </div>
        ) : null}
        <ReplyBox
          label={t('help_reply_label')}
          sendLabel={t('web_help_reply_send')}
          offlineText={t('web_help_send_offline')}
          max={BODY_MAX}
          onSend={reply}
        />
      </>
    )
  }

  return (
    <>
      <TopBar title={title} back={helpPaths.list()} />
      {content}
    </>
  )
}
