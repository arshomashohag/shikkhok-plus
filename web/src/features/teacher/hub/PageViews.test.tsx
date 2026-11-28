/**
 * The owner's page-view counts [0050] on the listing editor.
 *
 * What is asserted: the owner page's and each viewed batch page's counts
 * are shown in both windows, a batch is named by the owner's own batch
 * name, a batch no longer listed still shows its counts, the card says the
 * counts are visits and not people, and a failed read draws nothing.
 */
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate } from '../../../i18n/i18n'
import { json, renderScreen } from '../../../test/render'
import { OwnerPageViews } from './hubUi'

const en = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const VIEWS = {
  owner_page: { last_7_days: 5, last_30_days: 11 },
  batches: [
    { batch_id: 'b1', last_7_days: 4, last_30_days: 10 },
    { batch_id: 'gone', last_7_days: 0, last_30_days: 2 },
  ],
}

const BATCHES = [{ batch_id: 'b1', batch_name: 'Physics · Batch A' }]

function serve(views: () => Response) {
  fetchMock.mockImplementation(async (url: string) => {
    const path = url.split('?')[0]!
    if (path.endsWith('/v1/hub/listing/views')) return views()
    if (path.endsWith('/v1/hub/batch-listings')) return json(200, BATCHES)
    return json(404, {
      error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
    })
  })
}

describe('OwnerPageViews', () => {
  it('shows each page in both windows, says it counts visits', async () => {
    serve(() => json(200, VIEWS))
    renderScreen(<OwnerPageViews />, '/more/hub')

    expect(await screen.findByText(en('web_hub_views_title'))).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_views_explain'))).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_views_owner_page'))).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_views_counts', 5, 11))).toBeInTheDocument()
    expect(screen.getByText('Physics · Batch A')).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_views_counts', 4, 10))).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_views_batch_gone'))).toBeInTheDocument()
    expect(screen.getByText(en('web_hub_views_counts', 0, 2))).toBeInTheDocument()
  })

  it('draws nothing when the counts cannot be read', async () => {
    serve(() =>
      json(500, {
        error: { code: 'INTERNAL', message_key: 'error.unexpected', retryable: true },
      }),
    )
    const { container } = renderScreen(<OwnerPageViews />, '/more/hub')

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/listing/views'))).toBe(true),
    )
    expect(screen.queryByText(en('web_hub_views_title'))).toBeNull()
    expect(container.querySelector('section')).toBeNull()
  })
})
