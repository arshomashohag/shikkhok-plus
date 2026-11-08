/**
 * The prompt to set a password, for an account made before passwords
 * (`has_password` false on `/v1/me`). Such a person signs in with a code
 * today, and once they sign out they will need the code flow again, so
 * the prompt stays — on every screen, with no "Not now" — until a
 * password is set. Whether one is set is the server's to say.
 */
import { Link, useLocation } from 'react-router'
import { useT } from '../../../i18n/i18n'
import { useOptionalSession } from '../../../session/session'
import { ShieldIcon } from '../../../ui/icons'
import { securityPaths } from './paths'

/** True when the server says the account has no password yet. */
export function needsPassword(me: { has_password?: boolean } | null | undefined): boolean {
  return me?.has_password === false
}

export function PasswordPrompt() {
  const { t } = useT()
  const session = useOptionalSession()
  const { pathname } = useLocation()
  if (!needsPassword(session?.me) || pathname === securityPaths.password()) return null
  return (
    <section className="card outlined mfa-prompt" aria-labelledby="password-prompt-title">
      <span className="mfa-prompt-icon" aria-hidden="true">
        <ShieldIcon size={24} />
      </span>
      <div className="mfa-prompt-text">
        <h2 id="password-prompt-title" className="title">
          {t('web_password_prompt_title')}
        </h2>
        <p className="meta">{t('web_password_prompt_body')}</p>
        <div className="button-row">
          <Link className="btn btn-primary btn-small" to={securityPaths.password()}>
            {t('web_password_set_action')}
          </Link>
        </div>
      </div>
    </section>
  )
}
