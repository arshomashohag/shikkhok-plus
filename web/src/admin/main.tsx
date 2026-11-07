/**
 * The admin app's entry (`admin.html`, `npm run build:admin`).
 *
 * A separate build from the main app, served at the root of its own
 * hostname: the main app's bundle contains none of this, and this one
 * has no service worker, no install prompt and no app session.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
// The shared styles first, so the admin app's own rules come after them.
import '../styles/tokens.css'
import '../styles/app.css'
import { PrefsProvider, usePrefs } from '../core/prefs'
import { I18nProvider } from '../i18n/i18n'
import { AdminApp } from './AdminApp'

function WithLanguage() {
  const { lang } = usePrefs()
  return (
    <I18nProvider lang={lang}>
      <BrowserRouter>
        <AdminApp />
      </BrowserRouter>
    </I18nProvider>
  )
}

const root = document.getElementById('root')
if (!root) throw new Error('admin.html has no #root')

createRoot(root).render(
  <StrictMode>
    <PrefsProvider>
      <WithLanguage />
    </PrefsProvider>
  </StrictMode>,
)
