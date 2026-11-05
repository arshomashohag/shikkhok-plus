/**
 * The frame around every signed-in screen: a bottom bar on a phone-width
 * window and a side rail on a desktop-width one, with the same tabs.
 */
import { NavLink, Outlet } from 'react-router'
import { useT } from '../i18n/i18n'
import { usePwa } from '../pwa/pwa'
import { useReadySession } from '../session/session'
import { useOnline } from '../core/useResource'
import { Snackbar } from '../ui/components'
import {
  CloudOffIcon,
  DownloadIcon,
  HomeIcon,
  LayersIcon,
  MailIcon,
  MoreIcon,
  UsersIcon,
  WalletIcon,
} from '../ui/icons'
import { tabsFor, type Tab } from './nav'
import { formatPhone } from '../core/format'

const ICONS = {
  home: HomeIcon,
  layers: LayersIcon,
  wallet: WalletIcon,
  users: UsersIcon,
  mail: MailIcon,
  more: MoreIcon,
} as const

function NavItems({ tabs }: { tabs: Tab[] }) {
  const { t } = useT()
  return tabs.map((tab) => {
    const Icon = ICONS[tab.icon]
    return (
      <NavLink
        key={tab.to}
        to={tab.to}
        className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
      >
        <span className="nav-icon">
          <Icon size={22} />
        </span>
        <span>{t(tab.label)}</span>
      </NavLink>
    )
  })
}

export function AppShell() {
  const { t } = useT()
  const { session } = useReadySession()
  const pwa = usePwa()
  const online = useOnline()
  const tabs = tabsFor(session.lens)
  const who = session.me.self_name ?? (session.me.phone ? formatPhone(session.me.phone) : '')

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t('web_skip_to_content')}
      </a>
      <div className="titlebar-drag" />
      <nav className="rail" aria-label="ShikkhokPlus">
        <div className="rail-brand">
          <img src={`${import.meta.env.BASE_URL}icons/favicon.svg`} alt="" />
          <span>ShikkhokPlus</span>
        </div>
        <NavItems tabs={tabs} />
        <div className="rail-footer">
          {pwa.canInstall ? (
            <button
              type="button"
              className="btn btn-tonal btn-small"
              onClick={() => void pwa.install()}
            >
              <DownloadIcon size={18} />
              {t('web_install')}
            </button>
          ) : null}
          {who ? <span>{t('web_signed_in_as', who)}</span> : null}
        </div>
      </nav>
      <main id="main" className="shell-main" tabIndex={-1}>
        {!online ? (
          <div className="banner" role="status" style={{ marginTop: 16 }}>
            <CloudOffIcon />
            <span>{t('web_offline_banner')}</span>
          </div>
        ) : null}
        <Outlet />
      </main>
      <nav className="bottom-nav" aria-label="ShikkhokPlus">
        <NavItems tabs={tabs} />
      </nav>
      {pwa.updateReady ? (
        <Snackbar
          text={t('web_update_ready')}
          action={t('web_update_reload')}
          onAction={pwa.applyUpdate}
          onDismiss={pwa.dismissUpdate}
        />
      ) : null}
    </div>
  )
}
