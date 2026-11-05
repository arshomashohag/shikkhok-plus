/**
 * The frame around sign-in and sign-up, as the web boards draw it: the
 * brand panel on the left of a wide window with what ShikkhokPlus is
 * for, and the form on the right. On a phone the panel shrinks to a
 * band carrying only the mark.
 */
import type { ReactNode } from 'react'
import { useT } from '../../i18n/i18n'
import { CheckIcon } from '../../ui/icons'

/** The mark in its on-blue colours: white and the light accent. */
function MarkOnBlue() {
  return (
    <svg width="48" height="50" viewBox="24 20 66 68" aria-hidden="true">
      <circle cx="40" cy="33" r="9" fill="#FFFFFF" />
      <path d="M28 84V56a12 12 0 0 1 24 0v28Z" fill="#FFFFFF" />
      <circle cx="64" cy="42" r="7" fill="#A9C7FF" />
      <path d="M54 84V63a10 10 0 0 1 20 0v21Z" fill="#A9C7FF" />
      <g fill="none" stroke="#1D4F91" strokeWidth="2.4" strokeLinejoin="round">
        <path d="M40 63c6 0 10 2 13 5v16c-3-3-7-4-13-4Z" />
        <path d="M66 63c-6 0-10 2-13 5v16c3-3 7-4 13-4Z" />
      </g>
      <path
        d="M46 72L53 80L79 41.5"
        fill="none"
        stroke="#1D4F91"
        strokeWidth="8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polygon
        points="85.6,31.8 84.7,42.1 76.4,36.5"
        fill="#1D4F91"
        stroke="#1D4F91"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <path
        d="M46 72L53 80L79 41.5"
        fill="none"
        stroke="#A9C7FF"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polygon
        points="85.6,31.8 84.7,42.1 76.4,36.5"
        fill="#A9C7FF"
        stroke="#A9C7FF"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function AuthFrame({ children, wide }: { children: ReactNode; wide?: boolean }) {
  const { t } = useT()
  const points = [
    'web_auth_point_login',
    'web_auth_point_teacher',
    'web_auth_point_student',
    'web_auth_point_guardian',
  ]
  return (
    <div className="auth-page">
      <aside className="auth-hero">
        <div className="auth-brand">
          <MarkOnBlue />
          <span>
            Shikkhok<span className="plus">Plus</span>
          </span>
        </div>
        <p className="auth-tagline">{t('web_auth_tagline')}</p>
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
        <div className={wide ? 'auth-card wide' : 'auth-card'}>{children}</div>
      </div>
    </div>
  )
}
