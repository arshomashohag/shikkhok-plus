/**
 * Members and the timetable as screens: rows a re-read could not confirm
 * are shown under a banner and cannot be acted on, and a week switch
 * never shows the old week's classes.
 */
import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
