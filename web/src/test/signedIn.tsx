/**
 * Render routes signed in for real against a mocked API: tokens in
 * storage, `/v1/me` answering, the session resolving its lens. For area
 * screens tests that need the session, as the account area's do.
 */
import { render } from '@testing-library/react'
import { StrictMode, type ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { vi } from 'vitest'
import { saveTokens } from '../api/tokens'
import { I18nProvider } from '../i18n/i18n'
import { PwaProvider } from '../pwa/pwa'
import { SessionProvider, useSession } from '../session/session'
import type { Lang } from '../core/format'
import { json } from './render'

export type Handler = (method: string, url: string, body: unknown) => Response | undefined

export interface Call {
  method: string
  url: string
  body: unknown
  headers: Record<string, string>
}

/**
 * Sign in and route every request to `handler`; `/v1/me` answers with
 * the given lens. Unhandled requests are a 404.
 *
 * @return The calls made, in order
 */
export function mockSignedIn(
  handler: Handler,
  lens: 'teacher' | 'student' | 'guardian' = 'teacher',
): Call[] {
  const calls: Call[] = []
  saveTokens({ access_token: 'A', refresh_token: 'R', expires_in: 900 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const body = init.body ? JSON.parse(init.body as string) : undefined
      calls.push({ method, url, body, headers: (init.headers ?? {}) as Record<string, string> })
      if (method === 'GET' && url.endsWith('/v1/me'))
        return json(200, {
          self_name: 'Karim Uddin',
          phone: null,
          lenses: [{ kind: lens, count: 1 }],
        })
      return (
        handler(method, url, body) ??
        json(404, {
          error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
        })
      )
    }),
  )
  return calls
}

function Ready({ children }: { children: ReactNode }) {
  const { session } = useSession()
  return session.state === 'ready' ? children : null
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

/** Render `routes` at `path`; any other path renders where it is. */
export function renderRoutes(
  routes: { path: string; element: ReactNode }[],
  path: string,
  lang: Lang = 'en',
) {
  return render(
    <StrictMode>
      <I18nProvider lang={lang}>
        <PwaProvider>
          <SessionProvider>
            <MemoryRouter initialEntries={[path]}>
              <Ready>
                <Routes>
                  {routes.map((r) => (
                    <Route key={r.path} path={r.path} element={r.element} />
                  ))}
                  <Route path="*" element={<Where />} />
                </Routes>
              </Ready>
            </MemoryRouter>
          </SessionProvider>
        </PwaProvider>
      </I18nProvider>
    </StrictMode>,
  )
}
