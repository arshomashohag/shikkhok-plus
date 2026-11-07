/**
 * Help centre: the questions this account has asked, most recently
 * active first, each with where it stands. Any role sees it; it is
 * reached from More.
 */
import { useEffect } from 'react'
import { Link } from 'react-router'
import { ago } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../ui/components'
import { PlusIcon } from '../../ui/icons'
import { listTickets } from './api'
import { mapList, STATUS_CHIP, STATUS_KEY, type HelpTicket } from './mappers'
import { setNewReplies } from './newReplies'
import { helpPaths } from './paths'
import './help.css'

export function HelpList() {
  const { t } = useT()
  const { resource, reload } = useResource(() => listTickets().then(mapList), [])

  useEffect(() => {
    if (resource.state === 'loaded' && !resource.error) setNewReplies(resource.data.newReplies)
  }, [resource])

  const ask = (
    <Link className="btn btn-primary" to={helpPaths.ask()}>
      <PlusIcon size={20} />
      {t('help_ask')}
    </Link>
  )

  let body: React.ReactNode
  let subtitle: string | undefined
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('help_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.tickets.length === 0)
    body = (
      <div className="card">
        <EmptyState title={t('help_empty_title')} body={t('help_empty_body')} action={ask} />
      </div>
    )
  else {
    const { tickets, newReplies } = resource.data
    subtitle = newReplies > 0 ? t('web_help_new_replies', newReplies) : undefined
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <div className="button-row help-ask">{ask}</div>
        <ul className="card flush list">
          {tickets.map((ticket) => (
            <TicketRow key={ticket.id} ticket={ticket} />
          ))}
        </ul>
      </>
    )
  }

  return (
    <>
      <TopBar title={t('help_title')} subtitle={subtitle} back="/more" />
      {body}
    </>
  )
}

function TicketRow({ ticket }: { ticket: HelpTicket }) {
  const { t } = useT()
  return (
    <li>
      <Link className="row help-row" to={helpPaths.ticket(ticket.id)}>
        <span className="grow">
          <span className="title">{ticket.subject}</span>
          <span className="meta help-preview">{ticket.preview}</span>
          <span className="help-row-foot">
            <span className={`chip ${STATUS_CHIP[ticket.status]}`}>
              {t(STATUS_KEY[ticket.status])}
            </span>
            {ticket.newReply ? (
              <span className="help-new">
                <span className="help-dot" aria-hidden="true" />
                {t('help_new_reply')}
              </span>
            ) : null}
            <span className="meta">
              {t('web_help_updated', ago(ticket.updatedAt, new Date(), t))}
            </span>
          </span>
        </span>
      </Link>
    </li>
  )
}
