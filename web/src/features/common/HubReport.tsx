/**
 * Report a public hub page, opened from the page's "Report this page"
 * link: `/ui/hub-report?kind=owner_listing|batch_listing&id=<uuid>`. The
 * id is what `POST /v1/hub/reports` takes: the owner's id for an owner
 * listing, the batch's for a batch listing.
 *
 * **The target is the link's and only the link's.** A kind other than
 * the two listing kinds, or an id that is not a UUID, says the link is
 * not valid and sends nothing; the reader cannot retarget a report here.
 *
 * Any signed-in reader may report, whatever their lens; a signed-out one
 * is taken through sign-in and back (`session/returnPath.ts`). The reason
 * is the server's closed vocabulary, the note optional and at most 500
 * characters. A refusal is the server's words (`hub.report_*`); a dropped
 * connection keeps the reason and the note and offers Retry [TC-8].
 */
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { fileHubReport, type Schemas } from '../../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { EmptyState, TopBar } from '../../ui/components'
import { WarningIcon } from '../../ui/icons'

type Request = Schemas['HubReportRequest']
type Kind = 'owner_listing' | 'batch_listing'
type Reason = Request['reason']

/** The server's limit on the note (`HubReportRequest.note`). */
const NOTE_MAX = 500

/** In the order a reader weighs them: the gravest first, "Something else" last. */
const REASONS: readonly Reason[] = [
  'child_safety',
  'personal_info',
  'abusive',
  'fake',
  'misleading',
  'other',
]

const KINDS: Record<Kind, string> = {
  owner_listing: 'hub_report_target_owner',
  batch_listing: 'hub_report_target_batch',
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** The link's target, or null when either half is not one this screen reports. */
function targetOf(params: URLSearchParams): { kind: Kind; id: string } | null {
  const kind = params.get('kind')
  const id = params.get('id')
  if ((kind !== 'owner_listing' && kind !== 'batch_listing') || !id || !UUID.test(id)) return null
  return { kind, id }
}

export function HubReport() {
  const { t } = useT()
  const [params] = useSearchParams()
  const target = targetOf(params)
  return (
    <>
      <TopBar title={t('hub_report_title')} back />
      {target ? (
        <ReportForm kind={target.kind} id={target.id} />
      ) : (
        <EmptyState title={t('hub_report_link_invalid')} body={t('hub_report_link_invalid_body')} />
      )}
    </>
  )
}

function ReportForm({ kind, id }: { kind: Kind; id: string }) {
  const { t, message } = useT()
  const [reason, setReason] = useState<Reason | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [failure, setFailure] = useState<{ text: string; retryable: boolean } | null>(null)

  async function send() {
    if (!reason || busy) return
    setBusy(true)
    setFailure(null)
    const trimmed = note.trim()
    try {
      await fileHubReport({
        target_kind: kind,
        target_id: id,
        reason,
        ...(trimmed ? { note: trimmed } : {}),
      })
      setSent(true)
    } catch (e) {
      // Offline can be retried; a refusal only when the server says so.
      const error = e instanceof ApiError ? e : null
      setFailure({
        text: `${t('hub_report_failed')} ${message(error?.messageKey ?? UNEXPECTED_KEY)}`,
        retryable: !error || error.offline || error.retryable,
      })
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send()
  }

  if (sent)
    return (
      <div className="card form-page">
        <div className="banner info" role="status">
          {t('hub_report_sent')}
        </div>
      </div>
    )

  return (
    <form className="card form-page" onSubmit={onSubmit} noValidate>
      <p className="meta">{t(KINDS[kind])}</p>
      <fieldset className="field">
        <legend>{t('hub_report_reason_question')}</legend>
        {REASONS.map((r) => (
          <label key={r} className="choice">
            <input
              type="radio"
              name="reason"
              value={r}
              checked={reason === r}
              disabled={busy}
              onChange={() => setReason(r)}
            />
            <span>{t(`hub_report_reason_${r}`)}</span>
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label htmlFor="hub-report-note">{t('hub_report_note_label')}</label>
        <textarea
          id="hub-report-note"
          rows={4}
          value={note}
          maxLength={NOTE_MAX}
          disabled={busy}
          onChange={(e) => setNote(e.target.value)}
          aria-describedby="hub-report-note-help hub-report-note-count"
        />
        <div className="row">
          <span id="hub-report-note-help" className="help grow">
            {t('hub_report_note_help')}
          </span>
          <span id="hub-report-note-count" className="meta">
            {t('hub_report_note_count', note.length, NOTE_MAX)}
          </span>
        </div>
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span className="grow">{failure.text}</span>
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
        <button type="submit" className="btn btn-primary" disabled={busy || !reason}>
          {busy ? t('hub_report_sending') : t('hub_report_send')}
        </button>
      </div>
    </form>
  )
}
