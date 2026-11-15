/**
 * The moderation queue against a mocked admin API: rows in the order the
 * server sends them, and nothing written until an act is confirmed.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json } from '../../test/render'
import '../strings'
import { resetAdminSessionForTests } from '../session'
import { renderAdmin, serveAdmin, type Call } from '../test/renderAdmin'

afterEach(() => {
  vi.unstubAllGlobals()
  resetAdminSessionForTests()
  sessionStorage.clear()
})

const report = (n: number, hours: number, owner: string | null = `owner-${n}`) => ({
  kind: 'report',
  report_id: `r${n}`,
  target_kind: 'listing',
  target_id: `t${n}`,
  owner_id: owner,
  title: `Teacher ${n}`,
  text: 'Call me on a number',
  reason: 'personal_info',
  note: null,
  reporter_ref: `P-${n}`,
  waited_hours: hours,
})

describe('Admin hub queue', () => {
  it('lists reports oldest first and suspends an owner after confirm', async () => {
    let calls: Call[] = []
    calls = serveAdmin((method, url) => {
      if (url.includes('/v1/admin/hub/queue'))
        return json(200, { kind: 'report', items: [report(1, 52), report(2, 3)] })
      if (method === 'PUT' && url.includes('/suspension'))
        return json(200, { owner_id: 'owner-1', suspended: true })
      return undefined
    })
    renderAdmin('/hub')

    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(2)
    // As served: the oldest wait first.
    expect(within(rows[0]!).getByText('Teacher 1')).toBeInTheDocument()
    expect(within(rows[0]!).getByText(/Waiting 52 h/)).toBeInTheDocument()
    expect(within(rows[1]!).getByText(/Waiting 3 h/)).toBeInTheDocument()
    expect(calls.some((c) => c.url.includes('kind=report'))).toBe(true)

    await userEvent.selectOptions(within(rows[0]!).getByRole('combobox'), 'child_safety')
    await userEvent.click(within(rows[0]!).getByRole('button', { name: 'Suspend listing' }))
    // The confirmation is in the page, and nothing has been sent yet.
    expect(within(rows[0]!).getByText("Suspend this owner's listing?")).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)

    await userEvent.click(within(rows[0]!).getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')).toMatchObject({
        url: '/v1/admin/hub/owners/owner-1/suspension',
        body: { suspended: true, reason_code: 'child_safety' },
      }),
    )
  })

  it('sends nothing when a decision is cancelled', async () => {
    const calls = serveAdmin((_m, url) =>
      url.includes('/v1/admin/hub/queue')
        ? json(200, { kind: 'report', items: [report(1, 5)] })
        : undefined,
    )
    renderAdmin('/hub')
    await userEvent.click(await screen.findByRole('button', { name: 'Dismiss' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(calls.filter((c) => c.method !== 'GET')).toEqual([])
  })

  it('upholds a report after confirm', async () => {
    const calls = serveAdmin((method, url) => {
      if (url.includes('/v1/admin/hub/queue'))
        return json(200, { kind: 'report', items: [report(1, 5)] })
      if (method === 'POST') return json(200, { report_id: 'r1', status: 'upheld' })
      return undefined
    })
    renderAdmin('/hub')
    await userEvent.click(await screen.findByRole('button', { name: 'Uphold' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')).toMatchObject({
        url: '/v1/admin/hub/reports/r1/decision',
        body: { decision: 'upheld' },
      }),
    )
  })

  it('lifts a suspension from the Suspended listings tab', async () => {
    const calls = serveAdmin((method, url) => {
      if (url.includes('kind=listing'))
        return json(200, {
          kind: 'listing',
          items: [
            {
              ...report(1, 70, 'owner-9'),
              kind: 'listing',
              report_id: null,
              reason: 'fake',
              reporter_ref: null,
            },
          ],
        })
      if (url.includes('/v1/admin/hub/queue')) return json(200, { kind: 'report', items: [] })
      if (method === 'PUT') return json(200, { owner_id: 'owner-9', suspended: false })
      return undefined
    })
    renderAdmin('/hub')
    await userEvent.click(await screen.findByRole('button', { name: 'Suspended listings' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Lift suspension' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')).toMatchObject({
        url: '/v1/admin/hub/owners/owner-9/suspension',
        body: { suspended: false, reason_code: 'fake' },
      }),
    )
  })

  it('moves focus to Confirm, and back to the trigger on Cancel', async () => {
    serveAdmin((_m, url) =>
      url.includes('/v1/admin/hub/queue')
        ? json(200, { kind: 'report', items: [report(1, 5)] })
        : undefined,
    )
    renderAdmin('/hub')
    const dismiss = await screen.findByRole('button', { name: 'Dismiss' })
    await userEvent.click(dismiss)
    expect(screen.getByRole('button', { name: 'Confirm' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Dismiss' })).toHaveFocus()
  })
})
