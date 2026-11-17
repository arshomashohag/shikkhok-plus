/**
 * The public-hub editor's pure parts: what a draft is, what changed, and
 * which words and chip a server answer gets.
 *
 * **Every decision is the server's.** The checklist's items and the
 * `publishable` flag arrive computed; nothing here decides whether a
 * listing is complete, and no money value is parsed. [TC-9] [D-31]
 */
import type { Schemas } from '../../../api/endpoints'

export type Listing = Schemas['OwnerListingResponse']
export type BatchListing = Schemas['BatchListingResponse']
export type ListingStatus = Listing['status']
export type TeachingMode = Listing['teaching_mode'][number]
export type ChecklistItem = Schemas['ChecklistItemWire']

export const TEACHING_MODES: readonly TeachingMode[] = ['in_person', 'home_visit', 'online']

export type ClassLevel = BatchListing['class_levels'][number]
export type Curriculum = NonNullable<BatchListing['curriculum']>

/**
 * The closed class-level vocabulary, in the order a teacher reads it. The
 * contract's enum is the authority; `satisfies` makes a value the server
 * would refuse a compile error here.
 */
export const CLASS_LEVELS = [
  'class_1',
  'class_2',
  'class_3',
  'class_4',
  'class_5',
  'class_6',
  'class_7',
  'class_8',
  'class_9',
  'class_10',
  'class_11',
  'class_12',
  'ssc',
  'hsc',
  'admission',
  'o_level',
  'a_level',
  'other',
] as const satisfies readonly ClassLevel[]

export const CURRICULA = [
  'national_bangla',
  'national_english',
  'english_medium',
  'madrasah',
  'other',
] as const satisfies readonly Curriculum[]

/** Saved class levels and curriculum in the reader's words, never the raw values. */
export function levelsLine(
  b: Pick<BatchListing, 'class_levels' | 'curriculum'>,
  t: (key: string) => string,
): string {
  const levels = b.class_levels.map((l) => t(`web_hub_level_${l}`)).join(', ')
  const curriculum = b.curriculum ? t(`web_hub_curriculum_${b.curriculum}`) : ''
  return [levels, curriculum].filter(Boolean).join(' · ')
}

export const STATUS_KEY: Record<ListingStatus, string> = {
  draft: 'web_hub_status_draft',
  published: 'web_hub_status_published',
  hidden: 'web_hub_status_hidden',
  suspended: 'web_hub_status_suspended',
}

/** Draft is neutral and suspended is the error tone; the rest use the shared chips. */
export const STATUS_CHIP: Record<ListingStatus, string> = {
  draft: 'chip-neutral',
  published: 'chip-paid',
  hidden: 'chip-partial',
  suspended: 'chip-overdue',
}

/** The label for a checklist item, or null for a key this client has no words for. */
export function checklistLabelKey(key: string): string | null {
  return KNOWN_CHECKS.has(key) ? `web_hub_check_${key}` : null
}

const KNOWN_CHECKS: ReadonlySet<string> = new Set([
  'public_name',
  'public_title',
  'slug',
  'area',
  'headline',
  'bio',
  'contact_or_none',
  'description',
  'class_levels',
  'subjects',
  'mode',
])

/** What the owner has typed, as strings so an input never holds null. */
export interface Draft {
  publicName: string
  publicNameLatin: string
  slug: string
  headlineEn: string
  headlineBn: string
  bioEn: string
  bioBn: string
  qualifications: string
  modes: TeachingMode[]
  districtCode: string
  upazilaCode: string
  streetAddress: string
  phone: string
}

export function draftOf(l: Listing): Draft {
  return {
    publicName: l.public_name,
    publicNameLatin: l.public_name_latin ?? '',
    slug: l.slug ?? '',
    headlineEn: l.headline_en ?? '',
    headlineBn: l.headline_bn ?? '',
    bioEn: l.bio_en ?? '',
    bioBn: l.bio_bn ?? '',
    qualifications: l.qualifications ?? '',
    modes: [...l.teaching_mode],
    districtCode: l.district_code ?? '',
    upazilaCode: l.upazila_code ?? '',
    streetAddress: l.street_address ?? '',
    phone: l.public_contact_phone ?? '',
  }
}

const sameModes = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((m) => b.includes(m))

/** True when the draft differs from what the server holds. */
export function isDirty(draft: Draft, l: Listing): boolean {
  return updateBody(draft, l) !== null
}

/**
 * The fields that changed, or null when nothing did. An omitted field is
 * left alone by the server and an empty string clears a text field, so
 * only what the person touched is sent. The district and upazila travel
 * together: the server checks that the upazila lies in the district.
 */
export function updateBody(draft: Draft, l: Listing): Schemas['OwnerListingUpdateRequest'] | null {
  const was = draftOf(l)
  const body: Schemas['OwnerListingUpdateRequest'] = {}
  if (draft.publicName.trim() !== was.publicName) body.public_name = draft.publicName.trim()
  if (draft.publicNameLatin.trim() !== was.publicNameLatin)
    body.public_name_latin = draft.publicNameLatin.trim()
  if (draft.slug.trim() !== was.slug) body.slug = draft.slug.trim()
  if (draft.headlineEn !== was.headlineEn) body.headline_en = draft.headlineEn
  if (draft.headlineBn !== was.headlineBn) body.headline_bn = draft.headlineBn
  if (draft.bioEn !== was.bioEn) body.bio_en = draft.bioEn
  if (draft.bioBn !== was.bioBn) body.bio_bn = draft.bioBn
  if (draft.qualifications !== was.qualifications) body.qualifications = draft.qualifications
  if (!sameModes(draft.modes, was.modes)) body.teaching_mode = draft.modes
  if (draft.districtCode !== was.districtCode || draft.upazilaCode !== was.upazilaCode) {
    body.district_code = draft.districtCode
    body.upazila_code = draft.upazilaCode
  }
  if (draft.streetAddress !== was.streetAddress) body.street_address = draft.streetAddress
  if (draft.phone.trim() !== was.phone) body.public_contact_phone = draft.phone.trim()
  return Object.keys(body).length > 0 ? body : null
}

/**
 * The division a district sits in. A BBS district code is its division's
 * code followed by two digits (`BD2019` in `BD20`), which is how the
 * area list is keyed; an unrecognised code gives null, and the person
 * picks the division again.
 */
export function divisionOf(districtCode: string, divisionCodes: readonly string[]): string {
  return divisionCodes.find((d) => districtCode.startsWith(d) && districtCode !== d) ?? ''
}

// ------------------------------------------------------------- batches

export interface BatchDraft {
  slug: string
  publicTitle: string
  descriptionEn: string
  descriptionBn: string
  syllabusEn: string
  syllabusBn: string
  levels: ClassLevel[]
  curriculum: '' | Curriculum
  tags: string
  mode: '' | NonNullable<BatchListing['mode']>
  admissions: NonNullable<BatchListing['admissions']>
  showFee: boolean
  showSchedule: boolean
}

export function batchDraftOf(b: BatchListing): BatchDraft {
  return {
    slug: b.slug ?? '',
    publicTitle: b.public_title ?? '',
    descriptionEn: b.description_en ?? '',
    descriptionBn: b.description_bn ?? '',
    syllabusEn: b.syllabus_en ?? '',
    syllabusBn: b.syllabus_bn ?? '',
    levels: [...b.class_levels],
    curriculum: b.curriculum ?? '',
    tags: b.subject_tags.join(', '),
    mode: b.mode ?? '',
    admissions: b.admissions ?? 'open',
    showFee: b.show_fee ?? false,
    showSchedule: b.show_schedule ?? false,
  }
}

/** A comma-separated field as a list, without blanks. */
export function splitList(text: string): string[] {
  return text
    .split(/[,،]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/**
 * A batch listing's first save must say whether the fee and the timetable
 * are public, so both flags always travel; the rest is the full draft,
 * which the server treats as the new values.
 */
export function batchBody(d: BatchDraft): Schemas['BatchListingUpdateRequest'] {
  return {
    slug: d.slug.trim() || undefined,
    public_title: d.publicTitle.trim(),
    description_en: d.descriptionEn,
    description_bn: d.descriptionBn,
    syllabus_en: d.syllabusEn,
    syllabus_bn: d.syllabusBn,
    // In vocabulary order, whatever order they were tapped in.
    class_levels: CLASS_LEVELS.filter((l) => d.levels.includes(l)),
    curriculum: d.curriculum,
    subject_tags: splitList(d.tags),
    mode: d.mode,
    admissions: d.admissions,
    show_fee: d.showFee,
    show_schedule: d.showSchedule,
  }
}

/** The exact fallback label the server sends for a member who has not agreed to be named. */
export const CENTRE_FACULTY = 'Centre faculty'

/** Teacher names for display; the server's fallback label is shown in the reader's language. */
export function teacherLine(names: readonly string[], t: (key: string) => string): string {
  return names.map((n) => (n === CENTRE_FACULTY ? t('web_hub_centre_faculty') : n)).join(', ')
}
