/**
 * Notifications: the list, and one message's own page.
 *
 * Opening a message marks it read and goes where it points (`targetFor`),
 * as Android's `InboxViewModel.select` does: marks to the marksheet, a
 * fee reminder to that seat's fees, a payment to check to the payment.
 * Everything else, and anything behind a lens other than the one being
 * looked through, opens the message's own page.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ago, formatClock, formatMonth, formatShortDate, type Lang } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { BellIcon } from '../../../ui/icons'
import { accountPaths } from '../../family/reader'
import { markAllRead, markRead, readInbox, readInboxItem } from './api'
import {
  OUTCOME_KEY,
  TITLE_KEY,
  classLine,
  inboxBody,
  inboxSubject,
  mapDetail,
  mapInbox,
  targetFor,
  type InboxContent,
  type InboxMessage,
} from './mappers'
import { inboxChanged, setUnreadCount } from './unread'
import './account.css'

/** "17 Oct, 9:10 am" in Dhaka, Western digits in both languages. */
export function formatDateTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    timeZone: 'Asia/Dhaka',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

/** "17 Oct, 4:00 pm": a class's day and start time, for a class-change line. */
export function formatClassWhen(isoDate: string, time: string, lang: Lang): string {
  return `${formatShortDate(isoDate, lang)}, ${formatClock(time, lang)}`
}

export function Inbox() {
  const { t, lang, message: messageText } = useT()
  const navigate = useNavigate()
  const { session } = useReadySession()
  const { resource, reload } = useResource((signal) => readInbox(signal).then(mapInbox), [])
  const [paymentsOnly, setPaymentsOnly] = useState(false)
  const [busy, setBusy] = useState(false)
  const [writeError, setWriteError] = useState<string | null>(null)

  useEffect(() => {
    if (resource.state === 'loaded') setUnreadCount(resource.data.unread)
  }, [resource])

  const line = (m: InboxMessage) =>
    inboxBody(
      m,
      t,
      (p) => formatMonth(p, lang),
      (d, time) => formatClassWhen(d, time, lang),
    )

  async function open(m: InboxMessage) {
    if (m.unread) {
      // Marked read before leaving, as Android does; a failure to mark
      // never blocks opening the thing it is about.
      await markRead(m.id).catch(() => undefined)
      inboxChanged()
    }
    navigate(targetFor(m, session.lens))
  }

  async function readAll() {
    setBusy(true)
    setWriteError(null)
    try {
      await markAllRead()
      inboxChanged()
      reload()
    } catch (e) {
      const key = (e as { messageKey?: string }).messageKey ?? 'error.unexpected'
      setWriteError(messageText(key))
    } finally {
      setBusy(false)
    }
  }

  let body: React.ReactNode
  let unread = 0
  if (resource.state === 'loading') {
    body = <Loading rows={4} />
  } else if (resource.state === 'failed') {
    body = <ErrorCard title={t('inbox_title')} error={resource.error} onRetry={reload} />
  } else {
    const { messages } = resource.data
    unread = resource.data.unread
    const hasPayments = messages.some((m) => m.kind === 'claim_to_verify')
    const shown =
      paymentsOnly && hasPayments ? messages.filter((m) => m.kind === 'claim_to_verify') : messages
    body =
      messages.length === 0 ? (
        <div className="card">
          <EmptyState title={t('inbox_empty_title')} body={t('inbox_empty_body')} />
        </div>
      ) : (
        <>
          {resource.error ? (
            <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
          ) : null}
          {hasPayments ? (
            <div className="chips" style={{ margin: '4px 0 12px' }}>
              <button
                type="button"
                className="chip chip-filter"
                aria-pressed={!paymentsOnly}
                onClick={() => setPaymentsOnly(false)}
              >
                {t('inbox_filter_all')}
              </button>
              <button
                type="button"
                className="chip chip-filter"
                aria-pressed={paymentsOnly}
                onClick={() => setPaymentsOnly(true)}
              >
                {t('inbox_filter_payments')}
              </button>
            </div>
          ) : null}
          <ul className="card flush list">
            {shown.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  className={m.unread ? 'row inbox-row unread' : 'row inbox-row'}
                  onClick={() => void open(m)}
                >
                  <span className="inbox-bell" aria-hidden="true">
                    <BellIcon size={20} />
                  </span>
                  <span className="grow">
                    <span className="title inbox-title">
                      {t(TITLE_KEY[m.kind], inboxSubject(m))}
                    </span>
                    {line(m) ? <span className="meta inbox-line">{line(m)}</span> : null}
                    <span className="meta inbox-line">{ago(m.sentAt, new Date(), t)}</span>
                  </span>
                  {m.unread ? (
                    <span className="inbox-dot">
                      <span className="visually-hidden">{t('web_account_unread')}</span>
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </>
      )
  }

  const canReadAll = resource.state === 'loaded' && !resource.error && unread > 0

  return (
    <>
      <TopBar
        title={t('inbox_title')}
        subtitle={unread > 0 ? t('web_account_unread_count', unread) : undefined}
        actions={
          canReadAll ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={busy}
              onClick={() => void readAll()}
            >
              {t('inbox_mark_all_read')}
            </button>
          ) : null
        }
      />
      {writeError ? (
        <div className="banner error" role="alert" style={{ marginBottom: 12 }}>
          {writeError}
        </div>
      ) : null}
      {body}
    </>
  )
}

export function InboxItem() {
  const { notificationId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(
    (signal) => readInboxItem(notificationId, signal).then(mapDetail),
    [notificationId],
  )

  // A message opened by its own address is read now too.
  useEffect(() => {
    if (
      resource.state === 'loaded' &&
      resource.data.state === 'available' &&
      resource.data.unread
    ) {
      void markRead(notificationId)
        .then(inboxChanged)
        .catch(() => undefined)
    }
  }, [resource, notificationId])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={2} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('inbox_detail_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.state === 'unavailable')
    body = (
      <div className="card">
        <EmptyState title={t('inbox_item_unavailable')} />
      </div>
    )
  else {
    const d = resource.data
    body = (
      <article className="card">
        <h2 className="inbox-detail-title">{t(TITLE_KEY[d.kind], inboxSubject(d))}</h2>
        {d.content ? <Content content={d.content} /> : null}
      </article>
    )
  }

  return (
    <>
      <TopBar title={t('inbox_detail_title')} back={accountPaths.inbox()} />
      {body}
    </>
  )
}

function Content({ content }: { content: InboxContent }) {
  const { t, lang } = useT()
  switch (content.kind) {
    case 'notice':
      return (
        <>
          <p className="inbox-notice">{content.body}</p>
          <p className="meta">{formatDateTime(content.postedAt, lang)}</p>
          {content.editedAt ? (
            <p className="meta">
              {t('inbox_notice_edited', formatDateTime(content.editedAt, lang))}
            </p>
          ) : null}
        </>
      )
    case 'exam':
      return (
        <dl className="kv">
          {content.cancelled ? (
            <dd className="danger" style={{ gridColumn: '1 / -1' }}>
              {t('inbox_exam_cancelled_line')}
            </dd>
          ) : null}
          <dt>{t('inbox_exam_date')}</dt>
          <dd>{formatShortDate(content.date, lang)}</dd>
          <dt>{t('inbox_exam_subject')}</dt>
          <dd>{content.subjectName}</dd>
          <dt>{t('inbox_exam_total')}</dt>
          <dd>{content.totalMarks}</dd>
          {content.topics.length > 0 ? (
            <>
              <dt>{t('inbox_exam_topics')}</dt>
              <dd>{content.topics.join(', ')}</dd>
            </>
          ) : null}
        </dl>
      )
    case 'payment':
      return (
        <dl className="kv">
          <dt>{t('inbox_payment_period')}</dt>
          <dd>{formatMonth(content.period, lang)}</dd>
          <dt>{t('inbox_payment_claimed')}</dt>
          <dd className="amount">{content.claimed.format()}</dd>
          {content.approved ? (
            <>
              <dt>{t('inbox_payment_approved_amount')}</dt>
              <dd className="amount">{content.approved.format()}</dd>
            </>
          ) : null}
          <dt>{t('inbox_payment_outcome')}</dt>
          <dd>{t(OUTCOME_KEY[content.outcome])}</dd>
          {content.reason ? (
            <>
              <dt>{t('inbox_payment_reason')}</dt>
              <dd>{content.reason}</dd>
            </>
          ) : null}
        </dl>
      )
    case 'class':
      return (
        <p className="inbox-notice">
          {classLine(content.classKind, content.change, t, (d, time) =>
            formatClassWhen(d, time, lang),
          )}
        </p>
      )
  }
}
