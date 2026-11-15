/**
 * The render-error boundary [functional-spec § 10 item 2]: a page that
 * throws while rendering shows the error card instead of a blank root,
 * and both navigation and Retry recover without a reload.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider, translate } from '../i18n/i18n'
import { RouteErrorBoundary } from './RouteErrorBoundary'

const en = (key: string) => translate('en', key)

let failing = true
let healthyMounts = 0

function Boom() {
  if (failing) throw new Error('render failed')
  return <p>recovered</p>
}

function Healthy() {
  useEffect(() => {
    healthyMounts += 1
  }, [])
  return <p>healthy page</p>
}

/** Navigation that lives outside the boundary, as the browser's own does. */
function Go() {
  const navigate = useNavigate()
  return (
    <>
      <button type="button" onClick={() => void navigate('/fine')}>
        to fine
      </button>
      <button type="button" onClick={() => void navigate('/fine?tab=2')}>
        to fine with a search
      </button>
    </>
  )
}

const signOut = vi.fn()

function Harness() {
  const { pathname } = useLocation()
  return (
    <>
      <Go />
      <RouteErrorBoundary pathname={pathname} onSignOut={signOut}>
        <Routes>
          <Route path="/boom" element={<Boom />} />
          <Route path="/fine" element={<Healthy />} />
        </Routes>
      </RouteErrorBoundary>
    </>
  )
}

function renderAt(path: string) {
  return render(
    <I18nProvider lang="en">
      <MemoryRouter initialEntries={[path]}>
        <Harness />
      </MemoryRouter>
    </I18nProvider>,
  )
}

beforeEach(() => {
  failing = true
  healthyMounts = 0
  signOut.mockClear()
  // React reports a caught render error itself; keep the run's output clean.
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})
afterEach(() => {
  failing = true
})

describe('RouteErrorBoundary', () => {
  it('a child that throws during render shows the error card, not a blank root', () => {
    renderAt('/boom')
    const card = screen.getByRole('alert')
    expect(card).toHaveTextContent(en('error_unexpected'))
    expect(screen.getByRole('button', { name: en('auth_retry') })).toBeInTheDocument()
    expect(document.body.textContent).not.toBe('')
  })

  it('navigating to another path renders that route', async () => {
    renderAt('/boom')
    expect(screen.getByRole('alert')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'to fine' }))
    expect(screen.getByText('healthy page')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('Retry renders the children again', async () => {
    renderAt('/boom')
    failing = false
    await userEvent.click(screen.getByRole('button', { name: en('auth_retry') }))
    expect(screen.getByText('recovered')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('Retry on a page that still throws shows the card again', async () => {
    renderAt('/boom')
    await userEvent.click(screen.getByRole('button', { name: en('auth_retry') }))
    expect(screen.getByRole('alert')).toHaveTextContent(en('error_unexpected'))
  })

  it('a navigation that changes only the search string does not remount a healthy page', async () => {
    renderAt('/fine')
    expect(healthyMounts).toBe(1)
    await userEvent.click(screen.getByRole('button', { name: 'to fine with a search' }))
    expect(screen.getByText('healthy page')).toBeInTheDocument()
    expect(healthyMounts).toBe(1)
  })

  it('the card offers Log out, which ends the session', async () => {
    renderAt('/boom')
    await userEvent.click(screen.getByRole('button', { name: en('more_log_out') }))
    expect(signOut).toHaveBeenCalledTimes(1)
  })

  it('a healthy page renders its children untouched', () => {
    renderAt('/fine')
    expect(screen.getByText('healthy page')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
