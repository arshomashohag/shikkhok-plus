/**
 * The frame every admin screen sits in: a title, the three sections as
 * tabs, and the screen, inside the admin app's header (`../AdminChrome`).
 *
 * Access is the server's to decide. A 403 means this number is not, or
 * no longer, an administrator: the screen says so and offers Log out
 * rather than an error that suggests trying again. A 404 means the
 * request did not come through the admin edge, and says that instead.
 * A 401 never reaches here: the client ends the session and the app
 * returns to log-in (`../client.ts`).
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { ApiError } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { ErrorCard, TopBar } from '../../ui/components'
import { ShieldIcon } from '../../ui/icons'
import '../strings'
import { endAdminSession } from '../session'
import { isNotAdmin, isUnavailable } from './mappers'
import { adminPaths } from './paths'
import './admin.css'

export type AdminTab = 'overview' | 'teachers' | 'help'

const TABS: { tab: AdminTab; to: string; label: string }[] = [
  { tab: 'overview', to: adminPaths.overview(), label: 'web_admin_tab_overview' },
  { tab: 'teachers', to: adminPaths.teachers(), label: 'web_admin_tab_teachers' },
  { tab: 'help', to: adminPaths.people(), label: 'web_admin_tab_help' },
]

export function AdminFrame({
  tab,
  title,
  subtitle,
  back,
  children,
}: {
  tab: AdminTab
  title?: string
  subtitle?: ReactNode
  back?: string
  children: ReactNode
}) {
  const { t } = useT()
  return (
    <>
      <TopBar title={title ?? t('web_admin_title')} subtitle={subtitle} back={back} />
      <nav className="tabs admin-tabs" aria-label={t('web_admin_title')}>
        {TABS.map((x) => (
          <Link key={x.tab} to={x.to} aria-current={x.tab === tab ? 'page' : undefined}>
            {t(x.label)}
          </Link>
        ))}
      </nav>
      {children}
    </>
  )
}

/** Shown when the server no longer treats this session as an administrator's. */
export function NotAdmin() {
  const { t } = useT()
  return (
    <>
      <TopBar title={t('web_admin_title')} />
      <div className="card admin-denied" role="alert">
        <span className="admin-denied-icon" aria-hidden="true">
          <ShieldIcon size={28} />
        </span>
        <h2>{t('web_admin_not_admin_title')}</h2>
        <p className="meta">{t('web_admin_not_admin_body')}</p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => endAdminSession('signed-out')}
        >
          {t('more_log_out')}
        </button>
      </div>
    </>
  )
}

/** Shown when a request did not come through the admin edge (a 404). */
export function Unavailable() {
  const { t } = useT()
  return (
    <>
      <TopBar title={t('web_admin_title')} />
      <div className="card admin-denied" role="alert">
        <span className="admin-denied-icon" aria-hidden="true">
          <ShieldIcon size={28} />
        </span>
        <p className="meta">{t('web_admin_unavailable')}</p>
      </div>
    </>
  )
}

/**
 * A failed load: the not-an-administrator page for a 403, the
 * not-available page for a 404, else the usual error.
 */
export function AdminFailure({
  tab,
  title,
  error,
  onRetry,
}: {
  tab: AdminTab
  title: string
  error: ApiError
  onRetry: () => void
}) {
  if (isNotAdmin(error)) return <NotAdmin />
  if (isUnavailable(error)) return <Unavailable />
  return (
    <AdminFrame tab={tab}>
      <ErrorCard title={title} error={error} onRetry={onRetry} />
    </AdminFrame>
  )
}

/** A figure with its label, and a line under it. A link when it leads somewhere. */
export function Stat({
  label,
  value,
  sub,
  to,
}: {
  label: string
  value: string
  sub?: string
  to?: string
}) {
  const content = (
    <>
      <span className="label">{label}</span>
      <span className="figure">{value}</span>
      {sub ? <span className="meta">{sub}</span> : null}
    </>
  )
  return to ? (
    <Link className="card kpi admin-stat" to={to}>
      {content}
    </Link>
  ) : (
    <div className="card kpi admin-stat">{content}</div>
  )
}
