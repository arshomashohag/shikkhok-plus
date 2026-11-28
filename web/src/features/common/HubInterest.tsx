/**
 * Share interest in one listed batch [0049], opened from a public batch
 * page's "I'm interested" link: `/ui/hub-interest?owner=<slug>&batch=<id>`.
 *
 * **Nothing is typed.** The family confirms sharing the phone number on
 * their account with whoever runs the batch, so they can be called when a
 * seat opens, after ticking the same adult-guardian declaration a join
 * request needs: the box starts unticked, and nothing is sent without it. The screen first reads the target, so the family sees who
 * would receive the number before choosing; the target never carries the
 * number itself, only whether the account has one. An account without one
 * is sent to add it first.
 *
 * Sharing again changes nothing, and an interest already shared shows the
 * way to the family's own list, where it can be taken back. Every refusal
 * is the server's words; a dropped connection offers Retry [TC-8]. A
 * signed-out reader is taken through sign-in and back
 * (`session/returnPath.ts`).
 */
import { useId, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from '../../api/errors'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, TopBar } from '../../ui/components'
import { accountPaths } from '../family/reader'
import { securityPaths } from '../account/security/paths'
import {
  readInterestTarget,
  shareInterest,
  type InterestTarget,
} from '../teacher/hub/enquiries.api'
import { failureText, FailureBanner } from '../teacher/hub/hubUi'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** The link's owner and batch, or null when the link is not one this screen takes. */
function linkOf(params: URLSearchParams): { owner: string; batch: string } | null {
  const owner = params.get('owner')
  const batch = params.get('batch')
  if (!owner || batch === null || !UUID.test(batch)) return null
  return { owner, batch }
}

export function HubInterest() {
  const { t } = useT()
  const [params] = useSearchParams()
  const link = linkOf(params)
  return (
    <>
      <TopBar title={t('web_hub_interest_title')} back />
      {link ? (
        <Target owner={link.owner} batch={link.batch} />
      ) : (
        <EmptyState title={t('hub_report_link_invalid')} />
      )}
    </>
  )
}

function MyRequestsLink() {
  const { t } = useT()
  return <Link to={accountPaths.myEnquiries()}>{t('hub_enquiry_mine_link')}</Link>
}

function Target({ owner, batch }: { owner: string; batch: string }) {
  const { t, message } = useT()
  const { resource, reload } = useResource(
    (signal) => readInterestTarget(owner, batch, signal),
    [owner, batch],
  )

  if (resource.state === 'loading') return <Loading rows={3} />
  if (resource.state === 'failed') {
    const e = resource.error
    // Switched off, or not taking interest: a plain "not available", not an error to retry.
    if (!e.offline && !e.retryable)
      return (
        <div className="banner info" role="status">
          <p className="grow" style={{ margin: 0 }}>
            {message(e.messageKey)}
          </p>
        </div>
      )
    return <ErrorCard title={t('web_hub_interest_title')} error={e} onRetry={reload} />
  }

  const target = resource.data
  return (
    <>
      <div className="card">
        <div className="title" style={{ overflowWrap: 'anywhere' }}>
          {t('web_hub_interest_to', target.owner_public_name)}
        </div>
        <div className="meta" style={{ overflowWrap: 'anywhere' }}>
          {target.batch_title}
        </div>
      </div>
      <Share owner={owner} batch={batch} target={target} />
    </>
  )
}

function Share({ owner, batch, target }: { owner: string; batch: string; target: InterestTarget }) {
  const { t, message } = useT()
  const [busy, setBusy] = useState(false)
  const [shared, setShared] = useState(target.already_shared)
  const [justShared, setJustShared] = useState(false)
  const [declared, setDeclared] = useState(false)
  const [tried, setTried] = useState(false)
  const ids = useId()
  const [failure, setFailure] = useState<{ text: string; retryable: boolean } | null>(null)

  if (shared)
    return (
      <div className="banner info" role="status">
        <div className="grow">
          <p style={{ margin: 0 }}>
            {justShared
              ? t('web_hub_interest_shared', target.owner_public_name)
              : t('web_hub_interest_already')}
          </p>
          <MyRequestsLink />
        </div>
      </div>
    )

  if (!target.has_phone)
    return (
      <div className="banner info" role="status">
        <div className="grow">
          <p style={{ margin: 0 }}>{t('hub_interest_needs_phone')}</p>
          <Link to={securityPaths.addContact('phone')}>{t('web_hub_interest_add_phone')}</Link>
        </div>
      </div>
    )

  async function share() {
    setTried(true)
    if (!declared) return
    setBusy(true)
    setFailure(null)
    try {
      await shareInterest(owner, batch)
      setJustShared(true)
      setShared(true)
    } catch (e) {
      setFailure({
        text: `${t('web_hub_interest_failed')} ${failureText(e, t, message)}`,
        retryable: !(e instanceof ApiError) || e.offline || e.retryable,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <p style={{ overflowWrap: 'anywhere' }}>
        {t('web_hub_interest_explain', target.owner_public_name)}
      </p>
      <div className="field">
        <label className="choice">
          <input
            type="checkbox"
            checked={declared}
            disabled={busy}
            onChange={(e) => setDeclared(e.target.checked)}
            aria-invalid={(tried && !declared) || undefined}
            aria-describedby={tried && !declared ? `${ids}-declared-error` : undefined}
          />
          <span>{t('hub_enquiry_declaration')}</span>
        </label>
        {tried && !declared ? (
          <span id={`${ids}-declared-error`} className="field-error">
            {t('web_hub_interest_declaration_required')}
          </span>
        ) : null}
      </div>
      {failure ? (
        <FailureBanner
          text={failure.text}
          onRetry={failure.retryable ? () => void share() : undefined}
        />
      ) : null}
      <div className="button-row">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void share()}
        >
          {t('web_hub_interest_share')}
        </button>
      </div>
    </>
  )
}
