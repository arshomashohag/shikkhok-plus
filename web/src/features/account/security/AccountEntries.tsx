/**
 * Settings rows for how the person signs in: the password (set or
 * change), and adding the phone number or email address the account
 * lacks. Which rows show follows `/v1/me` as the server answered it;
 * nothing is inferred.
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { ChevronIcon, MailIcon, ShieldIcon, UsersIcon } from '../../../ui/icons'
import { securityPaths } from './paths'
import { needsPassword } from './PasswordPrompt'

function EntryRow({
  to,
  icon,
  title,
  sub,
  offline,
  badge,
}: {
  to: string
  icon: ReactNode
  title: string
  sub: string
  offline: string | null | undefined
  badge?: ReactNode
}) {
  const content = (
    <>
      {icon}
      <span className="grow">
        <span className="title">{title}</span>
        <br />
        <span className="meta">{offline ?? sub}</span>
      </span>
      {badge}
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
        <Link className="row" to={to}>
          {content}
        </Link>
      )}
    </li>
  )
}

/**
 * @param offline The "needs a connection" line, when offline; the rows
 *   are greyed then
 */
export function AccountEntries({ offline }: { offline?: string | null }) {
  const { t } = useT()
  const { session } = useReadySession()
  const { me } = session
  const missing = needsPassword(me)
  // An older server does not say; offer nothing it cannot answer.
  const knowsPassword = typeof me.has_password === 'boolean'
  return (
    <>
      {knowsPassword ? (
        <EntryRow
          to={securityPaths.password()}
          icon={<ShieldIcon />}
          title={t(missing ? 'web_password_set_title' : 'web_password_change_title')}
          sub={t(missing ? 'web_password_entry_none' : 'web_password_entry_set')}
          offline={offline}
          badge={
            missing ? (
              <span className="chip chip-recommended">{t('web_mfa_recommended')}</span>
            ) : null
          }
        />
      ) : null}
      {me.phone === null ? (
        <EntryRow
          to={securityPaths.addContact('phone')}
          icon={<UsersIcon />}
          title={t('web_contact_add_phone')}
          sub={t('web_contact_add_phone_why')}
          offline={offline}
        />
      ) : null}
      {me.email === null ? (
        <EntryRow
          to={securityPaths.addContact('email')}
          icon={<MailIcon />}
          title={t('web_contact_add_email')}
          sub={t('web_contact_add_email_why')}
          offline={offline}
        />
      ) : null}
    </>
  )
}
