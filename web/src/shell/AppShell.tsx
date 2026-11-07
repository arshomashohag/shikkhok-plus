/**
 * The frame around every signed-in screen: a bottom bar on a phone-width
 * window and a side rail on a desktop-width one, with the same tabs.
 *
 * On desktop the rail follows the web boards: the mark and a collapse
 * toggle at the top, the tabs as pills, and who is signed in at the
 * bottom. Collapsing keeps the icons and is remembered on this computer.
 */
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { readQueue } from '../api/endpoints'
import { useT } from '../i18n/i18n'
import { usePwa } from '../pwa/pwa'
import { useReadySession } from '../session/session'
import { useOnline } from '../core/useResource'
import { Avatar, Snackbar } from '../ui/components'
import {
  CheckBadgeIcon,
  CloudOffIcon,
  DownloadIcon,
  HomeIcon,
  LayersIcon,
  MailIcon,
  MoreIcon,
  PanelIcon,
  UsersIcon,
  WalletIcon,
} from '../ui/icons'
import { tabsFor, homeFor, type Tab } from './nav'
import { pageWidth } from './pageWidth'
import { useUnreadCount } from '../features/account/area'
import { formatPhone, initial } from '../core/format'
import { MfaPrompt } from '../features/account/security'

const ICONS = {
  home: HomeIcon,
  layers: LayersIcon,
  wallet: WalletIcon,
  users: UsersIcon,
  mail: MailIcon,
  more: MoreIcon,
  verify: CheckBadgeIcon,
} as const

const COLLAPSE_KEY = 'sp.rail.collapsed'

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

function storeCollapsed(value: boolean): void {
  try {
    if (value) window.localStorage.setItem(COLLAPSE_KEY, '1')
    else window.localStorage.removeItem(COLLAPSE_KEY)
  } catch {
    // Private window: the rail simply opens expanded next time.
  }
}

/**
 * How many payments wait for this teacher, for the rail's count. Read
 * again on every navigation, so deciding one on the Verify screen and
 * moving on shows the new number. Null until known or when it fails --
 * the count is a convenience and never blocks the rail.
 */
function useVerifyCount(enabled: boolean): number | null {
  const { pathname } = useLocation()
  const [count, setCount] = useState<number | null>(null)
  useEffect(() => {
    if (!enabled) return
    let live = true
    readQueue().then(
      (q) => {
        if (live) setCount(q.pending.length)
      },
      () => {
        if (live) setCount(null)
      },
    )
    return () => {
      live = false
    }
  }, [enabled, pathname])
  return enabled ? count : null
}

function NavItems({
  tabs,
  counts,
  unread,
}: {
  tabs: Tab[]
  counts: Partial<Record<string, number>>
  unread: number
}) {
  const { t } = useT()
  return tabs.map((tab) => {
    const Icon = ICONS[tab.icon]
    // The inbox lives under More, so More carries its unread count.
    const count = tab.to === '/more' ? unread : (counts[tab.to] ?? 0)
    const shown = count > 99 ? '99+' : String(count)
    return (
      <NavLink
        key={tab.to}
        to={tab.to}
        title={t(tab.label)}
        className={({ isActive }) =>
          ['nav-item', isActive ? 'active' : '', tab.desktopOnly ? 'desktop-only' : '']
            .filter(Boolean)
            .join(' ')
        }
      >
        <span className="nav-icon">
          <Icon size={22} />
          {count > 0 ? (
            <span className="nav-badge" aria-hidden="true">
              {shown}
            </span>
          ) : null}
        </span>
        <span className="nav-label">{t(tab.label)}</span>
        {count > 0 ? (
          <span
            className="nav-count"
            aria-label={
              tab.to === '/more'
                ? t('web_account_unread_count', count)
                : t('web_nav_verify_count', count)
            }
          >
            {shown}
          </span>
        ) : null}
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
  const unread = useUnreadCount() ?? 0
  const verifyCount = useVerifyCount(session.lens === 'teacher')
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const phone = session.me.phone ? formatPhone(session.me.phone) : ''
  const name = session.me.self_name ?? phone
  const role = session.lens ? t(`lens_${session.lens}`) : t('web_role_none')
  const counts = { '/verify': verifyCount ?? 0 }
  const { pathname } = useLocation()
  const width = pageWidth(pathname)
  // The two-step verification suggestion sits on the home screen only.
  const home = pathname === homeFor(session.lens) || pathname === '/today'

  const toggle = () => {
    setCollapsed((c) => {
      storeCollapsed(!c)
      return !c
    })
  }

  return (
    <div className={collapsed ? 'shell rail-collapsed' : 'shell'}>
      <a className="skip-link" href="#main">
        {t('web_skip_to_content')}
      </a>
      <div className="titlebar-drag" />
      <nav className="rail" aria-label="ShikkhokPlus">
        <div className="rail-top">
          <Link className="rail-brand" to={homeFor(session.lens)}>
            <img src={`${import.meta.env.BASE_URL}icons/favicon.svg`} alt="" />
            <span>
              Shikkhok<span className="plus">Plus</span>
            </span>
          </Link>
          <button
            type="button"
            className="rail-toggle"
            onClick={toggle}
            aria-expanded={!collapsed}
            aria-label={collapsed ? t('web_rail_expand') : t('web_rail_collapse')}
            title={collapsed ? t('web_rail_expand') : t('web_rail_collapse')}
          >
            <PanelIcon size={20} />
          </button>
        </div>
        <NavItems tabs={tabs} counts={counts} unread={unread} />
        <div className="rail-footer">
          {pwa.canInstall ? (
            <button
              type="button"
              className="btn btn-tonal btn-small"
              onClick={() => void pwa.install()}
              title={t('web_install')}
            >
              <DownloadIcon size={18} />
              <span>{t('web_install')}</span>
            </button>
          ) : null}
          {name ? (
            <Link
              className="rail-me"
              to="/more"
              title={t('web_signed_in_as', name)}
              aria-label={t('web_signed_in_as', name)}
            >
              <Avatar letter={initial(name)} />
              <span className="who">
                <span className="name">{name}</span>
                <span className="meta">{[role, phone].filter(Boolean).join(' · ')}</span>
              </span>
            </Link>
          ) : null}
        </div>
      </nav>
      <main id="main" className={`shell-main width-${width}`} tabIndex={-1}>
        {!online ? (
          <div className="banner" role="status" style={{ marginTop: 16 }}>
            <CloudOffIcon />
            <span>{t('web_offline_banner')}</span>
          </div>
        ) : null}
        {home ? <MfaPrompt /> : null}
        <Outlet />
      </main>
      <nav className="bottom-nav" aria-label="ShikkhokPlus">
        <NavItems tabs={tabs.filter((tab) => !tab.desktopOnly)} counts={{}} unread={unread} />
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
