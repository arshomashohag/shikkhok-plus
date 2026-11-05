/**
 * More: who is signed in, switching role, settings, install, log out.
 */
import { Link } from 'react-router'
import { formatPhone } from '../../core/format'
import { useT } from '../../i18n/i18n'
import { usePwa } from '../../pwa/pwa'
import { useReadySession } from '../../session/session'
import { Section, TopBar } from '../../ui/components'
import {
  ChevronIcon,
  DownloadIcon,
  LogOutIcon,
  MailIcon,
  SettingsIcon,
  SwapIcon,
} from '../../ui/icons'

export function More() {
  const { t } = useT()
  const { session, signOut, chooseLens } = useReadySession()
  const pwa = usePwa()
  const lensLabel = session.lens ? t(`lens_${session.lens}`) : t('web_role_none')
  const others = session.options.filter((o) => o.lens !== session.lens)

  return (
    <>
      <TopBar title={t('profile_title')} />
      <div className="card">
        <div className="title" style={{ fontSize: '1.25rem' }}>
          {session.me.self_name ?? t('more_name_missing')}
        </div>
        <div className="meta">
          {t('more_role_line', lensLabel, session.me.phone ? formatPhone(session.me.phone) : '')}
        </div>
      </div>

      {others.length > 0 ? (
        <Section title={t('lens_switch')}>
          <ul className="card flush list">
            {others.map((o) => (
              <li key={o.lens}>
                <button type="button" className="row" onClick={() => chooseLens(o.lens)}>
                  <SwapIcon />
                  <span className="grow">
                    <span className="title">{t(`lens_${o.lens}`)}</span>
                    <br />
                    <span className="meta">{t(`lens_${o.lens}_count`, o.count)}</span>
                  </span>
                  <ChevronIcon />
                </button>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title={t('more_section_app')}>
        <ul className="card flush list">
          {session.lens === 'student' || session.lens === 'guardian' ? (
            <li>
              <Link className="row" to="/invitations">
                <MailIcon />
                <span className="grow title">{t('more_invitations')}</span>
                <ChevronIcon />
              </Link>
            </li>
          ) : null}
          <li>
            <Link className="row" to="/settings">
              <SettingsIcon />
              <span className="grow">
                <span className="title">{t('more_settings')}</span>
                <br />
                <span className="meta">{t('web_settings_sub')}</span>
              </span>
              <ChevronIcon />
            </Link>
          </li>
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
        </ul>
      </Section>
      <p className="meta" style={{ textAlign: 'center', marginTop: 24 }}>
        {t('more_version', __APP_VERSION__)}
      </p>
    </>
  )
}
