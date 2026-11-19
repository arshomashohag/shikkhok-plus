/**
 * The owner's join requests [H5]: the inbox, and one request with its
 * answers. Reached from the listing editor's "Join requests" row, which is
 * drawn only once the inbox read succeeds, and from a `hub_enquiry_received`
 * inbox message, under the current teacher workspace.
 *
 * **The server decides; the screens render.** The list is in the server's
 * order, open requests first. The guardian's contact is a `tel:` or
 * `mailto:` link only when the server sent one, which it does only while
 * the guardian chose to share it; otherwise it reads "Not shared". The
 * answers offered are exactly `outcomes_allowed`, and "Add as student"
 * opens the add-student form filled from the request, which answers
 * `added` once the student is saved (`people/NewStudent.tsx`). Every
 * refused answer reads in the server's words.
 *
 * Opened while join requests are switched off, or for a request that is
 * gone, either screen says so plainly, with no Retry.
 */
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatDateTime, formatPhone } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { ChevronIcon } from '../../../ui/icons'
import { paths } from '../paths'
import {
  ACTIONS,
  OWNER_OUTCOME_KEY,
  closeEnquiry,
  levelKey,
  listOwnerEnquiries,
  readOwnerEnquiry,
  type OwnerEnquiry,
  type Outcome,
} from './enquiries.api'
import { failureText, FailureBanner } from './hubUi'

/**
 * A read that failed for a reason trying again cannot fix — switched off,
 * not found — reads as the server's sentence; anything else is an error
 * card with Retry when the server says it can help.
 */
function Failed({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  const { t, message } = useT()
  if (!error.offline && !error.retryable)
    return (
      <div className="banner info" role="status">
        <p className="grow" style={{ margin: 0 }}>
          {message(error.messageKey)}
        </p>
      </div>
    )
  return <ErrorCard title={t('hub_enquiry_inbox_title')} error={error} onRetry={onRetry} />
}

/** Open, or the answer given, in the owner's words. */
function StatusChip({ enquiry }: { enquiry: OwnerEnquiry }) {
  const { t } = useT()
  if (enquiry.status === 'open')
    return <span className="chip chip-partial">{t('hub_enquiry_needs_answer')}</span>
  return enquiry.outcome ? (
    <span className="chip">{t(OWNER_OUTCOME_KEY[enquiry.outcome])}</span>
  ) : null
}

export function OwnerEnquiries() {
  const { t, lang } = useT()
  const { resource, reload } = useResource((signal) => listOwnerEnquiries(signal), [])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed') body = <Failed error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0) body = <EmptyState title={t('hub_enquiry_inbox_empty')} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list" aria-label={t('hub_enquiry_inbox_title')}>
          {resource.data.map((e) => (
            <li key={e.id}>
              <Link className="row" to={paths.hubEnquiry(e.id)}>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="title" style={{ overflowWrap: 'anywhere' }}>
                    {e.student_name}
                  </div>
                  <div className="meta" style={{ overflowWrap: 'anywhere' }}>
                    {t(levelKey(e.class_level))} · {e.batch_title ?? t('hub_enquiry_any_class')} ·{' '}
                    {formatDateTime(e.received_at, lang, true)}
                  </div>
                </div>
                <div className="end">
                  <StatusChip enquiry={e} />
                </div>
                <ChevronIcon />
              </Link>
            </li>
          ))}
        </ul>
      </>
    )

  return (
    <>
      <TopBar title={t('hub_enquiry_inbox_title')} back={paths.hub()} />
      {body}
    </>
  )
}

export function EnquiryDetail() {
  const { t } = useT()
  const { enquiryId = '' } = useParams()
  const { resource, reload } = useResource(
    (signal) => readOwnerEnquiry(enquiryId, signal),
    [enquiryId],
  )

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed') body = <Failed error={resource.error} onRetry={reload} />
  else body = <Detail key={resource.loadedAt.getTime()} initial={resource.data} />

  return (
    <>
      <TopBar title={t('hub_enquiry_detail_title')} back={paths.hubEnquiries()} />
      {body}
    </>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="meta">{label}</div>
      <div style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{children}</div>
    </div>
  )
}

function Detail({ initial }: { initial: OwnerEnquiry }) {
  const { t, message, lang } = useT()
  const navigate = useNavigate()
  const [enquiry, setEnquiry] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<{ text: string; retry: Outcome | null } | null>(null)
  const [snack, setSnack] = useState<string | null>(null)

  async function answer(outcome: Outcome) {
    setBusy(true)
    setFailure(null)
    try {
      setEnquiry(await closeEnquiry(enquiry.id, outcome))
      setSnack(t('hub_enquiry_closed_snack'))
    } catch (e) {
      const retryable = !(e instanceof ApiError) || e.offline || e.retryable
      setFailure({
        text: `${t('hub_enquiry_close_failed')} ${failureText(e, t, message)}`,
        retry: retryable ? outcome : null,
      })
    } finally {
      setBusy(false)
    }
  }

  function act(outcome: Outcome) {
    // Adding is the add-student form's to finish: it saves, then answers.
    if (outcome === 'added') navigate(paths.studentNew(enquiry.batch_id ?? undefined, enquiry.id))
    else void answer(outcome)
  }

  const offered = ACTIONS.filter((a) => enquiry.outcomes_allowed.includes(a.outcome))
  const phone = enquiry.guardian_phone
  const email = enquiry.guardian_email

  return (
    <>
      <div className="card">
        <p style={{ marginTop: 0 }}>
          <StatusChip enquiry={enquiry} />
        </p>
        <Field label={t('hub_enquiry_student_name')}>{enquiry.student_name}</Field>
        <Field label={t('hub_enquiry_class_level')}>{t(levelKey(enquiry.class_level))}</Field>
        {enquiry.message ? (
          <Field label={t('hub_enquiry_field_message')}>{enquiry.message}</Field>
        ) : null}
        <Field label={t('hub_enquiry_field_batch')}>
          {enquiry.batch_title ?? t('hub_enquiry_any_class')}
        </Field>
        <Field label={t('hub_enquiry_field_received')}>
          {formatDateTime(enquiry.received_at, lang, true)}
        </Field>
        <Field label={t('hub_enquiry_field_contact')}>
          {phone ? (
            <a href={`tel:${phone}`}>{formatPhone(phone)}</a>
          ) : email ? (
            <a href={`mailto:${email}`}>{email}</a>
          ) : (
            t('hub_enquiry_contact_not_shared')
          )}
        </Field>
      </div>

      {failure ? (
        <FailureBanner
          text={failure.text}
          onRetry={failure.retry ? () => void answer(failure.retry as Outcome) : undefined}
        />
      ) : null}

      {offered.length > 0 ? (
        <div className="button-row" style={{ marginTop: 16 }}>
          {offered.map((a) => (
            <button
              key={a.outcome}
              type="button"
              className={a.outcome === 'added' ? 'btn btn-primary' : 'btn btn-outline'}
              disabled={busy}
              onClick={() => act(a.outcome)}
            >
              {t(a.key)}
            </button>
          ))}
        </div>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
