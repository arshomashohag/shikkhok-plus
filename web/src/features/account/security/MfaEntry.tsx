/**
 * The row that opens the two-step verification settings, on More and on
 * Settings: its state in words, and a "Recommended" label while the
 * server suggests it and it is off.
 */
import { Link } from 'react-router'
import { useT } from '../../../i18n/i18n'
import { ChevronIcon, ShieldIcon } from '../../../ui/icons'
import { securityPaths } from './paths'
import { isSuggested, useMfaStatus } from './status'

/**
 * @param offline The "needs a connection" line, when offline; the row is
 *   greyed then, as More's other account rows are
 */
export function MfaEntry({ offline }: { offline?: string | null }) {
  const { t } = useT()
  const status = useMfaStatus()
  const state = status
    ? [
        t(status.enabled ? 'web_mfa_status_on' : 'web_mfa_status_off'),
        status.required ? t('web_mfa_required') : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : null
  const content = (
    <>
      <ShieldIcon />
      <span className="grow">
        <span className="title">{t('web_mfa_title')}</span>
        {(offline ?? state) ? (
          <>
            <br />
            <span className="meta">{offline ?? state}</span>
          </>
        ) : null}
      </span>
      {isSuggested(status) ? (
        <span className="chip chip-recommended">{t('web_mfa_recommended')}</span>
      ) : null}
      <ChevronIcon />
    </>
  )
  return (
    <li>
      {offline ? (
        <span className="row" aria-disabled="true" style={{ opacity: 0.55 }}>
          {content}
        </span>
      ) : (
        <Link className="row" to={securityPaths.twoStep()}>
          {content}
        </Link>
      )}
    </li>
  )
}
