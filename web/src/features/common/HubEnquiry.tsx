/**
 * Ask an owner, or one of its batches, to take a student [H5], opened from
 * a public page's "Ask to join" link: `/ui/hub-enquiry?owner=<slug>[&batch=<id>]`.
 *
 * **The target is the link's and the server's.** An owner slug is taken as
 * given (the server answers one not-found for every slug it will not take
 * requests for); a batch that is not a UUID says the link is not valid and
 * sends nothing. The form first reads the target, so the guardian sees who
 * would receive the request, and what "share" would share, before choosing.
 *
 * **Consent is a choice the guardian makes, never a default.** Sharing the
 * phone (or, for an account with none, the email) is two options with
 * neither chosen, and the adult-guardian declaration is an unticked box;
 * a send without either is stopped here, as the server would refuse it.
 * The share option starts with the word the server's contact refusal tells
 * the guardian to tick ("Share" / "শেয়ার").
 *
 * A request already open with this owner shows the way to it instead of a
 * form. Every refusal is the server's words; a dropped connection keeps
 * what was typed and offers Retry [TC-8]. Any signed-in reader may ask,
 * whatever their lens; a signed-out one is taken through sign-in and back
 * (`session/returnPath.ts`).
 */
import { useId, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError, UNEXPECTED_KEY } from '../../api/errors'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, TopBar } from '../../ui/components'
import { WarningIcon } from '../../ui/icons'
import { accountPaths } from '../family/reader'
import {
  MAX_MESSAGE,
  MAX_STUDENT_NAME,
  levelKey,
  readEnquiryTarget,
  sendEnquiry,
  type EnquiryTarget,
  type EnquiryWrite,
} from '../teacher/hub/enquiries.api'
import { CLASS_LEVELS } from '../teacher/hub/hub.mappers'

type ClassLevel = EnquiryWrite['class_level']

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** The link's owner and batch, or null when the link is not one this form takes. */
function linkOf(params: URLSearchParams): { owner: string; batch: string | null } | null {
  const owner = params.get('owner')
  const batch = params.get('batch')
  if (!owner) return null
  if (batch !== null && !UUID.test(batch)) return null
  return { owner, batch }
}

export function HubEnquiry() {
  const { t } = useT()
  const [params] = useSearchParams()
  const link = linkOf(params)
  return (
    <>
      <TopBar title={t('hub_enquiry_title')} back />
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

function Target({ owner, batch }: { owner: string; batch: string | null }) {
  const { t, message } = useT()
  const { resource, reload } = useResource(
    (signal) => readEnquiryTarget(owner, batch, signal),
    [owner, batch],
  )

  if (resource.state === 'loading') return <Loading rows={4} />
  if (resource.state === 'failed') {
    const e = resource.error
    // Switched off, or not taking requests: a plain "not available", not an error to retry.
    if (!e.offline && !e.retryable)
      return (
        <div className="banner info" role="status">
          <p className="grow" style={{ margin: 0 }}>
            {message(e.messageKey)}
          </p>
        </div>
      )
    return <ErrorCard title={t('hub_enquiry_title')} error={e} onRetry={reload} />
  }

  const target = resource.data
  return (
    <>
      <div className="card">
        <div className="title" style={{ overflowWrap: 'anywhere' }}>
          {t('hub_enquiry_to', target.owner_public_name)}
        </div>
        {target.batch_title ? (
          <div className="meta" style={{ overflowWrap: 'anywhere' }}>
            {target.batch_title}
          </div>
        ) : null}
      </div>
      {target.already_open ? (
        <div className="banner info" role="status">
          <div className="grow">
            <p style={{ margin: 0 }}>{t('hub_enquiry_already_open_title')}</p>
            <MyRequestsLink />
          </div>
        </div>
      ) : (
        <EnquiryForm owner={owner} batch={batch} target={target} />
      )}
    </>
  )
}

interface Failure {
  text: string
  retryable: boolean
  alreadyOpen: boolean
}

function EnquiryForm({
  owner,
  batch,
  target,
}: {
  owner: string
  batch: string | null
  target: EnquiryTarget
}) {
  const { t, message } = useT()
  const ids = useId()
  const [name, setName] = useState('')
  const [level, setLevel] = useState<ClassLevel | ''>('')
  const [note, setNote] = useState('')
  // Null until the guardian chooses: sharing is never a default.
  const [share, setShare] = useState<boolean | null>(null)
  const [declared, setDeclared] = useState(false)
  // Whether a send was tried, so what is missing is said only then.
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)

  const missing = {
    name: name.trim() === '',
    level: level === '',
    share: share === null,
    declared: !declared,
  }
  const complete = !Object.values(missing).some(Boolean)

  async function send() {
    if (busy || !complete || level === '' || share === null) return
    setBusy(true)
    setFailure(null)
    const text = note.trim()
    try {
      await sendEnquiry(owner, {
        student_name: name.trim(),
        class_level: level,
        ...(text ? { message: text } : {}),
        ...(batch ? { batch_id: batch } : {}),
        share_contact: share,
        declares_adult_guardian: true,
      })
      setSent(true)
    } catch (e) {
      // Offline can be retried; a refusal only when the server says so.
      const error = e instanceof ApiError ? e : null
      setFailure({
        text: `${t('hub_enquiry_failed')} ${message(error?.messageKey ?? UNEXPECTED_KEY)}`,
        retryable: !error || error.offline || error.retryable,
        alreadyOpen: error?.code === 'ENQUIRY_ALREADY_OPEN',
      })
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTried(true)
    void send()
  }

  if (sent)
    return (
      <div className="card form-page">
        <div className="banner info" role="status">
          <div className="grow">
            <p style={{ margin: 0 }}>{t('hub_enquiry_sent')}</p>
            <MyRequestsLink />
          </div>
        </div>
      </div>
    )

  const problem = (key: keyof typeof missing) => tried && missing[key]
  const shareLabel =
    target.contact_kind === 'phone' ? 'hub_enquiry_share_phone' : 'hub_enquiry_share_email'

  return (
    <form className="card form-page" onSubmit={onSubmit} noValidate>
      <div className="field">
        <label htmlFor={`${ids}-name`}>{t('hub_enquiry_student_name')}</label>
        <input
          id={`${ids}-name`}
          value={name}
          maxLength={MAX_STUDENT_NAME}
          autoComplete="off"
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
          aria-invalid={problem('name') || undefined}
          aria-describedby={problem('name') ? `${ids}-name-error` : undefined}
        />
        {problem('name') ? (
          <span id={`${ids}-name-error`} className="field-error">
            {t('hub_enquiry_name_required')}
          </span>
        ) : null}
      </div>

      <div className="field">
        <label htmlFor={`${ids}-level`}>{t('hub_enquiry_class_level')}</label>
        <select
          id={`${ids}-level`}
          value={level}
          disabled={busy}
          onChange={(e) => setLevel(e.target.value as ClassLevel | '')}
          aria-invalid={problem('level') || undefined}
          aria-describedby={problem('level') ? `${ids}-level-error` : undefined}
        >
          <option value="">{t('hub_enquiry_class_choose')}</option>
          {CLASS_LEVELS.map((l) => (
            <option key={l} value={l}>
              {t(levelKey(l))}
            </option>
          ))}
        </select>
        {problem('level') ? (
          <span id={`${ids}-level-error`} className="field-error">
            {t('hub_enquiry_class_required')}
          </span>
        ) : null}
      </div>

      <div className="field">
        <label htmlFor={`${ids}-message`}>{t('hub_enquiry_message')}</label>
        <textarea
          id={`${ids}-message`}
          rows={4}
          value={note}
          maxLength={MAX_MESSAGE}
          disabled={busy}
          onChange={(e) => setNote(e.target.value)}
          aria-describedby={`${ids}-message-count`}
        />
        <div className="row">
          <span className="grow" />
          <span id={`${ids}-message-count`} className="meta">
            {t('hub_report_note_count', note.length, MAX_MESSAGE)}
          </span>
        </div>
      </div>

      <fieldset
        className="field"
        aria-describedby={`${ids}-share-help${problem('share') ? ` ${ids}-share-error` : ''}`}
      >
        <legend>{t('hub_enquiry_share_question')}</legend>
        <label className="choice">
          <input
            type="radio"
            name={`${ids}-share`}
            checked={share === true}
            disabled={busy}
            onChange={() => setShare(true)}
          />
          <span style={{ overflowWrap: 'anywhere' }}>
            {t(shareLabel, target.owner_public_name)}
          </span>
        </label>
        <label className="choice">
          <input
            type="radio"
            name={`${ids}-share`}
            checked={share === false}
            disabled={busy}
            onChange={() => setShare(false)}
          />
          <span>{t('hub_enquiry_share_none')}</span>
        </label>
        <span id={`${ids}-share-help`} className="help">
          {t('hub_enquiry_share_help')}
        </span>
        {problem('share') ? (
          <span id={`${ids}-share-error`} className="field-error">
            {t('hub_enquiry_share_required')}
          </span>
        ) : null}
      </fieldset>

      <div className="field">
        <label className="choice">
          <input
            type="checkbox"
            checked={declared}
            disabled={busy}
            onChange={(e) => setDeclared(e.target.checked)}
            aria-invalid={problem('declared') || undefined}
            aria-describedby={problem('declared') ? `${ids}-declared-error` : undefined}
          />
          <span>{t('hub_enquiry_declaration')}</span>
        </label>
        {problem('declared') ? (
          <span id={`${ids}-declared-error`} className="field-error">
            {t('hub_enquiry_declaration_required')}
          </span>
        ) : null}
      </div>

      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <div className="grow">
            <div>{failure.text}</div>
            {failure.alreadyOpen ? <MyRequestsLink /> : null}
          </div>
          {failure.retryable ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={busy}
              onClick={() => void send()}
            >
              {t('auth_retry')}
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="button-row">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? t('hub_enquiry_sending') : t('hub_enquiry_send')}
        </button>
      </div>
    </form>
  )
}
