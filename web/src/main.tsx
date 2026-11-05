import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { App } from './App'
import { PrefsProvider, usePrefs } from './core/prefs'
import { I18nProvider } from './i18n/i18n'
import { PwaProvider } from './pwa/pwa'
import { SessionProvider } from './session/session'
import './styles/tokens.css'
import './styles/app.css'

function WithLanguage() {
  const { lang } = usePrefs()
  return (
    <I18nProvider lang={lang}>
      <PwaProvider>
        <SessionProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </SessionProvider>
      </PwaProvider>
    </I18nProvider>
  )
}

const root = document.getElementById('root')
if (!root) throw new Error('index.html has no #root')

createRoot(root).render(
  <StrictMode>
    <PrefsProvider>
      <WithLanguage />
    </PrefsProvider>
  </StrictMode>,
)
