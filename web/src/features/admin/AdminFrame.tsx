/**
 * The frame every admin screen sits in: a title, the three sections as
 * tabs, and the screen. Inside the ordinary shell, so the rail and the
 * person's own tabs stay where they are.
 *
 * Access is the server's to decide. A screen that is refused with a 403
 * says the area is for administrators and offers the way back, instead
 * of an error that suggests trying again.
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { ApiError } from '../../api/errors'
import { useT } from '../../i18n/i18n'
import { ErrorCard, TopBar } from '../../ui/components'
import { ShieldIcon } from '../../ui/icons'
import { isNotAdmin } from './mappers'
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

/** Shown to a signed-in account the server does not treat as an administrator. */
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
        <Link className="btn btn-primary" to="/">
          {t('web_admin_go_home')}
        </Link>
      </div>
    </>
  )
}

/** A failed load: the not-an-administrator page for a 403, else the usual error. */
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
