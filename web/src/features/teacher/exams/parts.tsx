/**
 * Pieces both exam screens use: the publish bar, the mark history sheet,
 * and "Cancel exam" with its confirmation.
 */
import { useId, useState } from 'react'
import { ApiError } from '../../../api/errors'
import { ago, formatMark } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { Loading, Sheet } from '../../../ui/components'
import { cancelExam, readMarkHistory, publishExam } from './api'
import {
  canCancel,
  mapHistory,
  STATE_KEYS,
  type ExamItem,
  type ExamResults,
  type ResultRow,
} from './mappers'

/** The longest reason the server stores. */
export const CANCEL_REASON_MAX = 200

/**
 * "Cancel exam", offered only for an exam still on whose results are not
 * published. Nothing is sent until the teacher confirms in the sheet,
 * which says that every student and guardian will be told. A refusal is
 * shown in the server's own words.
 */
export function CancelExam({ exam, onCancelled }: { exam: ExamItem; onCancelled: () => void }) {
  const { t, message } = useT()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const id = useId()
  if (!canCancel(exam)) return null

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      const trimmed = reason.trim().slice(0, CANCEL_REASON_MAX)
      await cancelExam(exam.examId, { reason: trimmed === '' ? null : trimmed })
      setOpen(false)
      onCancelled()
    } catch (e) {
      setError(message(e instanceof ApiError ? e.messageKey : 'error.unexpected'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className="btn btn-text btn-small danger" onClick={() => setOpen(true)}>
        {t('exam_cancel_action')}
      </button>
      {open ? (
        <Sheet
          title={t('exam_cancel_confirm_title', exam.title)}
          subtitle={t('exam_cancel_confirm_body')}
          onClose={() => setOpen(false)}
        >
          {error ? (
            <div className="banner error" role="alert">
              {error}
            </div>
          ) : null}
          <div className="field">
            <label htmlFor={`${id}-reason`}>{t('exam_cancel_reason')}</label>
            <textarea
              id={`${id}-reason`}
              maxLength={CANCEL_REASON_MAX}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={() => setOpen(false)}>
              {t('exam_cancel_keep')}
            </button>
            <button
              type="button"
              className="btn btn-destructive grow"
              disabled={busy}
              onClick={() => void confirm()}
            >
              {t('exam_cancel_action')}
            </button>
          </div>
        </Sheet>
      ) : null}
    </>
  )
}

/** The server's code when a seat that could have sat the exam has no result. */
export const PUBLISH_INCOMPLETE_KEY = 'marks.publish.incomplete'

/**
 * Draft → review → publish. Families read none of an exam's marks until
 * it is published. What the bar says comes from the server: published or
 * not, and how many seats still lack a result (its own counts). Whether
 * publishing is allowed is decided by the server on the tap, and its
 * refusal is shown as it names it.
 */
export function PublishBar({
  results,
  onPublished,
  onRefused,
}: {
  results: ExamResults
  onPublished: () => void
  /** Called with the refusal's message key, e.g. to outline missing rows. */
  onRefused?: (messageKey: string) => void
}) {
  const { t, message } = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!results.writable || results.rows.length === 0) return null

  async function publish() {
    setBusy(true)
    setError(null)
    try {
      await publishExam(results.exam.examId)
      onPublished()
    } catch (e) {
      const key = e instanceof ApiError ? e.messageKey : 'error.unexpected'
      setError(message(key))
      onRefused?.(key)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="publish-bar" data-testid="publish-bar">
      {results.exam.published ? (
        <p className="banner">{t('mark_entry_published')}</p>
      ) : results.toEnter > 0 ? (
        <p className="meta">{t('mark_entry_to_enter', results.toEnter)}</p>
      ) : (
        <>
          <p className="meta">{t('mark_entry_publish_help')}</p>
          <button
            type="button"
            className="btn btn-primary btn-money"
            disabled={busy}
            onClick={() => void publish()}
          >
            {t('mark_entry_publish')}
          </button>
        </>
      )}
      {error ? (
        <div className="banner error" role="alert">
          {error}
        </div>
      ) : null}
    </div>
  )
}

/** "Marks recorded for <name>": every row ever written, the replaced ones struck through. */
export function HistorySheet({
  examId,
  row,
  onClose,
}: {
  examId: string
  row: ResultRow
  onClose: () => void
}) {
  const { t } = useT()
  const { resource } = useResource(
    () => readMarkHistory(examId, row.enrollmentId).then(mapHistory),
    [examId, row.enrollmentId],
  )
  return (
    <Sheet title={t('mark_history_title', row.displayName)} onClose={onClose}>
      {resource.state === 'loading' ? <Loading rows={2} /> : null}
      {resource.state === 'failed' ? (
        <p className="banner error" role="alert">
          {t('error_network_unreachable')}
        </p>
      ) : null}
      {resource.state === 'loaded' ? (
        <ul className="list">
          {resource.data.map((entry, i) => (
            <li key={i} className="row history-row">
              <span
                className={entry.superseded ? 'amount history-superseded' : 'amount'}
                style={{ minWidth: 64 }}
              >
                {entry.marks !== null ? formatMark(entry.marks) : t(STATE_KEYS[entry.state])}
              </span>
              <span className="meta grow">
                {entry.superseded
                  ? t('mark_history_replaced', ago(entry.recordedAt, new Date(), t))
                  : t('mark_history_current', ago(entry.recordedAt, new Date(), t))}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-text btn-money" onClick={onClose}>
          {t('action_close')}
        </button>
      </div>
    </Sheet>
  )
}
