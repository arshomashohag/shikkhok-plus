/**
 * The caller's own join requests [H5], whatever their lens: who each went
 * to, for whom, and where it stands, each with Withdraw. And the hook that
 * decides whether More shows the way here: only while the server lists at
 * least one request.
 *
 * **The server's codes, in words.** An open request is waiting; a closed
 * one reads the owner's answer from its outcome code, and a `call_us`
 * answer offers the owner's published number when the server sent one. A
 * request whose listing has gone has no owner name and reads as a teacher
 * no longer listed.
 *
 * **Withdrawal deletes completely**, open or answered, and is sent only
 * from the confirmation that says so. This list and the withdrawal are
 * never switched off, so a request sent before join requests were turned
 * off can still be withdrawn. A failed withdrawal keeps the row and offers
 * Retry when the server says it can help [TC-8].
 *
 * **Interests** [0049] are listed below the requests: each class the
 * caller shared their number for, whether the owner has seen it, and Take
 * back, which deletes it as a withdrawal does. Never switched off either.
 */
import { useState } from 'react'
import { ApiError } from '../../api/errors'
import { formatPhone, formatShortDate } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import {
  ConfirmSheet,
  EmptyState,
  ErrorCard,
  Loading,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../ui/components'
import { WarningIcon } from '../../ui/icons'
import {
  GUARDIAN_OUTCOME_KEY,
  levelKey,
  listMyEnquiries,
  listMyInterests,
  withdrawEnquiry,
  withdrawInterest,
  type MyEnquiry,
  type MyInterest,
} from '../teacher/hub/enquiries.api'
import { failureText } from '../teacher/hub/hubUi'

/** Whether More shows "My join requests": only once the server lists a request or an interest. */
export function useHasEnquiries(): boolean {
  const { resource } = useResource((signal) => listMyEnquiries(signal), [])
  const { resource: interests } = useResource((signal) => listMyInterests(signal), [])
  return (
    (resource.state === 'loaded' && resource.data.length > 0) ||
    (interests.state === 'loaded' && interests.data.length > 0)
  )
}

interface Failed {
  id: string
  text: string
  retryable: boolean
}

export function MyEnquiries() {
  const { t, message } = useT()
  const { resource, reload } = useResource((signal) => listMyEnquiries(signal), [])
  const [confirming, setConfirming] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failed | null>(null)
  const [snack, setSnack] = useState<string | null>(null)

  async function withdraw(id: string) {
    setBusy(true)
    setFailure(null)
    try {
      await withdrawEnquiry(id)
      setSnack(t('hub_enquiry_withdrawn'))
      reload()
    } catch (e) {
      setFailure({
        id,
        text: `${t('hub_enquiry_withdraw_failed')} ${failureText(e, t, message)}`,
        retryable: !(e instanceof ApiError) || e.offline || e.retryable,
      })
    } finally {
      setConfirming(null)
      setBusy(false)
    }
  }

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('hub_enquiry_mine_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0) body = <EmptyState title={t('hub_enquiry_mine_empty')} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list" aria-label={t('hub_enquiry_mine_title')}>
          {resource.data.map((e) => (
            <Request
              key={e.id}
              enquiry={e}
              busy={busy}
              failure={failure?.id === e.id ? failure : null}
              onWithdraw={() => setConfirming(e.id)}
            />
          ))}
        </ul>
      </>
    )

  return (
    <>
      <TopBar title={t('hub_enquiry_mine_title')} back="/more" />
      {body}
      <MyInterests />
      {confirming ? (
        <ConfirmSheet
          title={t('hub_enquiry_withdraw_title')}
          body={t('hub_enquiry_withdraw_body')}
          confirmLabel={t('hub_enquiry_withdraw')}
          busy={busy}
          onConfirm={() => void withdraw(confirming)}
          onCancel={() => setConfirming(null)}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}

function Request({
  enquiry: e,
  busy,
  failure,
  onWithdraw,
}: {
  enquiry: MyEnquiry
  busy: boolean
  failure: Failed | null
  onWithdraw: () => void
}) {
  const { t, lang } = useT()
  const phone = e.outcome === 'call_us' ? e.owner_contact_phone : null
  return (
    <li>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="title" style={{ overflowWrap: 'anywhere' }}>
            {e.owner_public_name ?? t('hub_enquiry_owner_unknown')}
          </div>
          {e.batch_title ? (
            <div className="meta" style={{ overflowWrap: 'anywhere' }}>
              {e.batch_title}
            </div>
          ) : null}
          <div className="meta">
            <span style={{ overflowWrap: 'anywhere' }}>{e.student_name}</span> ·{' '}
            {t(levelKey(e.class_level))} ·{' '}
            {t('hub_enquiry_sent_on', formatShortDate(e.sent_on, lang))}
          </div>
          {e.status === 'open' ? (
            <p style={{ margin: '4px 0 0' }}>
              <span className="chip">{t('hub_enquiry_status_open')}</span>
            </p>
          ) : e.outcome ? (
            <p style={{ margin: '4px 0 0' }}>{t(GUARDIAN_OUTCOME_KEY[e.outcome])}</p>
          ) : null}
          {phone ? (
            <p style={{ margin: '4px 0 0' }}>
              <a href={`tel:${phone}`}>{t('hub_enquiry_call_owner', formatPhone(phone))}</a>
            </p>
          ) : null}
        </div>
        <button
          type="button"
          className="btn btn-text btn-small"
          disabled={busy}
          onClick={onWithdraw}
        >
          {t('hub_enquiry_withdraw')}
        </button>
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span className="grow">{failure.text}</span>
          {failure.retryable ? (
            <button type="button" className="btn btn-text btn-small" onClick={onWithdraw}>
              {t('auth_retry')}
            </button>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

/** The classes the caller shared their number for [0049], each with Take back. */
function MyInterests() {
  const { t, message, lang } = useT()
  const { resource, reload } = useResource((signal) => listMyInterests(signal), [])
  const [confirming, setConfirming] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failed | null>(null)
  const [snack, setSnack] = useState<string | null>(null)

  async function withdraw(id: string) {
    setBusy(true)
    setFailure(null)
    try {
      await withdrawInterest(id)
      setSnack(t('web_hub_interest_withdrawn'))
      reload()
    } catch (e) {
      setFailure({
        id,
        text: `${t('web_hub_interest_failed')} ${failureText(e, t, message)}`,
        retryable: !(e instanceof ApiError) || e.offline || e.retryable,
      })
    } finally {
      setConfirming(null)
      setBusy(false)
    }
  }

  if (resource.state === 'loading') return null
  if (resource.state === 'failed')
    return (
      <ErrorCard title={t('web_hub_interest_mine_title')} error={resource.error} onRetry={reload} />
    )
  if (resource.data.length === 0) return null

  return (
    <section className="section">
      <div className="section-head">
        <h2>{t('web_hub_interest_mine_title')}</h2>
      </div>
      <ul className="card flush list" aria-label={t('web_hub_interest_mine_title')}>
        {resource.data.map((i: MyInterest) => (
          <li key={i.id}>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="title" style={{ overflowWrap: 'anywhere' }}>
                  {i.owner_public_name ?? t('hub_enquiry_owner_unknown')}
                </div>
                <div className="meta" style={{ overflowWrap: 'anywhere' }}>
                  {i.batch_title ?? t('web_hub_interest_class_gone')} ·{' '}
                  {t('web_hub_interest_shared_on', formatShortDate(i.shared_on, lang))}
                </div>
                <p style={{ margin: '4px 0 0' }}>
                  <span className="chip">
                    {i.status === 'open' ? t('web_hub_interest_open') : t('web_hub_interest_seen')}
                  </span>
                </p>
              </div>
              <button
                type="button"
                className="btn btn-text btn-small"
                disabled={busy}
                onClick={() => setConfirming(i.id)}
              >
                {t('web_hub_interest_withdraw')}
              </button>
            </div>
            {failure?.id === i.id ? (
              <div className="banner error" role="alert">
                <WarningIcon />
                <span className="grow">{failure.text}</span>
                {failure.retryable ? (
                  <button
                    type="button"
                    className="btn btn-text btn-small"
                    onClick={() => void withdraw(i.id)}
                  >
                    {t('auth_retry')}
                  </button>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {confirming ? (
        <ConfirmSheet
          title={t('web_hub_interest_withdraw_title')}
          body={t('web_hub_interest_withdraw_body')}
          confirmLabel={t('web_hub_interest_withdraw')}
          busy={busy}
          onConfirm={() => void withdraw(confirming)}
          onCancel={() => setConfirming(null)}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </section>
  )
}
