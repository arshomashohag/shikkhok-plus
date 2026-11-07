/**
 * Support's side of the help centre: everyone who has asked ("By
 * person"), and every ticket with a status filter ("All tickets"). Both
 * filters are the server's (`?status=`, `?ref=`); a person's tickets are
 * one person's reference, never a name lookup.
 */
import { Link, useSearchParams } from 'react-router'
import { ago } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, Loading, StaleBanner } from '../../ui/components'
import { STATUS_CHIP, type HelpStatus } from '../help/mappers'
import '../help/help.css'
import { readRequesters, readTickets } from './api'
import { AdminFailure, AdminFrame } from './AdminFrame'
import {
  ADMIN_STATUS_KEY,
  displayRef,
  mapAdminTickets,
  mapRequesters,
  PLATFORM_KEY,
  requesterDetail,
  requesterLabel,
  statusParam,
  type AdminTicket,
  type RequesterSummary,
} from './mappers'
import { adminPaths } from './paths'

/** "By person" and "All tickets", as links so each view has its own address. */
function HelpViews({ current }: { current: 'people' | 'tickets' }) {
  const { t } = useT()
  return (
    <div className="chips admin-views">
      <Link
        className="chip chip-filter"
        to={adminPaths.people()}
        aria-current={current === 'people' ? 'page' : undefined}
      >
        {t('web_admin_by_person')}
      </Link>
      <Link
        className="chip chip-filter"
        to={adminPaths.tickets()}
        aria-current={current === 'tickets' ? 'page' : undefined}
      >
        {t('web_admin_all_tickets')}
      </Link>
    </div>
  )
}

export function AdminRequesters() {
  const { t } = useT()
  const { resource, reload } = useResource(() => readRequesters().then(mapRequesters), [])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    return (
      <AdminFailure
        tab="help"
        title={t('web_admin_tab_help')}
        error={resource.error}
        onRetry={reload}
      />
    )
  else if (resource.data.length === 0)
    body = (
      <div className="card">
        <EmptyState title={t('web_admin_no_requesters')} />
      </div>
    )
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list">
          {resource.data.map((s) => (
            <RequesterRow key={s.requester.ref} summary={s} />
          ))}
        </ul>
      </>
    )

  return (
    <AdminFrame tab="help">
      <HelpViews current="people" />
      {body}
    </AdminFrame>
  )
}

function RequesterRow({ summary }: { summary: RequesterSummary }) {
  const { t } = useT()
  const { requester } = summary
  const detail = requesterDetail(requester, t)
  return (
    <li>
      <Link className="row help-row" to={adminPaths.tickets({ ref: requester.ref })}>
        <span className="grow">
          <span className="title">{requesterLabel(requester, t)}</span>
          {detail ? <span className="meta">{detail}</span> : null}
          <span className="meta">
            {t('web_admin_requester_counts', summary.tickets, summary.open)} ·{' '}
            {t('web_admin_last_activity', ago(summary.lastActivity, new Date(), t))}
          </span>
        </span>
        {summary.open > 0 ? (
          <span className="chip chip-verifying">
            {summary.open} {t('web_admin_status_open')}
          </span>
        ) : null}
      </Link>
    </li>
  )
}

const FILTERS: (HelpStatus | null)[] = [null, 'open', 'answered', 'closed']

export function AdminTickets() {
  const { t } = useT()
  const [params, setParams] = useSearchParams()
  const status = statusParam(params.get('status'))
  const ref = params.get('ref') || null
  const { resource, reload } = useResource(
    () => readTickets({ status: status ?? undefined, ref: ref ?? undefined }).then(mapAdminTickets),
    [status, ref],
  )

  function choose(next: HelpStatus | null) {
    const q = new URLSearchParams()
    if (next) q.set('status', next)
    if (ref) q.set('ref', ref)
    setParams(q, { replace: true })
  }

  if (resource.state === 'failed')
    return (
      <AdminFailure
        tab="help"
        title={t('web_admin_all_tickets')}
        error={resource.error}
        onRetry={reload}
      />
    )

  // Whose tickets these are, from the first one the server returned;
  // the reference alone when there are none.
  const first = resource.state === 'loaded' ? resource.data[0] : undefined
  const who = first ? requesterLabel(first.requester, t) : ref ? displayRef(ref) : null

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'loaded' && resource.data.length === 0)
    body = (
      <div className="card">
        <EmptyState title={t('web_admin_no_tickets')} />
      </div>
    )
  else if (resource.state === 'loaded')
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list">
          {resource.data.map((ticket) => (
            <TicketRow key={ticket.id} ticket={ticket} />
          ))}
        </ul>
      </>
    )

  return (
    <AdminFrame tab="help">
      <HelpViews current={ref ? 'people' : 'tickets'} />
      {ref ? (
        <div className="banner admin-person" role="status">
          <span className="grow">{t('web_admin_tickets_for', who ?? displayRef(ref))}</span>
          <Link className="btn btn-text btn-small" to={adminPaths.tickets({ status })}>
            {t('web_admin_clear_person')}
          </Link>
        </div>
      ) : null}
      <div className="chips admin-filters" role="group" aria-label={t('web_admin_col_status')}>
        {FILTERS.map((f) => (
          <button
            key={f ?? 'all'}
            type="button"
            className="chip chip-filter"
            aria-pressed={status === f}
            onClick={() => choose(f)}
          >
            {f ? t(ADMIN_STATUS_KEY[f]) : t('web_admin_filter_all')}
          </button>
        ))}
      </div>
      {body}
    </AdminFrame>
  )
}

function TicketRow({ ticket }: { ticket: AdminTicket }) {
  const { t } = useT()
  return (
    <li>
      <Link className="row help-row" to={adminPaths.ticket(ticket.id)}>
        <span className="grow">
          <span className="title">{ticket.subject}</span>
          <span className="meta admin-requester">{requesterLabel(ticket.requester, t)}</span>
          <span className="meta help-preview">{ticket.preview}</span>
          <span className="help-row-foot">
            <span className={`chip ${STATUS_CHIP[ticket.status]}`}>
              {t(ADMIN_STATUS_KEY[ticket.status])}
            </span>
            <span className="meta">
              {ticket.platform ? t(PLATFORM_KEY[ticket.platform]) : t('web_admin_platform_unknown')}{' '}
              · {t('web_admin_messages', ticket.messageCount)} ·{' '}
              {ago(ticket.updatedAt, new Date(), t)}
            </span>
          </span>
        </span>
      </Link>
    </li>
  )
}
