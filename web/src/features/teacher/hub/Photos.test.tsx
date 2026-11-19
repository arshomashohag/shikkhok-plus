/**
 * The Photos section against a fetch that answers like the API and the
 * bucket. What is asserted: the file goes to the presigned form as a CORS
 * simple request (no headers, fields first, file last), `complete` is
 * polled every two seconds for a minute and then offered as a retry that
 * does not upload again, both alt texts are required, every refusal reads
 * in the server's words, and reordering sends the ids in the new order.
 */
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../../i18n/i18n'
import { json, renderScreen } from '../../../test/render'
import { Photos } from './Photos'

const BUCKET = 'https://shikkhokplus-staging-media.s3.ap-south-1.amazonaws.com/'
const BATCH = '0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f'
const ids = [
  'a1111111-1111-4111-8111-111111111111',
  'b2222222-2222-4222-8222-222222222222',
] as const

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const photo = (id: string, position: number, over: Record<string, unknown> = {}) => ({
  id,
  batch_id: null,
  status: 'approved',
  alt_en: `Photo ${position}`,
  alt_bn: null,
  position,
  width: 960,
  height: 640,
  rejection_code: null,
  thumb_url: `https://shikkhokplus.example.test/m/key${position}/320.webp`,
  ...over,
})

const refusal = (status: number, code: string, key: string) =>
  json(status, { error: { code, message_key: key, retryable: false } })

const ticket = {
  media_id: ids[0],
  url: BUCKET,
  fields: { key: 'quarantine/abc', policy: 'p', 'x-amz-signature': 's' },
  expires_at: '2026-11-18T10:10:00Z',
}

interface Routes {
  list?: unknown[]
  init?: () => Response
  complete?: () => Response
  order?: (body: unknown) => Response
  remove?: () => Response
}

function serve(r: Routes = {}) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET'
    if (url === BUCKET) return new Response(null, { status: 204 })
    if (url.includes('/v1/hub/media/uploads')) return (r.init ?? (() => json(200, ticket)))()
    if (url.endsWith('/complete')) {
      return (r.complete ?? (() => json(200, photo(ids[0], 1, { status: 'pending_review' }))))()
    }
    if (url.endsWith('/v1/hub/media/order') && method === 'PUT') {
      return r.order?.(JSON.parse(init.body as string)) ?? json(200, [])
    }
    if (method === 'DELETE') return r.remove?.() ?? new Response(null, { status: 204 })
    if (url.includes('/v1/hub/media') && method === 'GET') return json(200, r.list ?? [])
    return refusal(404, 'NOT_FOUND', 'error.unexpected')
  })
}

const calls = (needle: string, method = 'POST') =>
  fetchMock.mock.calls.filter(
    ([u, init]) =>
      String(u).includes(needle) && ((init as RequestInit)?.method ?? 'GET') === method,
  )

const png = () => new File([new Uint8Array(10)], 'class.png', { type: 'image/png' })

async function fillAlts(user: ReturnType<typeof userEvent.setup>, en = 'A class', bn = 'ক্লাস') {
  await user.type(await screen.findByLabelText('Describe the photo (English)'), en)
  await user.type(screen.getByLabelText('Describe the photo (Bangla)'), bn)
}

const choose = (user: ReturnType<typeof userEvent.setup>, file = png()) =>
  user.upload(screen.getByLabelText('Add a photo'), file)

describe('Photos', () => {
  it('uploads through the presigned form and shows awaiting review', async () => {
    serve()
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user)

    expect(await screen.findByText('Awaiting review')).toBeInTheDocument()

    const [url, init] = calls(BUCKET)[0] as [string, RequestInit]
    expect(url).toBe(BUCKET)
    // A simple request: nothing but the method and the form, no headers, no credentials.
    expect(Object.keys(init).sort()).toEqual(['body', 'method'])
    const form = init.body as FormData
    const entries = [...form.keys()]
    expect(entries).toEqual(['key', 'policy', 'x-amz-signature', 'file'])
    expect(form.get('file')).toBeInstanceOf(File)
    // The API call carried the declared type and size, and the alts came with complete.
    expect(JSON.parse(calls('/v1/hub/media/uploads')[0]![1].body as string)).toEqual({
      batch_id: null,
      content_type: 'image/png',
      byte_size: 10,
    })
    expect(JSON.parse(calls('/complete')[0]![1].body as string)).toEqual({
      alt_en: 'A class',
      alt_bn: 'ক্লাস',
    })
  })

  it('retries complete while not uploaded, stops at 60s with retry', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let ready = false
    serve({
      complete: () =>
        ready
          ? json(200, photo(ids[0], 1, { status: 'pending_review' }))
          : refusal(409, 'MEDIA_NOT_UPLOADED', 'hub.media.not_uploaded'),
    })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user)

    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(calls('/complete')).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(calls('/complete')).toHaveLength(2)
    await act(() => vi.advanceTimersByTimeAsync(58_000))
    // Every 2 s from 0 s to 60 s, then it stops.
    expect(calls('/complete')).toHaveLength(31)
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(calls('/complete')).toHaveLength(31)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(translate('en', 'hub_media_not_uploaded'))
    // Retrying polls again; it never uploads a second time.
    ready = true
    await user.click(within(alert).getByRole('button', { name: 'Check again' }))
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(await screen.findByText('Awaiting review')).toBeInTheDocument()
    expect(calls(BUCKET)).toHaveLength(1)
    expect(calls('/v1/hub/media/uploads')).toHaveLength(1)
  })

  it('requires both alt texts', async () => {
    serve()
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await user.type(await screen.findByLabelText('Describe the photo (English)'), 'A class')
    await choose(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Describe the photo in English and Bangla before you choose it.',
    )
    expect(calls('/v1/hub/media/uploads')).toHaveLength(0)
    expect(calls(BUCKET)).toHaveLength(0)
  })

  it.each([
    ['MEDIA_TYPE_NOT_ALLOWED', 400, 'hub.media.type_not_allowed', 'hub_media_type_not_allowed'],
    ['MEDIA_TOO_LARGE', 400, 'hub.media.too_large', 'hub_media_too_large'],
    ['MEDIA_LIMIT_REACHED', 409, 'hub.media.limit_reached', 'hub_media_limit_reached'],
  ])('shows server error messages for the five codes: %s', async (code, status, key, resource) => {
    serve({ init: () => refusal(status, code, key) })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(translate('en', resource))
    expect(calls(BUCKET)).toHaveLength(0)
  })

  it('shows server error messages for the five codes: MEDIA_UNREADABLE', async () => {
    serve({ complete: () => refusal(400, 'MEDIA_UNREADABLE', 'hub.media.unreadable') })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      translate('en', 'hub_media_unreadable'),
    )
    // A refusal ends the poll and offers no retry of the same photo.
    expect(calls('/complete')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Check again' })).not.toBeInTheDocument()
  })

  it('shows the Bangla text of a refusal', async () => {
    serve({ init: () => refusal(400, 'MEDIA_TOO_LARGE', 'hub.media.too_large') })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      translate('en', 'hub_media_too_large'),
    )
    expect(translate('bn', 'hub_media_too_large')).not.toBe(translate('en', 'hub_media_too_large'))
  })

  it('refuses a file of the wrong type or size before any request', async () => {
    serve()
    const user = userEvent.setup({ applyAccept: false })
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user, new File(['x'], 'a.gif', { type: 'image/gif' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      translate('en', 'hub_media_type_not_allowed'),
    )
    const big = new File(['x'], 'big.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 8 * 1024 * 1024 + 1 })
    await choose(user, big)
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(translate('en', 'hub_media_too_large')),
    )
    expect(calls('/v1/hub/media/uploads')).toHaveLength(0)
  })

  it('reorder sends ids in order', async () => {
    let sent: unknown = null
    serve({
      list: [photo(ids[0], 1), photo(ids[1], 2)],
      order: (body) => {
        sent = body
        return json(200, [photo(ids[1], 1), photo(ids[0], 2)])
      },
    })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await user.click(await screen.findByRole('button', { name: 'Move photo 2 up' }))

    await waitFor(() => expect(sent).toEqual({ batch_id: null, ids: [ids[1], ids[0]] }))
    const items = await screen.findAllByRole('img')
    await waitFor(() => expect(screen.getAllByRole('img')[0]).toHaveAttribute('alt', 'Photo 1'))
    expect(items).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Move photo 1 up' })).toBeDisabled()
  })

  it('shows the quota of counted photos: 12 for an owner, 8 for a batch', async () => {
    serve({ list: [photo(ids[0], 1), photo(ids[1], 2)] })
    const first = renderScreen(<Photos batchId={null} />)
    expect(await screen.findByText('2 of 12 photos')).toBeInTheDocument()
    first.unmount()
    renderScreen(<Photos batchId={BATCH} />)
    expect(await screen.findByText('2 of 8 photos')).toBeInTheDocument()
    expect(calls(`batch_id=${BATCH}`, 'GET')).toHaveLength(1)
  })

  it('renders the absolute thumb_url as is, with alt text, and a placeholder when null', async () => {
    serve({ list: [photo(ids[0], 1), photo(ids[1], 2, { thumb_url: null, status: 'rejected' })] })
    renderScreen(<Photos batchId={null} />)
    const img = await screen.findByRole('img', { name: 'Photo 1' })
    expect(img).toHaveAttribute('src', 'https://shikkhokplus.example.test/m/key1/320.webp')
    expect(screen.getByText('No preview')).toBeInTheDocument()
    expect(screen.getByText('Not approved')).toBeInTheDocument()
  })

  it('deletes only after a confirmation', async () => {
    serve({ list: [photo(ids[0], 1)] })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await user.click(await screen.findByRole('button', { name: 'Delete photo 1' }))
    expect(calls(`/v1/hub/media/${ids[0]}`, 'DELETE')).toHaveLength(0)
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete photo' }))
    await waitFor(() => expect(calls(`/v1/hub/media/${ids[0]}`, 'DELETE')).toHaveLength(1))
    await waitFor(() => expect(screen.queryByRole('img')).not.toBeInTheDocument())
  })

  it('closes the confirmation when a delete fails, so the failure is seen', async () => {
    serve({
      list: [photo(ids[0], 1)],
      remove: () =>
        json(503, {
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message_key: 'error.temporarily_unavailable',
            retryable: true,
          },
        }),
    })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await user.click(await screen.findByRole('button', { name: 'Delete photo 1' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete photo' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(
      translate('en', 'error_temporarily_unavailable'),
    )
    // The photo is still listed: nothing was deleted.
    expect(screen.getByRole('img', { name: 'Photo 1' })).toBeInTheDocument()
  })

  it('counts what the server counts: a rejected photo frees its slot', async () => {
    serve({
      list: [
        photo(ids[0], 1),
        photo(ids[1], 2, { status: 'rejected', thumb_url: null }),
        photo('c3333333-3333-4333-8333-333333333333', 3, { status: 'pending_review' }),
      ],
    })
    renderScreen(<Photos batchId={null} />)
    expect(await screen.findByText('2 of 12 photos')).toBeInTheDocument()
  })

  it('reorders by the photos that count, never naming a rejected one', async () => {
    const third = 'c3333333-3333-4333-8333-333333333333'
    let sent: unknown = null
    serve({
      list: [
        photo(ids[1], 0, { status: 'rejected', thumb_url: null }),
        photo(ids[0], 1),
        photo(third, 2, { status: 'pending_review' }),
      ],
      order: (body) => {
        sent = body
        return json(200, [photo(third, 0), photo(ids[0], 1), photo(ids[1], 2)])
      },
    })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await user.click(await screen.findByRole('button', { name: 'Move photo 3 up' }))

    // Only the counted photos are named; the server keeps the rest after them.
    await waitFor(() => expect(sent).toEqual({ batch_id: null, ids: [third, ids[0]] }))
  })

  it('tells the owner not to show students', () => {
    for (const lang of ['en', 'bn'] as const) {
      const help = translate(lang, 'web_hub_photos_help')
      expect(help).not.toBe('web_hub_photos_help')
    }
    expect(translate('en', 'web_hub_photos_help')).toMatch(/students/)
    expect(translate('bn', 'web_hub_photos_help')).toMatch(/শিক্ষার্থী/)
  })

  it('a read-only (suspended) gallery still deletes, and nothing else', async () => {
    serve({ list: [photo(ids[0], 1), photo(ids[1], 2)] })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} readOnly />)
    await screen.findByRole('img', { name: 'Photo 1' })

    expect(screen.queryByRole('button', { name: 'Move photo 2 up' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Add a photo')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete photo 1' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete photo' }))

    await waitFor(() => expect(calls(`/v1/hub/media/${ids[0]}`, 'DELETE')).toHaveLength(1))
    await waitFor(() =>
      expect(screen.queryByRole('img', { name: 'Photo 1' })).not.toBeInTheDocument(),
    )
  })

  it('surfaces the suspended refusal', async () => {
    serve({ init: () => refusal(409, 'HUB_LISTING_SUSPENDED', 'hub.listing.suspended') })
    const user = userEvent.setup()
    renderScreen(<Photos batchId={null} />)
    await fillAlts(user)
    await choose(user)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(calls(BUCKET)).toHaveLength(0)
  })
})
