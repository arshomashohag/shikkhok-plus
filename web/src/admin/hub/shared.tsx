/**
 * What the moderation rows share: the report reasons and their labels, and
 * the in-page confirmation every act asks for before it sends anything.
 */
import { useEffect, useRef } from 'react'
import type { Schemas } from '../../api/endpoints'
import { useT } from '../../i18n/i18n'
import { WarningIcon } from '../../ui/icons'

export type Reason = Schemas['AdminHubSuspensionRequest']['reason_code']

export const REASONS: readonly Reason[] = [
  'personal_info',
  'child_safety',
  'abusive',
  'fake',
  'misleading',
  'other',
]

export const isReason = (r: string | null): r is Reason => REASONS.some((x) => x === r)

export function reasonLabel(t: (k: string) => string, reason: string | null): string {
  return isReason(reason) ? t(`web_admin_hub_reason_${reason}`) : (reason ?? '')
}

/**
 * Focus for a row's confirmation: opening it moves focus to Confirm;
 * closing it without acting returns focus to the button that opened it,
 * which was unmounted meanwhile and is found again by its `data-act`.
 *
 * @param open The open act's kind, or null when closed
 */
export function useConfirmFocus(open: string | null) {
  const confirmButton = useRef<HTMLButtonElement>(null)
  const row = useRef<HTMLLIElement>(null)
  /** Which trigger opened the confirmation, so Cancel can hand focus back to it. */
  const opener = useRef<string | null>(null)
  useEffect(() => {
    if (open) confirmButton.current?.focus()
    else if (opener.current) {
      row.current?.querySelector<HTMLElement>(`[data-act="${opener.current}"]`)?.focus()
      opener.current = null
    }
  }, [open])
  return { confirmButton, row, opener }
}

/** The confirmation banner: the question, what it records, Confirm and Cancel. */
export function ConfirmBanner({
  question,
  failure,
  busy,
  confirmButton,
  onConfirm,
  onCancel,
}: {
  question: string
  failure: string | null
  busy: boolean
  confirmButton: React.RefObject<HTMLButtonElement | null>
  onConfirm: () => void
  onCancel: () => void
}) {
  const { t } = useT()
  return (
    <div className="banner" role="group" aria-label={t('web_admin_hub_confirm')}>
      <div className="grow">
        <strong>{question}</strong>
        <br />
        <span className="meta">{t('web_admin_hub_confirm_body')}</span>
        {failure ? (
          <span className="field-error" role="alert">
            <WarningIcon /> {failure}
          </span>
        ) : null}
      </div>
      <div className="button-row">
        <button
          ref={confirmButton}
          type="button"
          className="btn btn-primary btn-small"
          disabled={busy}
          onClick={onConfirm}
        >
          {t('web_admin_hub_confirm')}
        </button>
        <button type="button" className="btn btn-text btn-small" disabled={busy} onClick={onCancel}>
          {t('web_admin_hub_cancel')}
        </button>
      </div>
    </div>
  )
}
