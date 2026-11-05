/**
 * "Record payment": the teacher records money received by hand for one
 * seat. The web counterpart of `RecordPaymentSheetView.kt`.
 *
 * The amount starts at what the server says is owed; channel defaults to
 * cash. The carry-or-waive question is the approval sheet's own
 * ({@link DispositionChoice}), asked only when the typed amount is below
 * what is owed. One retry key per opened sheet, so a resend after a lost
 * response is replayed by the server rather than recorded twice.
 */
import { useId, useState } from 'react'
import { ApiError } from '../../../api/errors'
import type { Money } from '../../../core/money'
import { useT } from '../../../i18n/i18n'
import { Sheet } from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import { mutationId } from '../classes/api'
import { recordPayment } from './api'
import { DispositionChoice } from './ApprovalSheet'
import {
  CASH,
  RECORD_CHANNELS,
  RECORD_NOTE_MAX,
  RECORD_REFERENCE_MAX,
  openRecord,
  recordBody,
  recordState,
  typeRecordAmount,
  type RecordInput,
} from './record'

export function RecordPaymentSheet({
  enrollmentId,
  name,
  owed,
  onClose,
  onRecorded,
}: {
  enrollmentId: string
  /** The seat's display name, for the subtitle. */
  name?: string
  /** What the seat owes now, as the server computed it. */
  owed: Money
  onClose: () => void
  /** Called with the amount recorded, in words, once the server accepted it. */
  onRecorded: (amount: string) => void
}) {
  const { t, message } = useT()
  const [input, setInput] = useState<RecordInput>(() => openRecord(owed, mutationId()))
  const [busy, setBusy] = useState(false)
  const [errorText, setErrorText] = useState<string | null>(null)
  const id = useId()
  const state = recordState(owed, input)
  const body = recordBody(owed, input)

  const comparison =
    state.side === 'exact'
      ? t('verify_line_exact')
      : state.side === 'short'
        ? t('verify_line_short_plain')
        : state.side === 'over'
          ? t('verify_line_over_plain')
          : null

  async function confirm() {
    if (!body || !state.received) return
    setBusy(true)
    setErrorText(null)
    try {
      await recordPayment(enrollmentId, body)
      onRecorded(state.received.format())
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setErrorText(
        error?.offline
          ? t('web_money_offline_nothing_changed')
          : message(error?.messageKey ?? 'error.unexpected'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('fees_record_title')} subtitle={name} onClose={onClose}>
      {errorText ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{errorText}</span>
        </div>
      ) : null}

      <p className="meta" style={{ marginTop: 0 }}>
        {t('fees_record_owed', owed.format())}
      </p>

      <div className="field">
        <label htmlFor={`${id}-amount`}>{t('verify_received_amount')}</label>
        <div className="money-input">
          <span aria-hidden="true">৳</span>
          <input
            id={`${id}-amount`}
            inputMode="decimal"
            autoComplete="off"
            value={input.typed}
            onChange={(e) => setInput((i) => typeRecordAmount(owed, i, e.target.value))}
            aria-invalid={input.typed !== '' && state.received === null ? true : undefined}
          />
        </div>
        {input.typed !== '' && state.received === null ? (
          <span className="field-error">{t('fee_invalid')}</span>
        ) : comparison ? (
          <span className={state.side === 'exact' ? 'meta accent' : 'meta danger'}>
            {comparison}
          </span>
        ) : null}
      </div>

      {state.needsDisposition ? (
        <DispositionChoice
          value={input.disposition}
          difference={null}
          onChoose={(disposition) => setInput((i) => ({ ...i, disposition }))}
        />
      ) : null}

      <div className="field">
        <label htmlFor={`${id}-channel`}>{t('fees_record_channel')}</label>
        <select
          id={`${id}-channel`}
          value={input.channel}
          onChange={(e) => setInput((i) => ({ ...i, channel: e.target.value }))}
        >
          {RECORD_CHANNELS.map((channel) => (
            <option key={channel} value={channel}>
              {channel === CASH ? t('fees_record_channel_cash') : channel}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor={`${id}-reference`}>{t('fees_record_reference')}</label>
        <input
          id={`${id}-reference`}
          autoComplete="off"
          maxLength={RECORD_REFERENCE_MAX}
          value={input.reference}
          onChange={(e) => setInput((i) => ({ ...i, reference: e.target.value }))}
        />
      </div>

      <div className="field">
        <label htmlFor={`${id}-note`}>{t('fees_record_note')}</label>
        <textarea
          id={`${id}-note`}
          maxLength={RECORD_NOTE_MAX}
          value={input.note}
          onChange={(e) => setInput((i) => ({ ...i, note: e.target.value }))}
        />
      </div>

      <div className="button-row">
        <button
          type="button"
          className="btn btn-primary btn-money"
          disabled={body === null || busy}
          onClick={() => void confirm()}
        >
          {t('fees_record_confirm', state.received?.format() ?? input.typed)}
        </button>
        <button type="button" className="btn btn-text btn-money" onClick={onClose}>
          {t('action_cancel')}
        </button>
      </div>
    </Sheet>
  )
}
