/**
 * The admin app's frames: the sign-in page (the main app's brand panel,
 * saying what this is for) and, once signed in, a header with when the
 * session ends, the language and Log out, above the screen.
 *
 * There is no side rail and no bottom bar: three sections fit as tabs in
 * each screen's own frame (`screens/AdminFrame.tsx`).
 */
import type { ReactNode } from 'react'
import { Link, Outlet } from 'react-router'
import { usePrefs } from '../core/prefs'
import { MarkOnBlue } from '../features/auth/AuthFrame'
import { useT } from '../i18n/i18n'
import { CheckIcon, ShieldIcon } from '../ui/icons'
import { endAdminSession, type AdminSession } from './session'
import { formatUntil } from './useAdminSession'
import './admin-app.css'

/** বাংলা ⇄ English, as one button naming the other language. */
export function LanguageToggle({ className = 'btn btn-text btn-small' }: { className?: string }) {
  const { lang, update } = usePrefs()
  const { t } = useT()
  const other = lang === 'bn' ? 'en' : 'bn'
  return (
    <button
      type="button"
      className={className}
      lang={other}
      title={t('web_language')}
      onClick={() => update({ lang: other })}
    >
      {other === 'bn' ? 'বাংলা' : 'English'}
    </button>
  )
}

function Brand() {
  const { t } = useT()
  return (
    <span className="admin-brand-name">
      <span>
        Shikkhok<span className="plus">Plus</span>
      </span>
      <span className="admin-badge">{t('web_admin_brand_badge')}</span>
    </span>
  )
}

export function AdminAuthFrame({ children }: { children: ReactNode }) {
  const { t } = useT()
  const points = [
    'web_admin_auth_point_allowlist',
    'web_admin_auth_point_two_codes',
    'web_admin_auth_point_hour',
  ]
  return (
    <div className="auth-page admin-auth">
      <aside className="auth-hero">
        <div className="admin-auth-top">
          <div className="auth-brand">
            <MarkOnBlue />
            <Brand />
          </div>
          <LanguageToggle className="btn btn-small admin-lang-on-blue" />
        </div>
        <p className="auth-tagline">{t('web_admin_auth_tagline')}</p>
        <ul className="auth-points">
          {points.map((key) => (
            <li key={key}>
              <CheckIcon size={20} />
              <span>{t(key)}</span>
            </li>
          ))}
        </ul>
      </aside>
      <div className="auth-panel">
        <div className="auth-card">{children}</div>
      </div>
    </div>
  )
}

/** The signed-in frame: header, then the screen. */
export function AdminShell({ session }: { session: AdminSession }) {
  const { t, lang } = useT()
  return (
    <div className="admin-shell">
      <a className="skip-link" href="#main">
        {t('web_skip_to_content')}
      </a>
      <header className="admin-header">
        <Link className="admin-header-brand" to="/">
          <span className="admin-header-mark" aria-hidden="true">
            <ShieldIcon size={20} />
          </span>
          <Brand />
        </Link>
        <span className="admin-until meta">
          {t('web_admin_signed_in_until', formatUntil(session.expiresAt, lang))}
        </span>
        <span className="admin-header-actions">
          <LanguageToggle />
          <button
            type="button"
            className="btn btn-outline btn-small"
            onClick={() => endAdminSession('signed-out')}
          >
            {t('more_log_out')}
          </button>
        </span>
      </header>
      <main id="main" className="admin-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
