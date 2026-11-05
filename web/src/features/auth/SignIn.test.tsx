import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearTokens, readTokens } from '../../api/tokens'
import { json, renderScreen } from '../../test/render'
import { SignIn } from './SignIn'

const fetchMock = vi.fn()
beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
  clearTokens()
})

it('refuses a malformed number without calling the server', async () => {
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '12345')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  expect(screen.getByRole('alert')).toHaveTextContent('11 digits')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('sends the code, then signs in by itself after the sixth digit', async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/v1/auth/otp')) return json(200, { status: 'requested' })
    if (url.endsWith('/v1/auth/verify'))
      return json(200, { access_token: 'A', refresh_token: 'R', expires_in: 900 })
    return json(200, { lenses: [] })
  })
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '০১৭১১-২৩৪৫৬৭')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))

  // The same words whether or not the number has an account [D-33].
  expect(await screen.findByText(/If this number has an account/)).toBeInTheDocument()
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual({ phone: '01711234567' })

  await userEvent.type(screen.getByLabelText('Enter the code'), '123456')
  await waitFor(() => expect(readTokens()?.access).toBe('A'))
  const verify = fetchMock.mock.calls.find(([u]) => (u as string).endsWith('/verify'))
  expect(JSON.parse(verify![1].body as string)).toEqual({ phone: '01711234567', code: '123456' })
})

it('shows the string the server named for a wrong code', async () => {
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith('/v1/auth/otp')
      ? json(200, { status: 'requested' })
      : json(400, {
          error: { code: 'VALIDATION', message_key: 'auth.otp.expired', retryable: false },
        }),
  )
  renderScreen(<SignIn />)
  await userEvent.type(screen.getByLabelText('Mobile number'), '01711234567')
  await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
  await userEvent.type(await screen.findByLabelText('Enter the code'), '000000')
  expect(await screen.findByRole('alert')).toHaveTextContent('This code has expired')
  expect(readTokens()).toBeNull()
})
