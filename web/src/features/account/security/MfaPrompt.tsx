/**
 * The home screen's suggestion to turn on two-step verification, for an
 * account the server recommends it for (a teacher or a centre member)
 * while it is off. Students and guardians are never prompted: for them
 * the server says `recommended: false`, and it lives only in Settings.
 *
 * "Not now" is remembered in this browser: a per-viewer convenience, the
 * one flag this feature keeps in `localStorage`, and no API data. The
 * Settings entry keeps its "Recommended" label regardless.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { useT } from '../../../i18n/i18n'
import { ShieldIcon } from '../../../ui/icons'
import { securityPaths, type TwoStepEntry } from './paths'
import { isSuggested, useMfaStatus } from './status'

export const PROMPT_DISMISSED_KEY = 'sp.mfa.prompt.dismissed'

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(PROMPT_DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

function storeDismissed(): void {
  try {
    window.localStorage.setItem(PROMPT_DISMISSED_KEY, '1')
  } catch {
    // Private window: it is dismissed for this visit only.
  }
}

export function MfaPrompt() {
  const { t } = useT()
  const status = useMfaStatus()
  const [dismissed, setDismissed] = useState(readDismissed)
  if (dismissed || !isSuggested(status)) return null
  const start: TwoStepEntry = { start: true }
  return (
    <section className="card outlined mfa-prompt" aria-labelledby="mfa-prompt-title">
      <span className="mfa-prompt-icon" aria-hidden="true">
        <ShieldIcon size={24} />
      </span>
      <div className="mfa-prompt-text">
        <h2 id="mfa-prompt-title" className="title">
          {t('web_mfa_prompt_title')}
        </h2>
        <p className="meta">{t('web_mfa_prompt_body')}</p>
        <div className="button-row">
          <Link className="btn btn-primary btn-small" to={securityPaths.twoStep()} state={start}>
            {t('web_mfa_turn_on')}
          </Link>
          <button
            type="button"
            className="btn btn-text btn-small"
            onClick={() => {
              storeDismissed()
              setDismissed(true)
            }}
          >
            {t('web_mfa_prompt_not_now')}
          </button>
        </div>
      </div>
    </section>
  )
}
