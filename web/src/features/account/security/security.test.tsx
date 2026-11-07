/**
 * Two-step verification against a mocked API, signed in for real: the
 * settings screen's flows, the More entry's label and the home prompt.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTokens } from '../../../api/tokens'
import { json } from '../../../test/render'
import { mockSignedIn, renderRoutes, type Call } from '../../../test/signedIn'
import { More } from '../More'
import { MfaPrompt, PROMPT_DISMISSED_KEY } from './MfaPrompt'
import { securityRoutes } from './index'
import { resetMfaStatus, type MfaStatus } from './status'
import { resetUnreadCount } from '../area/unread'

const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
const URI = `otpauth://totp/ShikkhokPlus:%2B8801711234567?secret=${SECRET}&issuer=ShikkhokPlus`
const CODES = Array.from({ length: 10 }, (_, i) => `ABCD${i}-EFGH${i}`)
const NEW_CODES = Array.from({ length: 10 }, (_, i) => `NEWC${i}-ODES${i}`)

const OFF: MfaStatus = {
  enabled: false,
  enabled_at: null,
  recovery_codes_left: 0,
  recommended: true,
  required: false,
}
const ON: MfaStatus = {
  enabled: true,
  enabled_at: '2026-11-01T04:00:00Z',
  recovery_codes_left: 10,
  recommended: true,
  required: false,
}

let status: MfaStatus
let calls: Call[]
const posts = (path: string) => calls.filter((c) => c.method === 'POST' && c.url.endsWith(path))
const reads = () => calls.filter((c) => c.method === 'GET' && c.url.endsWith('/v1/me/mfa'))

function serve(lens: 'teacher' | 'student' = 'teacher') {
  calls = mockSignedIn((method, url, body) => {
    const path = new URL(url, 'http://x').pathname
    if (method === 'GET' && path === '/v1/me/mfa') return json(200, status)
    if (path === '/v1/me/mfa/setup') return json(200, { secret: SECRET, otpauth_uri: URI })
    if (path === '/v1/me/mfa/confirm') {
      if ((body as { code: string }).code === '000000')
        return json(400, {
          error: { code: 'MFA_WRONG', message_key: 'mfa.code_wrong', retryable: false },
        })
      status = { ...ON, enabled_at: '2026-11-07T05:00:00Z' }
      return json(200, { recovery_codes: CODES })
    }
    if (path === '/v1/me/mfa/disable') {
      status = { ...OFF }
      return json(200, status)
    }
    if (path === '/v1/me/mfa/recovery-codes') return json(200, { recovery_codes: NEW_CODES })
    return undefined
  }, lens)
}

const SETTINGS = '/settings/security'

beforeEach(() => {
  localStorage.clear()
  resetMfaStatus()
  resetUnreadCount()
})
afterEach(() => {
  vi.unstubAllGlobals()
  clearTokens()
})

describe('two-step verification settings', () => {
  it('turns it on: QR code and key, the first code, then the codes once', async () => {
    status = { ...OFF }
    serve()
    renderRoutes(securityRoutes, SETTINGS)
    expect(await screen.findByText('Off')).toBeInTheDocument()
    expect(screen.getByText('Recommended')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Turn on' }))
    expect(
      await screen.findByRole('img', {
        name: 'QR code to add ShikkhokPlus to your authenticator app',
      }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('mfa-secret')).toHaveTextContent(
      'JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP',
    )
    expect(screen.getByRole('link', { name: 'Open in authenticator app' })).toHaveAttribute(
      'href',
      URI,
    )

    // A wrong first code is said inline and nothing changes.
    const field = screen.getByLabelText('Enter the 6-digit code the app now shows')
    expect(field).toHaveAttribute('inputmode', 'numeric')
    await userEvent.type(field, '000000')
    expect(await screen.findByRole('alert')).toHaveTextContent("That code isn't right.")

    await userEvent.type(field, '123456')
    const list = await screen.findByRole('list', { name: 'Recovery codes' })
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(CODES)
    expect(posts('/v1/me/mfa/confirm').at(-1)!.body).toEqual({ code: '123456' })

    // Shown once: a reload asks first while they are on screen.
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)

    await userEvent.click(screen.getByRole('button', { name: "I've saved them" }))
    expect(await screen.findByText('Two-step verification is on.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Recovery codes' })).toBeNull()
    expect(await screen.findByText('On since 7 Nov 2026')).toBeInTheDocument()
    const after = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(after)
    expect(after.defaultPrevented).toBe(false)
  })

  it('copies the codes, and says so when the browser will not', async () => {
    status = { ...OFF }
    serve()
    renderRoutes(securityRoutes, SETTINGS)
    await userEvent.click(await screen.findByRole('button', { name: 'Turn on' }))
    await userEvent.type(
      await screen.findByLabelText('Enter the 6-digit code the app now shows'),
      '123456',
    )
    await screen.findByRole('list', { name: 'Recovery codes' })

    const writeText = vi
      .fn()
      .mockRejectedValueOnce(new Error('denied'))
      .mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    fireEvent.click(screen.getByRole('button', { name: 'Copy all' }))
    expect(await screen.findByText(/Couldn't copy/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy all' }))
    await waitFor(() => expect(writeText).toHaveBeenLastCalledWith(CODES.join('\n')))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('turns it off with an authenticator code', async () => {
    status = { ...ON }
    serve()
    renderRoutes(securityRoutes, SETTINGS)
    expect(await screen.findByText('On since 1 Nov 2026')).toBeInTheDocument()
    expect(screen.getByText('Recovery codes left: 10 of 10')).toBeInTheDocument()
    expect(screen.queryByText('Recommended')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Turn off' }))
    const submit = screen.getByRole('button', { name: 'Turn off' })
    expect(submit).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Authenticator code'), '246810')
    await userEvent.click(submit)
    expect(await screen.findByText('Two-step verification is off.')).toBeInTheDocument()
    expect(posts('/v1/me/mfa/disable')[0]!.body).toEqual({ code: '246810' })
    expect(await screen.findByRole('button', { name: 'Turn on' })).toBeInTheDocument()
  })

  it('turns it off with a recovery code instead', async () => {
    status = { ...ON }
    serve()
    renderRoutes(securityRoutes, SETTINGS)
    await userEvent.click(await screen.findByRole('button', { name: 'Turn off' }))
    await userEvent.click(screen.getByRole('button', { name: 'Use a recovery code instead' }))
    await userEvent.type(screen.getByLabelText('Recovery code'), 'abcd1-efgh1')
    await userEvent.click(screen.getByRole('button', { name: 'Turn off' }))
    await screen.findByText('Two-step verification is off.')
    expect(posts('/v1/me/mfa/disable')[0]!.body).toEqual({ recovery_code: 'ABCD1-EFGH1' })
  })

  it('gets new recovery codes, shown once', async () => {
    status = { ...ON, recovery_codes_left: 2 }
    serve()
    renderRoutes(securityRoutes, SETTINGS)
    // Two or fewer left: the screen says to get new ones.
    expect(await screen.findByText(/Only 2 of 10 recovery codes left/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'New recovery codes' }))
    await userEvent.type(screen.getByLabelText('Authenticator code'), '135790')
    await userEvent.click(screen.getByRole('button', { name: 'Get new codes' }))
    const list = await screen.findByRole('list', { name: 'Recovery codes' })
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(NEW_CODES)
    expect(posts('/v1/me/mfa/recovery-codes')[0]!.body).toEqual({ code: '135790' })

    status = { ...ON }
    await userEvent.click(screen.getByRole('button', { name: "I've saved them" }))
    expect(
      await screen.findByText('You have new recovery codes. The old ones no longer work.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Recovery codes' })).toBeNull()
  })

  it('offers no way to turn it off when it is required', async () => {
    status = { ...ON, required: true }
    serve()
    renderRoutes(securityRoutes, SETTINGS)
    expect(await screen.findByText('Required for your account')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New recovery codes' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Turn off' })).toBeNull()
  })

  it("shows the server's words when a change fails", async () => {
    status = { ...OFF }
    calls = mockSignedIn((method, url) => {
      if (method === 'GET' && url.endsWith('/v1/me/mfa')) return json(200, status)
      if (url.endsWith('/v1/me/mfa/setup'))
        return json(409, {
          error: { code: 'CONFLICT', message_key: 'mfa.already_enabled', retryable: false },
        })
      return undefined
    })
    renderRoutes(securityRoutes, SETTINGS)
    await userEvent.click(await screen.findByRole('button', { name: 'Turn on' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Two-step verification is already on for this account.',
    )
  })
})

describe('the More entry', () => {
  const routes = [{ path: '/more', element: <More /> }, ...securityRoutes]

  it('carries "Recommended" while it is off for a teacher', async () => {
    status = { ...OFF }
    serve()
    renderRoutes(routes, '/more')
    const entry = await screen.findByRole('link', { name: /Two-step verification/ })
    await waitFor(() => expect(entry).toHaveTextContent('Recommended'))
    expect(entry).toHaveTextContent('Off')
    expect(entry).toHaveAttribute('href', SETTINGS)
  })

  it('has no label for a student, for whom it is not recommended', async () => {
    status = { ...OFF, recommended: false }
    serve('student')
    renderRoutes(routes, '/more')
    const entry = await screen.findByRole('link', { name: /Two-step verification/ })
    await waitFor(() => expect(entry).toHaveTextContent('Off'))
    expect(entry).not.toHaveTextContent('Recommended')
  })
})

describe('the home prompt', () => {
  const routes = [
    { path: '/batches', element: <MfaPrompt /> },
    { path: '/my-batches', element: <MfaPrompt /> },
    ...securityRoutes,
  ]
  const title = 'Protect your account with two-step verification'

  it('is shown when recommended and off, and Turn on goes straight to the setup', async () => {
    status = { ...OFF }
    serve()
    renderRoutes(routes, '/batches')
    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.getByText(/takes over your SIM/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('link', { name: 'Turn on' }))
    expect(
      await screen.findByRole('img', {
        name: 'QR code to add ShikkhokPlus to your authenticator app',
      }),
    ).toBeInTheDocument()
    // Once, StrictMode notwithstanding: a second secret would replace the first.
    expect(posts('/v1/me/mfa/setup')).toHaveLength(1)
  })

  it('stays away after Not now', async () => {
    status = { ...OFF }
    serve()
    const { unmount } = renderRoutes(routes, '/batches')
    await userEvent.click(await screen.findByRole('button', { name: 'Not now' }))
    expect(screen.queryByText(title)).toBeNull()
    expect(localStorage.getItem(PROMPT_DISMISSED_KEY)).toBe('1')
    unmount()

    renderRoutes(routes, '/batches')
    await waitFor(() => expect(reads().length).toBeGreaterThan(0))
    expect(screen.queryByText(title)).toBeNull()
  })

  it('is not shown when it is already on', async () => {
    status = { ...ON }
    serve()
    renderRoutes(routes, '/batches')
    await waitFor(() => expect(reads().length).toBeGreaterThan(0))
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByText(title)).toBeNull()
  })

  it('is never shown to a student or guardian', async () => {
    status = { ...OFF, recommended: false }
    serve('student')
    renderRoutes(routes, '/my-batches')
    await waitFor(() => expect(reads().length).toBeGreaterThan(0))
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByText(title)).toBeNull()
  })
})
