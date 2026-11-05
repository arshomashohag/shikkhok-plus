import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import { I18nProvider } from '../i18n/i18n'
import { SessionProvider } from '../session/session'

/** Render a screen with English strings, a session and a router. */
export function renderScreen(ui: ReactElement, path = '/') {
  return render(
    <I18nProvider lang="en">
      <SessionProvider>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </SessionProvider>
    </I18nProvider>,
  )
}

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
