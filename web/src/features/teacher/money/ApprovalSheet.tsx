/**
 * T4 "Partial · carry forward or waive": approve an amount other than, or
 * as well as, what was reported. The web counterpart of
 * `ApprovalSheetView.kt`, including the case the first web slice refused:
 * a payment shared by several children, where the teacher names the child
 * who carries a shortfall or receives the extra as credit.
 */
import { useId, useState } from 'react'
import type { Schemas } from '../../../api/endpoints'
import { formatMonth } from '../../../core/format'
import { useT } from '../../../i18n/i18n'
import { Sheet } from '../../../ui/components'
import { WarningIcon } from '../../../ui/icons'
import type { PaymentReview } from '../mappers'
import {
  REVIEW_NOTE_MAX,
  sheetBody,
  sheetState,
  typeAmount,
  type Disposition,
  type SheetInput,
} from './review'

export function ApprovalSheet({
  review,
  initial,
  correcting,
  busy,
  errorText,
  onClose,
  onConfirm,
}: {
  review: PaymentReview
  initial: SheetInput
  correcting: boolean
  busy: boolean
  /** The server's refusal of the last attempt, already in words. */
  errorText: string | null
  onClose: () => void
  onConfirm: (body: Schemas['PaymentApprovalRequest'], received: string) => void
}) {
  const { t, lang } = useT()
  const [input, setInput] = useState<SheetInput>(initial)
  const state = sheetState(review, input)
  const body = sheetBody(review, input, correcting)
  const amountId = useId()
  const difference = state.shownDifference?.format() ?? null

  const comparison =
    state.side === 'exact'
      ? t('verify_line_exact')
      : state.side === 'short'
        ? difference
          ? t('verify_line_short', difference)
          : t('verify_line_short_plain')
        : state.side === 'over'
          ? difference
            ? t('verify_line_over', difference)
            : t('verify_line_over_plain')
          : null

  const childHeading =
    state.side === 'over'
      ? t('verify_credit_to')
      : input.disposition === 'waived'
        ? t('verify_waive_for')
        : difference
          ? t('verify_carry_onto', difference)
          : t('verify_carry_onto_plain')

  const choose = (disposition: Disposition) => setInput((i) => ({ ...i, disposition }))

  return (
    <Sheet
      title={
        state.side === 'short' && state.received
          ? t('verify_sheet_title_partial', state.received.format(), review.owedTogether.format())
          : t('verify_sheet_title')
      }
      subtitle={t('verify_sheet_sub', review.batchName)}
      onClose={onClose}
    >
      {errorText ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{errorText}</span>
        </div>
      ) : null}

      <dl className="money-lines">
        {review.children.map((c) => (
          <div key={c.enrollmentId}>
            <dt>{t('verify_child_line', c.displayName, formatMonth(c.period, lang))}</dt>
            <dd className="amount">{c.owed.format()}</dd>
          </div>
        ))}
        <div className="money-lines-total">
          <dt>{t('verify_owed_together')}</dt>
          <dd className="amount">{review.owedTogether.format()}</dd>
        </div>
      </dl>

      <div className="field">
        <label htmlFor={amountId}>{t('verify_received_amount')}</label>
        <div className="money-input">
          <span aria-hidden="true">৳</span>
          <input
            id={amountId}
            inputMode="decimal"
            autoComplete="off"
            value={input.typed}
            onChange={(e) => setInput((i) => typeAmount(review, i, e.target.value))}
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
        <DispositionChoice value={input.disposition} difference={difference} onChoose={choose} />
      ) : null}

      {state.needsChild ? (
        <fieldset className="field">
          <legend>{childHeading}</legend>
          {review.children.map((c) => (
            <label key={c.enrollmentId} className="choice">
              <input
                type="radio"
                name="bearer"
                checked={input.childId === c.enrollmentId}
                onChange={() => setInput((i) => ({ ...i, childId: c.enrollmentId }))}
              />
              <span>
                <span className="title">{c.displayName}</span>
                <br />
                <span className="meta">
                  {t(
                    'verify_marked_paid',
                    review.children
                      .filter((o) => o.enrollmentId !== c.enrollmentId)
                      .map((o) => o.displayName)
                      .join(', '),
                  )}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}

      <div className="field">
        <label htmlFor={`${amountId}-note`}>{t('verify_note_to_them')}</label>
        <textarea
          id={`${amountId}-note`}
          maxLength={REVIEW_NOTE_MAX}
          value={input.note}
          onChange={(e) => setInput((i) => ({ ...i, note: e.target.value }))}
        />
      </div>

      <div className="button-row">
        <button
          type="button"
          className="btn btn-primary btn-money"
          disabled={body === null || busy}
          onClick={() => body && state.received && onConfirm(body, state.received.format())}
        >
          {t('verify_partial_confirm', state.received?.format() ?? input.typed)}
        </button>
        <button type="button" className="btn btn-text btn-money" onClick={onClose}>
          {t('action_cancel')}
        </button>
      </div>
    </Sheet>
  )
}

/**
 * Carry forward or waive: the question a short amount must answer [BR5.4].
 * Neither is preselected, because the two have opposite consequences for
 * the family. Shared by this sheet and the "Record payment" sheet, so the
 * teacher reads the same choice in the same words on both.
 */
export function DispositionChoice({
  value,
  difference,
  onChoose,
}: {
  value: Disposition | null
  /** The shortfall in words, when the server has said what it is. */
  difference: string | null
  onChoose: (disposition: Disposition) => void
}) {
  const { t } = useT()
  const name = useId()
  return (
    <fieldset className="field">
      <legend className="visually-hidden">{t('fees_verification_disposition_required')}</legend>
      <label className="choice">
        <input
          type="radio"
          name={name}
          checked={value === 'carried'}
          onChange={() => onChoose('carried')}
        />
        <span>
          <span className="title">{t('verify_carry_forward')}</span>
          <br />
          <span className="meta">
            {difference
              ? t('verify_carry_forward_amount', difference)
              : t('verify_carry_forward_body')}
          </span>
        </span>
      </label>
      <label className="choice">
        <input
          type="radio"
          name={name}
          checked={value === 'waived'}
          onChange={() => onChoose('waived')}
        />
        <span>
          <span className="title">{t('verify_waive')}</span>
          <br />
          <span className="meta">{t('verify_waive_body')}</span>
        </span>
      </label>
    </fieldset>
  )
}
