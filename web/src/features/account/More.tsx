/**
 * More: who is signed in, with Edit; the inbox; invitations and children
 * for a student or guardian; the help centre, with its new replies; the teacher's Getting paid and Your records;
 * settings and install; switching role, log out and delete account.
 * Grouped as Android's profile screen groups them.
 *
 * Rows that change the account need a connection and say so offline,
 * as Android's `more_needs_connection` rows do.
 */
import { Link, useLocation } from 'react-router'
import { formatPhone } from '../../core/format'
import { useOnline } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { usePwa } from '../../pwa/pwa'
import { useReadySession } from '../../session/session'
import { Section, TopBar } from '../../ui/components'
import {
  BellIcon,
  ChevronIcon,
  DownloadIcon,
  EditIcon,
  LayersIcon,
  LogOutIcon,
  HelpIcon,
  MailIcon,
  SettingsIcon,
  SwapIcon,
  UsersIcon,
  WalletIcon,
  WarningIcon,
} from '../../ui/icons'
import { paths } from '../teacher/paths'
import { accountPaths } from '../family/reader'
import { useUnreadCount } from './area/unread'
import { helpPaths, useNewReplies } from '../help'
import { WorkspaceSection } from './Workspaces'

/** One More row: a link when there is somewhere to go, else greyed. */
function Row({
  to,
  icon,
  title,
  sub,
  disabled,
  badge,
}: {
  to: string
  icon: React.ReactNode
  title: string
  sub?: string | null
  disabled?: boolean
  badge?: React.ReactNode
}) {
  const content = (
    <>
      {icon}
      <span className="grow">
        <span className="title">{title}</span>
        {sub ? (
          <>
            <br />
            <span className="meta">{sub}</span>
          </>
        ) : null}
      </span>
      {badge}
      <ChevronIcon />
    </>
  )
  return (
    <li>
      {disabled ? (
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

export function More() {
  const { t } = useT()
  const { session, signOut, chooseLens } = useReadySession()
  const pwa = usePwa()
  const online = useOnline()
  const unread = useUnreadCount()
  const newReplies = useNewReplies()
  const location = useLocation()
  const saved = (location.state as { saved?: boolean } | null)?.saved === true
  const lensLabel = session.lens ? t(`lens_${session.lens}`) : t('web_role_none')
  const others = session.options.filter((o) => o.lens !== session.lens)
  const family = session.lens === 'student' || session.lens === 'guardian'
  const needsConnection = online ? null : t('more_needs_connection')

  return (
    <>
      <TopBar title={t('profile_title')} />
      {saved ? (
        <div className="banner" role="status" style={{ marginBottom: 12 }}>
          {t('profile_saved')}
        </div>
      ) : null}
      <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div className="grow" style={{ flex: 1, minWidth: 0 }}>
          <div className="title" style={{ fontSize: '1.25rem' }}>
            {session.me.self_name ?? t('more_name_missing')}
          </div>
          <div className="meta">
            {t('more_role_line', lensLabel, session.me.phone ? formatPhone(session.me.phone) : '')}
          </div>
        </div>
        {online ? (
          <Link className="btn btn-tonal btn-small" to={accountPaths.profileEdit()}>
            <EditIcon size={18} />
            {t('profile_edit')}
          </Link>
        ) : null}
      </div>

      <Section title={t('inbox_title')}>
        <ul className="card flush list">
          <Row
            to={accountPaths.inbox()}
            icon={<BellIcon />}
            title={t('inbox_title')}
            sub={t('web_account_inbox_sub')}
            badge={
              unread ? (
                <span
                  className="chip chip-overdue"
                  aria-label={t('web_account_unread_count', unread)}
                >
                  {unread}
                </span>
              ) : null
            }
          />
        </ul>
      </Section>

      {family ? (
        <Section title={t('more_section_records')}>
          <ul className="card flush list">
            <Row
              to="/invitations"
              icon={<MailIcon />}
              title={t('more_invitations')}
              sub={
                needsConnection ??
                (session.lens === 'guardian'
                  ? t('more_invitations_sub_guardian')
                  : t('more_invitations_sub_student'))
              }
              disabled={!online}
            />
            {session.lens === 'guardian' ? (
              <Row
                to={accountPaths.myChildren()}
                icon={<UsersIcon />}
                title={t('more_my_children')}
                sub={needsConnection}
                disabled={!online}
              />
            ) : null}
          </ul>
        </Section>
      ) : null}

      {family ? null : (
        <Section title={t('more_invitations')}>
          <ul className="card flush list">
            <Row
              to="/invitations"
              icon={<MailIcon />}
              title={t('membership_offers_title')}
              sub={needsConnection ?? t('more_invitations')}
              disabled={!online}
            />
          </ul>
        </Section>
      )}

      <WorkspaceSection online={online} />

      {session.lens === 'teacher' ? (
        <>
          <Section title={t('more_section_getting_paid')}>
            <ul className="card flush list">
              <Row
                to={paths.paymentMethods()}
                icon={<WalletIcon />}
                title={t('more_where_students_pay')}
                sub={needsConnection ?? t('more_where_students_pay_sub')}
                disabled={!online}
              />
            </ul>
          </Section>
          <Section title={t('more_section_records')}>
            <ul className="card flush list">
              <Row
                to={paths.collections()}
                icon={<LayersIcon />}
                title={t('profile_collections')}
                sub={needsConnection ?? t('more_collections_sub')}
                disabled={!online}
              />
              <Row
                to={paths.expenses()}
                icon={<WalletIcon />}
                title={t('expenses_title')}
                sub={needsConnection ?? t('summary_basis')}
                disabled={!online}
              />
              <Row
                to={paths.moneySummary()}
                icon={<LayersIcon />}
                title={t('summary_title')}
                sub={needsConnection ?? t('summary_basis')}
                disabled={!online}
              />
            </ul>
          </Section>
        </>
      ) : null}

      <Section title={t('settings_section_help')}>
        <ul className="card flush list">
          <Row
            to={helpPaths.list()}
            icon={<HelpIcon />}
            title={t('more_help')}
            sub={t('more_help_sub')}
            badge={
              newReplies ? (
                <span
                  className="chip chip-overdue"
                  aria-label={t('web_help_new_replies', newReplies)}
                >
                  {newReplies}
                </span>
              ) : null
            }
          />
        </ul>
      </Section>

      <Section title={t('more_section_app')}>
        <ul className="card flush list">
          <Row
            to="/settings"
            icon={<SettingsIcon />}
            title={t('more_settings')}
            sub={t('web_settings_sub')}
          />
          {pwa.canInstall ? (
            <li>
              <button type="button" className="row" onClick={() => void pwa.install()}>
                <DownloadIcon />
                <span className="grow">
                  <span className="title">{t('web_install')}</span>
                  <br />
                  <span className="meta">{t('web_install_sub')}</span>
                </span>
              </button>
            </li>
          ) : null}
        </ul>
      </Section>

      <Section title={t('more_section_account')}>
        <ul className="card flush list">
          {others.map((o) => (
            <li key={o.lens}>
              <button type="button" className="row" onClick={() => chooseLens(o.lens)}>
                <SwapIcon />
                <span className="grow">
                  <span className="title">
                    {t('lens_switch')} · {t(`lens_${o.lens}`)}
                  </span>
                  <br />
                  <span className="meta">{t(`lens_${o.lens}_count`, o.count)}</span>
                </span>
                <ChevronIcon />
              </button>
            </li>
          ))}
          <li>
            <button type="button" className="row" onClick={signOut}>
              <LogOutIcon />
              <span className="grow">
                <span className="title">{t('more_log_out')}</span>
                <br />
                <span className="meta">{t('web_shared_computer')}</span>
              </span>
            </button>
          </li>
          <Row
            to={accountPaths.deleteAccount()}
            icon={<WarningIcon />}
            title={t('more_delete_account')}
            sub={needsConnection}
            disabled={!online}
          />
        </ul>
      </Section>
      <p className="meta" style={{ textAlign: 'center', marginTop: 24 }}>
        {t('more_version', __APP_VERSION__)}
      </p>
    </>
  )
}
