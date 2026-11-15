/**
 * Members and the timetable as screens: rows a re-read could not confirm
 * are shown under a banner and cannot be acted on, and a week switch
 * never shows the old week's classes.
 */
import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate, translateMessage } from '../../../i18n/i18n'
import { json, renderScreen } from '../../../test/render'
import { Members } from './Members'
import { Timetable } from './Timetable'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const member = (id: string, name: string) => ({
  member_id: id,
  display_name: name,
  phone: '+8801711111111',
  role: 'teacher',
  decision: 'accepted',
  invited_at: '2026-11-06T00:00:00Z',
  revoked: false,
  is_you: false,
})

describe('Members', () => {
  it('shows a failed re-read and allows no removal until a read succeeds', async () => {
    fetchMock.mockResolvedValueOnce(json(200, [member('m0', 'You'), member('m1', 'Sumi')]))
    renderScreen(<Members />)
    const remove = await screen.findAllByRole('button', { name: 'Remove' })
    expect(remove[0]).toBeEnabled()
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    expect(await screen.findByText('Offline.')).toBeInTheDocument()
    for (const b of screen.getAllByRole('button', { name: 'Remove' })) expect(b).toBeDisabled()
  })

  // Regression, written first [functional-spec § 1 defect 2]: one
  // email-only invitation used to throw in render and blank the page for
  // every manager, so no one could reach the screen that revokes access.
  it('renders a member invited by email only, with no phone, and does not throw', async () => {
    fetchMock.mockResolvedValueOnce(
      json(200, [
        member('m0', 'You'),
        { ...member('m1', 'Rina'), phone: null, invited_email: 'rina@example.com' },
      ]),
    )
    renderScreen(<Members />)
    expect(await screen.findByText(/rina@example\.com/)).toBeInTheDocument()
    expect(screen.getByText('Rina')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(2)
  })
})

describe('Members — invite by phone or email [FR6.4] [W8]', () => {
  const invites = () =>
    fetchMock.mock.calls.filter(
      ([u, i]) =>
        (u as string).endsWith('/v1/centre/members') && (i as RequestInit).method === 'POST',
    )

  async function openInvite(post: () => Response) {
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) =>
      url.endsWith('/v1/centre/members') && init.method === 'POST'
        ? post()
        : json(200, [member('m0', 'You'), member('m1', 'Sumi')]),
    )
    renderScreen(<Members />)
    await screen.findByText('Sumi')
    await userEvent.click(screen.getByRole('button', { name: /Invite/ }))
  }

  it('an email-only invite posts the email and no phone', async () => {
    await openInvite(() =>
      json(201, { ...member('m2', 'Rina'), phone: null, invited_email: 'rina@example.com' }),
    )
    await userEvent.type(screen.getByLabelText(/Name/), 'Rina')
    const email = screen.getByLabelText(translate('en', 'centre_invite_email_label'))
    expect(email).toHaveAttribute('autocomplete', 'off')
    expect(screen.getByText(translate('en', 'centre_invite_by_help'))).toBeInTheDocument()
    await userEvent.type(email, 'Rina@Example.com')
    await userEvent.click(
      screen.getByRole('button', { name: translate('en', 'centre_invite_submit') }),
    )
    await waitFor(() => expect(invites()).toHaveLength(1))
    const body = JSON.parse((invites()[0]![1] as RequestInit).body as string) as Record<
      string,
      unknown
    >
    expect(body).toEqual({ display_name: 'Rina', email: 'rina@example.com', role: 'teacher' })
    expect(body).not.toHaveProperty('phone')
  })

  it('Invite stays disabled with a name and neither contact', async () => {
    await openInvite(() => json(201, member('m2', 'Rina')))
    await userEvent.type(screen.getByLabelText(/Name/), 'Rina')
    expect(
      screen.getByRole('button', { name: translate('en', 'centre_invite_submit') }),
    ).toBeDisabled()
  })

  it('centre.member.already_invited shows in the banner, in its reworded string', async () => {
    await openInvite(() =>
      json(409, {
        error: { code: 'CONFLICT', message_key: 'centre.member.already_invited', retryable: false },
      }),
    )
    await userEvent.type(screen.getByLabelText(/Name/), 'Rina')
    await userEvent.type(
      screen.getByLabelText(translate('en', 'centre_invite_email_label')),
      'rina@example.com',
    )
    await userEvent.click(
      screen.getByRole('button', { name: translate('en', 'centre_invite_submit') }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      translateMessage('en', 'centre.member.already_invited'),
    )
    expect(translateMessage('en', 'centre.member.already_invited')).toContain('contact')
  })
})

describe('Timetable', () => {
  it('drops this week’s classes while the next week loads', async () => {
    const cls = {
      session_id: 'c1',
      batch_id: 'b1',
      batch_name: 'Physics A',
      subject: null,
      date: new Date().toISOString().slice(0, 10),
      start_time: '16:00:00',
      duration_minutes: 60,
      status: 'scheduled',
      teacher_member_id: null,
      teacher_name: null,
      room_id: null,
      room_name: null,
      overridden: false,
    }
    let calls = 0
    fetchMock.mockImplementation((url: string) => {
      if (!url.includes('/v1/centre/timetable')) return Promise.resolve(json(200, []))
      calls += 1
      return calls === 1 ? Promise.resolve(json(200, [cls])) : new Promise<Response>(() => {})
    })
    renderScreen(<Timetable />)
    expect(await screen.findByText('Physics A')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Next week/ }))
    expect(screen.queryByText('Physics A')).toBeNull()
  })
})
