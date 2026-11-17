/**
 * The listing editor and the batch listings against a fetch that answers
 * like the API. What is asserted is that the screen renders the server's
 * decisions: the checklist and `publishable` drive Publish, a suspended
 * listing is read-only, money stays the server's string, and a failed
 * save keeps the form.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { json, renderScreen } from '../../../test/render'
import { BatchListings } from './BatchListings'
import { HubListing } from './Listing'
import { NameConsent } from './NameConsent'
import { translate } from '../../../i18n/i18n'

const fetchMock = vi.fn()
beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const checklist = (done: boolean) =>
  ['public_name', 'slug', 'area', 'headline', 'bio', 'contact_or_none'].map((key) => ({
    key,
    done: key === 'contact_or_none' ? true : done,
  }))

const listing = (over: Record<string, unknown> = {}) => ({
  status: 'draft',
  slug: 'sumi-apa',
  public_name: 'Sumi Akter',
  public_name_latin: null,
  headline_en: 'Maths and science',
  headline_bn: null,
  bio_en: 'Ten years of teaching.',
  bio_bn: null,
  qualifications: null,
  teaching_mode: ['in_person'],
  district_code: null,
  upazila_code: null,
  street_address: null,
  public_contact_phone: null,
  consent_version: null,
  published_at: null,
  checklist: checklist(true),
  publishable: true,
  runs_classes: false,
  consent_version_current: '2026-11-14',
  is_centre: false,
  ...over,
})

/** Answer the editor's reads; `listingBody` is what GET /v1/hub/listing returns. */
function serve(
  listingBody: unknown,
  extra?: (url: string, init: RequestInit) => Response | undefined,
) {
  fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const made = extra?.(url, init)
    if (made) return made
    if (url.endsWith('/v1/hub/listing') && (init.method ?? 'GET') === 'GET')
      return json(200, listingBody)
    if (url.includes('/v1/hub/areas')) return json(200, [])
    return json(404, {
      error: { code: 'NOT_FOUND', message_key: 'error.unexpected', retryable: false },
    })
  })
}

describe('HubListing', () => {
  it('renders checklist from server and disables Publish until publishable', async () => {
    serve(listing({ checklist: checklist(false), publishable: false }))
    renderScreen(<HubListing />)
    const list = await screen.findByRole('list', { name: 'Before you publish' })
    expect(within(list).getAllByText('Still needed').length).toBe(5)
    expect(within(list).getByText('Done')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled()
  })

  it('enables Publish when the server says publishable, and shows the badge it sends', async () => {
    serve(listing({ runs_classes: true }))
    renderScreen(<HubListing />)
    expect(await screen.findByText('Runs classes on ShikkhokPlus')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Publish' })).toBeEnabled()
  })

  it('publish sheet sends consent_version from the response', async () => {
    let posted: unknown = null
    serve(listing({ consent_version_current: '2031-01-01' }), (url, init) => {
      if (url.endsWith('/v1/hub/listing/publish') && init.method === 'POST') {
        posted = JSON.parse(init.body as string)
        return json(200, listing({ status: 'published', consent_version_current: '2031-01-01' }))
      }
      return undefined
    })
    renderScreen(<HubListing />)
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/unpublish at any time/i)).toBeInTheDocument()
    const confirm = within(dialog).getByRole('button', { name: 'Publish listing' })
    expect(confirm).toBeDisabled()
    await userEvent.click(within(dialog).getByRole('checkbox'))
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)
    await waitFor(() => expect(posted).toEqual({ consent_version: '2031-01-01' }))
    expect(await screen.findByText('Published')).toBeInTheDocument()
  })

  it('shows suspended banner and read-only fields when status is suspended', async () => {
    serve(listing({ status: 'suspended' }))
    renderScreen(<HubListing />)
    expect(await screen.findByText('This listing has been suspended')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Appeal through Help' })).toHaveAttribute(
      'href',
      '/help/new',
    )
    expect(screen.getByLabelText('Public name')).toBeDisabled()
    expect(screen.getByLabelText('Web address')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Publish' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull()
  })

  it('a failed save shows retry and keeps the form', async () => {
    let puts = 0
    serve(listing(), (_url, init) => {
      if (init.method !== 'PUT') return undefined
      puts += 1
      if (puts === 1) throw new TypeError('Failed to fetch')
      return json(200, listing({ public_name: 'Sumi Apa' }))
    })
    renderScreen(<HubListing />)
    const name = await screen.findByLabelText('Public name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Sumi Apa')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/not saved/)).toBeInTheDocument()
    // Nothing typed is lost.
    expect(screen.getByLabelText('Public name')).toHaveValue('Sumi Apa')
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(puts).toBe(2))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(screen.getByLabelText('Public name')).toHaveValue('Sumi Apa')
  })

  it('sends only the fields that changed', async () => {
    let body: unknown = null
    serve(listing(), (_url, init) => {
      if (init.method !== 'PUT') return undefined
      body = JSON.parse(init.body as string)
      return json(200, listing({ headline_en: 'Changed' }))
    })
    renderScreen(<HubListing />)
    const headline = await screen.findByLabelText('Headline (English)')
    await userEvent.clear(headline)
    await userEvent.type(headline, 'Changed')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(body).toEqual({ headline_en: 'Changed' }))
  })

  it('edits the optional Latin name and sends only it', async () => {
    let body: unknown = null
    serve(listing({ public_name: 'সুমি আক্তার' }), (_url, init) => {
      if (init.method !== 'PUT') return undefined
      body = JSON.parse(init.body as string)
      return json(200, listing({ public_name: 'সুমি আক্তার', public_name_latin: 'Sumi Akter' }))
    })
    renderScreen(<HubListing />)
    const latin = await screen.findByLabelText('Name in English letters (optional)')
    expect(latin).toHaveValue('')
    expect(latin).toHaveAttribute('maxLength', '120')
    await userEvent.type(latin, ' Sumi Akter ')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(body).toEqual({ public_name_latin: 'Sumi Akter' }))
    await waitFor(() =>
      expect(screen.getByLabelText('Name in English letters (optional)')).toHaveValue('Sumi Akter'),
    )
  })

  it('area pickers go division, district, upazila from /v1/hub/areas', async () => {
    const area = (code: string, kind: string, en: string) => ({
      code,
      kind,
      name_en: en,
      name_bn: en,
    })
    serve(listing(), (url) => {
      if (!url.includes('/v1/hub/areas')) return undefined
      if (url.includes('parent=BD2019')) return json(200, [area('BD20190040', 'upazila', 'Savar')])
      if (url.includes('parent=BD20')) return json(200, [area('BD2019', 'district', 'Dhaka')])
      return json(200, [area('BD20', 'division', 'Dhaka Division')])
    })
    renderScreen(<HubListing />)
    await screen.findByRole('option', { name: 'Dhaka Division' })
    await userEvent.selectOptions(screen.getByLabelText('Division'), 'BD20')
    await screen.findByRole('option', { name: 'Dhaka' })
    await userEvent.selectOptions(screen.getByLabelText('District'), 'BD2019')
    await screen.findByRole('option', { name: 'Savar' })
    await userEvent.selectOptions(
      screen.getByLabelText('Upazila or city corporation'),
      'BD20190040',
    )
    expect(screen.getByLabelText('Upazila or city corporation')).toHaveValue('BD20190040')
    expect(screen.queryByLabelText('Thana (optional)')).toBeNull()
  })

  it('a city corporation opens an optional thana picker, and a saved thana reopens under its city', async () => {
    const area = (code: string, kind: string, en: string) => ({
      code,
      kind,
      name_en: en,
      name_bn: en,
    })
    const tree: Record<string, unknown[]> = {
      '': [area('BD30', 'division', 'Dhaka Division')],
      BD30: [area('BD3026', 'district', 'Dhaka')],
      BD3026: [
        area('BD30260072', 'upazila', 'Savar'),
        area('BD30262500', 'city_corporation', 'Dhaka North City Corporation'),
      ],
      BD30262500: [
        area('MT3026250003', 'metro_thana', 'Mirpur'),
        area('MT3026250006', 'metro_thana', 'Uttara'),
      ],
    }
    const puts: unknown[] = []
    serve(listing({ district_code: 'BD3026', upazila_code: 'MT3026250003' }), (url, init) => {
      if (init.method === 'PUT') {
        const sent = JSON.parse(init.body as string) as { upazila_code: string }
        puts.push(sent)
        return json(200, listing({ district_code: 'BD3026', upazila_code: sent.upazila_code }))
      }
      if (!url.includes('/v1/hub/areas')) return undefined
      const parent = new URL(url, 'http://test').searchParams.get('parent') ?? ''
      return json(200, tree[parent] ?? [])
    })
    renderScreen(<HubListing />)

    // The saved thana's city corporation is found and both are shown chosen.
    const thana = await screen.findByLabelText('Thana (optional)')
    await waitFor(() => expect(thana).toHaveValue('MT3026250003'))
    expect(screen.getByLabelText('Upazila or city corporation')).toHaveValue('BD30262500')

    // Leaving the thana blank keeps the city corporation.
    await userEvent.selectOptions(thana, '')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() =>
      expect(puts).toEqual([{ district_code: 'BD3026', upazila_code: 'BD30262500' }]),
    )

    // Choosing a thana stores the thana.
    await userEvent.selectOptions(screen.getByLabelText('Thana (optional)'), 'MT3026250006')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(puts).toHaveLength(2))
    expect(puts[1]).toEqual({ district_code: 'BD3026', upazila_code: 'MT3026250006' })

    // An upazila closes the thana picker again.
    await userEvent.selectOptions(
      screen.getByLabelText('Upazila or city corporation'),
      'BD30260072',
    )
    expect(screen.queryByLabelText('Thana (optional)')).toBeNull()
  })
})

const batch = (over: Record<string, unknown> = {}) => ({
  batch_id: 'b1',
  batch_name: 'Physics A',
  subjects: ['Physics'],
  status: 'draft',
  slug: null,
  public_title: null,
  description_en: null,
  description_bn: null,
  syllabus_en: null,
  syllabus_bn: null,
  class_levels: [],
  curriculum: null,
  subject_tags: [],
  mode: null,
  admissions: null,
  show_fee: true,
  show_schedule: false,
  fee: '1200.00',
  teacher_names: ['Centre faculty'],
  checklist: [{ key: 'slug', done: false }],
  publishable: false,
  ...over,
})

describe('BatchListings', () => {
  it('batch row shows Centre faculty from teacher_names', async () => {
    fetchMock.mockResolvedValue(json(200, [batch()]))
    renderScreen(<BatchListings />)
    expect(await screen.findByText('Physics A')).toBeInTheDocument()
    expect(screen.getByText('Taught by Centre faculty')).toBeInTheDocument()
  })

  it('fee is shown via the server money string, never parsed to a number', async () => {
    // A string a float round trip would change ("1200.50" -> 1200.5).
    fetchMock.mockResolvedValue(json(200, [batch({ fee: '1200.50' })]))
    renderScreen(<BatchListings />)
    expect(await screen.findByText('Fee ৳1200.50')).toBeInTheDocument()
  })

  it('says the fee is not public when the server sends none', async () => {
    fetchMock.mockResolvedValue(json(200, [batch({ fee: null, show_fee: false })]))
    renderScreen(<BatchListings />)
    expect(await screen.findByText('Fee not shown publicly')).toBeInTheDocument()
  })

  it('wraps a long Bangla batch name instead of truncating it', async () => {
    const name = 'উচ্চতর গণিত ও পদার্থবিজ্ঞান সম্মিলিত প্রস্তুতি ব্যাচ — এসএসসি পরীক্ষার্থীদের জন্য'
    fetchMock.mockResolvedValue(json(200, [batch({ batch_name: name })]))
    renderScreen(<BatchListings />)
    const title = await screen.findByText(name)
    expect(title).toHaveStyle({ overflowWrap: 'anywhere' })
  })
})

describe('street address', () => {
  it('is shown only when the server says the owner is a centre', async () => {
    serve(listing({ is_centre: false }))
    const solo = renderScreen(<HubListing />)
    await screen.findByLabelText('Public name')
    expect(screen.queryByLabelText('Street address')).toBeNull()
    solo.unmount()
    serve(listing({ is_centre: true }))
    renderScreen(<HubListing />)
    expect(await screen.findByLabelText('Street address')).toBeInTheDocument()
  })
})

describe('area load failure', () => {
  it('shows an error with Retry instead of empty pickers', async () => {
    let fail = true
    serve(listing(), (url) => {
      if (!url.includes('/v1/hub/areas')) return undefined
      if (fail)
        return json(500, {
          error: { code: 'X', message_key: 'error.unexpected', retryable: true },
        })
      return json(200, [
        { code: 'BD20', kind: 'division', name_en: 'Dhaka Division', name_bn: 'ঢাকা' },
      ])
    })
    renderScreen(<HubListing />)
    const alert = await screen.findByText('Areas could not be loaded.')
    fail = false
    await userEvent.click(
      within(alert.closest('[role="alert"]') as HTMLElement).getByRole('button', { name: 'Retry' }),
    )
    expect(await screen.findByRole('option', { name: 'Dhaka Division' })).toBeInTheDocument()
  })
})

describe('Centre faculty wording', () => {
  it('localizes the server fallback and uses a natural Bangla form', () => {
    expect(translate('bn', 'web_hub_batch_teachers', 'ক')).toBe('শিক্ষক: ক')
    expect(translate('bn', 'web_hub_centre_faculty')).toBe('সেন্টারের শিক্ষকবৃন্দ')
  })
})

describe('NameConsent', () => {
  const memberships = (consent: boolean) => [
    {
      member_id: 'm1',
      centre_id: 'c1',
      centre_name: 'Udoy Coaching',
      role: 'teacher',
      public_name_consent: consent,
      name_shown: 'Karim Sir',
    },
  ]

  it('reflects the server state and calls the endpoint when toggled', async () => {
    let put: unknown = null
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/me/centre-memberships')) return json(200, memberships(false))
      if (url.endsWith('/centres/c1/members/me/public-name-consent') && init.method === 'PUT') {
        put = JSON.parse(init.body as string)
        return new Response(null, { status: 204 })
      }
      return json(404, {})
    })
    renderScreen(<NameConsent />)
    const box = await screen.findByRole('checkbox', {
      name: /Show my name on the centre’s public listing/,
    })
    expect(screen.getByText('Udoy Coaching')).toBeInTheDocument()
    expect(box).not.toBeChecked()
    await userEvent.click(box)
    await waitFor(() => expect(put).toEqual({ consent: true }))
    expect(box).toBeChecked()
  })

  it('shows Retry on failure and keeps the previous state', async () => {
    let puts = 0
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/me/centre-memberships')) return json(200, memberships(true))
      if (init.method === 'PUT') {
        puts += 1
        if (puts === 1) throw new TypeError('Failed to fetch')
        return new Response(null, { status: 204 })
      }
      return json(404, {})
    })
    renderScreen(<NameConsent />)
    const box = await screen.findByRole('checkbox')
    expect(box).toBeChecked()
    await userEvent.click(box)
    const alert = await screen.findByRole('alert')
    expect(box).toBeChecked()
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(puts).toBe(2))
    await waitFor(() => expect(box).not.toBeChecked())
  })

  it('renders nothing for an account with no accepted memberships', async () => {
    fetchMock.mockResolvedValue(json(200, []))
    const { container } = renderScreen(<NameConsent />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(container.querySelector('input')).toBeNull()
  })
})

describe('batch vocabulary', () => {
  it('saves class levels and curriculum as vocabulary values, not free text', async () => {
    let body: Record<string, unknown> | null = null
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/hub/batch-listings')) return json(200, [batch()])
      if (url.endsWith('/v1/batches/b1/listing') && init.method === 'PUT') {
        body = JSON.parse(init.body as string)
        return json(200, batch({ class_levels: ['class_9', 'class_10'] }))
      }
      return json(404, {})
    })
    renderScreen(<BatchListings />)
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText(/for example 9, 10/)).toBeNull()
    const levels = within(dialog).getByRole('group', { name: 'Class levels' })
    await userEvent.click(within(levels).getByRole('button', { name: 'Class 9' }))
    await userEvent.click(within(levels).getByRole('button', { name: 'Class 10' }))
    expect(within(levels).getByRole('button', { name: 'Class 9' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await userEvent.selectOptions(
      within(dialog).getByLabelText('Curriculum'),
      'National curriculum (Bangla version)',
    )
    await userEvent.type(within(dialog).getByLabelText('Public title'), 'SSC Physics')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({
      class_levels: ['class_9', 'class_10'],
      curriculum: 'national_bangla',
      public_title: 'SSC Physics',
    })
  })

  it('shows saved levels and curriculum in words, never raw values', async () => {
    fetchMock.mockResolvedValue(
      json(200, [batch({ class_levels: ['class_9', 'hsc'], curriculum: 'madrasah' })]),
    )
    renderScreen(<BatchListings />)
    expect(await screen.findByText('Class 9, HSC · Madrasah')).toBeInTheDocument()
    expect(screen.queryByText(/class_9/)).toBeNull()
  })

  it('has a Bangla label for every class level and curriculum', () => {
    expect(translate('bn', 'web_hub_level_class_9')).toBe('নবম শ্রেণি')
    expect(translate('bn', 'web_hub_curriculum_madrasah')).toBe('মাদ্রাসা')
  })
})

describe('text limits', () => {
  it('match the server: headline 140, biography 4000, street 200', async () => {
    serve(listing({ is_centre: true }))
    renderScreen(<HubListing />)
    expect(await screen.findByLabelText('Headline (English)')).toHaveAttribute('maxLength', '140')
    expect(screen.getByLabelText('About you (Bangla)')).toHaveAttribute('maxLength', '4000')
    expect(screen.getByLabelText('Street address')).toHaveAttribute('maxLength', '200')
  })

  it('match the server on a batch: title 120, description and syllabus 4000', async () => {
    fetchMock.mockResolvedValue(json(200, [batch()]))
    renderScreen(<BatchListings />)
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Public title')).toHaveAttribute('maxLength', '120')
    expect(within(dialog).getByLabelText('Description (English)')).toHaveAttribute(
      'maxLength',
      '4000',
    )
    expect(within(dialog).getByLabelText('Syllabus (Bangla)')).toHaveAttribute('maxLength', '4000')
  })
})

describe('outdated consent', () => {
  it('reloads the listing and publishes with the new consent version', async () => {
    let gets = 0
    const posted: unknown[] = []
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/hub/listing') && (init.method ?? 'GET') === 'GET') {
        gets += 1
        return json(
          200,
          listing({ consent_version_current: gets === 1 ? '2026-11-14' : '2027-01-01' }),
        )
      }
      if (url.endsWith('/v1/hub/listing/publish')) {
        const sent = JSON.parse(init.body as string)
        posted.push(sent)
        if (sent.consent_version !== '2027-01-01')
          return json(400, {
            error: {
              code: 'HUB_CONSENT_OUTDATED',
              message_key: 'hub.consent_outdated',
              retryable: false,
            },
          })
        return json(200, listing({ status: 'published' }))
      }
      if (url.includes('/v1/hub/areas')) return json(200, [])
      return json(404, {})
    })
    renderScreen(<HubListing />)
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('checkbox'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish listing' }))
    await waitFor(() => expect(gets).toBe(2))
    // The terms changed, so they must be agreed to again.
    expect(within(dialog).getByRole('checkbox')).not.toBeChecked()
    await userEvent.click(within(dialog).getByRole('checkbox'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish listing' }))
    await waitFor(() =>
      expect(posted).toEqual([
        { consent_version: '2026-11-14' },
        { consent_version: '2027-01-01' },
      ]),
    )
  })

  it('keeps unsaved edits when it reloads', async () => {
    let gets = 0
    fetchMock.mockImplementation(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/hub/listing') && (init.method ?? 'GET') === 'GET') {
        gets += 1
        return json(200, listing({ consent_version_current: `2027-01-0${gets}` }))
      }
      if (url.endsWith('/v1/hub/listing/publish'))
        return json(400, {
          error: {
            code: 'HUB_CONSENT_OUTDATED',
            message_key: 'hub.consent_outdated',
            retryable: false,
          },
        })
      if (url.includes('/v1/hub/areas')) return json(200, [])
      return json(404, {})
    })
    renderScreen(<HubListing />)
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('checkbox'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish listing' }))
    await waitFor(() => expect(gets).toBe(2))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    const name = screen.getByLabelText('Public name')
    await userEvent.type(name, ' Apa')
    expect(name).toHaveValue('Sumi Akter Apa')
  })
})

describe('NameConsent extras', () => {
  it('shows the exact name the centre page will publish', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith('/v1/me/centre-memberships')
        ? json(200, [
            {
              member_id: 'm1',
              centre_id: 'c1',
              centre_name: 'Udoy Coaching',
              role: 'teacher',
              public_name_consent: false,
              name_shown: 'Karim Sir',
            },
          ])
        : json(404, {}),
    )
    renderScreen(<NameConsent />)
    expect(await screen.findByText('Shown as: Karim Sir')).toBeInTheDocument()
  })

  it('shows a failure with Retry when the memberships cannot load', async () => {
    let calls = 0
    fetchMock.mockImplementation(async (url: string) => {
      if (!url.endsWith('/v1/me/centre-memberships')) return json(404, {})
      calls += 1
      if (calls === 1) throw new TypeError('Failed to fetch')
      return json(200, [
        {
          member_id: 'm1',
          centre_id: 'c1',
          centre_name: 'Udoy Coaching',
          role: 'teacher',
          public_name_consent: false,
          name_shown: 'Karim Sir',
        },
      ])
    })
    renderScreen(<NameConsent />)
    const alert = await screen.findByRole('alert')
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Udoy Coaching')).toBeInTheDocument()
  })
})

describe('publish sheet focus', () => {
  it('opens with focus inside the sheet', async () => {
    serve(listing())
    renderScreen(<HubListing />)
    await userEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog.contains(document.activeElement)).toBe(true)
  })
})
