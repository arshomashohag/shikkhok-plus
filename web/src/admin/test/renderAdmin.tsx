/**
 * Render the whole admin app at an address against a mocked API, signed
 * in with an admin token or not. Every request goes to `handler`;
 * anything it does not answer is a 404 as from the API.
 */
import { render } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter, useLocation } from 'react-router'
import { vi } from 'vitest'
import { PrefsProvider } from '../../core/prefs'
import type { Lang } from '../../core/format'
import { I18nProvider } from '../../i18n/i18n'
import { json } from '../../test/render'
import { AdminApp } from '../AdminApp'
import { resetAdminSessionForTests, saveAdminSession } from '../session'

export type Handler = (method: string, url: string, body: unknown) => Response | undefined

export interface Call {
  method: string
  url: string
  body: unknown
  headers: Record<string, string>
}

export const notFound = () =>
  json(404, { error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false } })

/**
 * Route every request to `handler` and record it.
 *
 * @param signedIn Start with an admin token for the next hour
 * @return The calls made, in order
 */
export function serveAdmin(handler: Handler, signedIn = true): Call[] {
  const calls: Call[] = []
  resetAdminSessionForTests()
  sessionStorage.clear()
  if (signedIn) saveAdminSession({ access_token: 'ADMIN', expires_in: 3600 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const body = init.body ? JSON.parse(init.body as string) : undefined
      calls.push({ method, url, body, headers: (init.headers ?? {}) as Record<string, string> })
      return handler(method, url, body) ?? notFound()
    }),
  )
  return calls
}

function Where() {
  const location = useLocation()
  return (
    <p data-testid="where">
      {location.pathname}
      {location.search}
    </p>
  )
}

export function renderAdmin(path: string, lang: Lang = 'en') {
  return render(
    <StrictMode>
      <PrefsProvider>
        <I18nProvider lang={lang}>
          <MemoryRouter initialEntries={[path]}>
            <AdminApp />
            <Where />
          </MemoryRouter>
        </I18nProvider>
      </PrefsProvider>
    </StrictMode>,
  )
}
