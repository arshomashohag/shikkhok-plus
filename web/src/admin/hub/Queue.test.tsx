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
  target_kind: 'owner_listing',
  target_id: `t${n}`,
  owner_id: owner,
  title: `Teacher ${n}`,
  fields: [
    { key: 'public_name', value: `Teacher ${n}` },
    { key: 'headline_en', value: 'Call me on a number' },
  ],
  reason: 'personal_info',
  note: null,
  reporter_ref: `P-${n}`,
  waited_hours: hours,
})

const BUCKET = 'https://shikkhokplus-media.s3.ap-south-1.amazonaws.com'

const mediaItem = (n: number, reason: string | null = null) => ({
  kind: 'media',
  report_id: null,
  target_kind: 'media',
  target_id: `m${n}`,
  owner_id: `owner-${n}`,
  title: `Teacher ${n}`,
  fields: [
    { key: 'alt_en', value: `Classroom ${n}` },
    { key: 'alt_bn', value: `শ্রেণিকক্ষ ${n}` },
  ],
  reason,
  note: null,
  reporter_ref: null,
  waited_hours: 2,
})

const preview = (id: string, w: number) => ({
  width: w,
  url: `${BUCKET}/archive/${id}/${w}.webp?X-Amz-Expires=300&X-Amz-Signature=${id}${w}`,
})

const mediaDetail = (n: number, status = 'pending_review') => ({
  media_id: `m${n}`,
  status,
  width: 1600,
  height: 1200,
  previews: [preview(`m${n}`, 320), preview(`m${n}`, 960), preview(`m${n}`, 1600)],
  alt_en: `Classroom ${n}`,
  alt_bn: `শ্রেণিকক্ষ ${n}`,
  public_name: `Teacher ${n}`,
  public_title: null,
  report_count: status === 'held' ? 1 : 0,
})

/** Serve the media queue and each photo's detail; record decisions. */
function serveMedia(items: ReturnType<typeof mediaItem>[], held: string[] = []) {
  return serveAdmin((method, url, body) => {
    if (url.includes('/v1/admin/hub/queue'))
      return json(200, { kind: 'media', items: url.includes('kind=media') ? items : [] })
    const decided = url.match(/\/v1\/admin\/hub\/media\/(m\d+)\/decision$/)
    if (method === 'POST' && decided) {
      const decision = (body as { decision: string }).decision
      return json(200, {
        media_id: decided[1],
        status: decision === 'approve' ? 'approved' : 'rejected',
      })
    }
    const read = url.match(/\/v1\/admin\/hub\/media\/m(\d+)$/)
    if (method === 'GET' && read) {
      const n = Number(read[1])
      return json(200, mediaDetail(n, held.includes(`m${n}`) ? 'held' : 'pending_review'))
    }
    return undefined
  })
}

describe('Admin hub queue', () => {
  it('media tab approves and rejects', async () => {
    const calls = serveMedia([mediaItem(1), mediaItem(2, 'child_safety')], ['m2'])
    renderAdmin('/hub')
    await userEvent.click(await screen.findByRole('button', { name: 'Photos' }))

    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]!).getByText('Classroom 1')).toBeInTheDocument()
    // Status and previews come from each photo's own read.
    expect(await within(rows[1]!).findByText('Held after a report')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Reason: Child safety')).toBeInTheDocument()
    expect(within(rows[1]!).getByText(/Reports: 1 · Waiting 2 h/)).toBeInTheDocument()
    await within(rows[0]!).findByRole('img', { name: 'Classroom 1' })

    // Approve waits for the checklist line to be ticked.
    const approve = within(rows[0]!).getByRole('button', { name: 'Approve' })
    expect(approve).toBeDisabled()
    await userEvent.click(
      within(rows[0]!).getByRole('checkbox', { name: 'No identifiable student in the photo' }),
    )
    await userEvent.click(approve)
    expect(within(rows[0]!).getByText('Approve this photo?')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    await userEvent.click(within(rows[0]!).getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')).toMatchObject({
        url: '/v1/admin/hub/media/m1/decision',
        body: { decision: 'approve' },
      }),
    )

    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    const again = screen.getAllByRole('listitem')
    await userEvent.selectOptions(
      within(again[1]!).getByRole('combobox', { name: 'Rejection reason' }),
      'identifiable_child',
    )
    await userEvent.click(within(again[1]!).getByRole('button', { name: 'Reject' }))
    expect(within(again[1]!).getByText('Reject this photo?')).toBeInTheDocument()
    await userEvent.click(within(again[1]!).getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'POST')[1]).toMatchObject({
        url: '/v1/admin/hub/media/m2/decision',
        body: { decision: 'reject', code: 'identifiable_child' },
      }),
    )
    expect(calls.some((c) => c.url.includes('kind=media'))).toBe(true)
  })

  it('preview images load from presigned URLs', async () => {
    serveMedia([mediaItem(1)])
    renderAdmin('/hub?tab=media')

    const image = await screen.findByRole('img', { name: 'Classroom 1' })
    expect(image).toHaveAttribute('src', preview('m1', 960).url)
    const srcset = image.getAttribute('srcset') ?? ''
    for (const w of [320, 960, 1600]) expect(srcset).toContain(`${preview('m1', w).url} ${w}w`)
    // Nothing from the bucket is fetched by the app itself: the browser loads it.
    expect(screen.getByText('No identifiable student in the photo')).toBeInTheDocument()
  })

  it('names the checklist line in Bangla too', async () => {
    const { ADMIN_BN } = await import('../strings')
    expect(ADMIN_BN['web_admin_hub_media_check']).toBe(
      'ছবিতে শনাক্ত করা যায় এমন কোনো শিক্ষার্থী নেই',
    )
  })

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

  it('names the target kind and shows every submitted field with its label', async () => {
    serveAdmin((_m, url) =>
      url.includes('/v1/admin/hub/queue')
        ? json(200, {
            kind: 'report',
            items: [
              {
                ...report(1, 5),
                target_kind: 'batch_listing',
                title: 'HSC Physics',
                fields: [
                  { key: 'public_title', value: 'HSC Physics' },
                  { key: 'description_en', value: 'Weekend batch' },
                  { key: 'syllabus_bn', value: 'সিলেবাস' },
                  { key: 'subject_tags', value: 'physics, maths' },
                ],
              },
              report(2, 3),
            ],
          })
        : undefined,
    )
    renderAdmin('/hub')
    const rows = await screen.findAllByRole('listitem')
    expect(within(rows[0]!).getByText('Batch page')).toBeInTheDocument()
    // The title is the row's heading, not repeated as a field.
    expect(within(rows[0]!).getAllByText('HSC Physics')).toHaveLength(1)
    expect(within(rows[0]!).getByText('Description (English)')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('Weekend batch')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('Syllabus (Bangla)')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('সিলেবাস')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('physics, maths')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Teacher or centre page')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Headline (English)')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Call me on a number')).toBeInTheDocument()
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
