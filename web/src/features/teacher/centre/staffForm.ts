/**
 * The staff form's state and the bodies it sends. Validation is format
 * only; whether pay terms pair is the server's rule, shown by its key.
 */
import type { Schemas } from '../../../api/endpoints'
import { normalisePhone } from '../../../core/format'
import { Money, toLatinDigits } from '../../../core/money'

export type StaffKind = 'teacher' | 'other'
export type PayBasis = Schemas['StaffResponse']['pay_basis']

export interface StaffInput {
  kind: StaffKind
  name: string
  phone: string
  email: string
  roleLabel: string
  house: string
  road: string
  city: string
  postcode: string
  basis: PayBasis
  rate: string
  joinedOn: string
}

/** An empty form, or one filled from an existing record to correct it. */
export function staffInput(kind: StaffKind, row?: Schemas['StaffResponse']): StaffInput {
  return {
    kind,
    name: row?.display_name ?? '',
    phone: row?.phone ?? '',
    email: row?.email ?? '',
    roleLabel: row?.role_label ?? '',
    house: row?.staff_house ?? '',
    road: row?.staff_road ?? '',
    city: row?.staff_city ?? '',
    postcode: row?.staff_postcode ?? '',
    basis: row?.pay_basis ?? 'monthly',
    rate: row?.pay_rate ? Money.fromWire(row.pay_rate).wire : '',
    joinedOn: row?.joined_on ?? '',
  }
}

const orNull = (s: string) => s.trim() || null

function details(input: StaffInput) {
  const rate = input.basis === 'none' ? null : Money.fromTyped(input.rate)
  if (input.basis !== 'none' && !rate) return null
  const postcode = toLatinDigits(input.postcode.trim())
  if (postcode && !/^[0-9]{4}$/.test(postcode)) return null
  return {
    display_name: input.name.trim(),
    email: orNull(input.email),
    staff_house: orNull(input.house),
    staff_road: orNull(input.road),
    staff_city: orNull(input.city),
    staff_postcode: postcode || null,
    pay_basis: input.basis,
    pay_rate: rate ? rate.wire : null,
    ...(input.joinedOn ? { joined_on: input.joinedOn } : {}),
  }
}

/** The body inviting a teacher, or null while it cannot be sent. */
export function teacherBody(input: StaffInput): Schemas['StaffTeacherRequest'] | null {
  const phone = normalisePhone(input.phone)
  const base = details(input)
  if (!base || !base.display_name || !phone) return null
  return { ...base, phone }
}

/** The body recording other staff, or null while it cannot be sent. */
export function otherBody(input: StaffInput): Schemas['StaffOtherRequest'] | null {
  const typedPhone = input.phone.trim()
  const phone = typedPhone ? normalisePhone(typedPhone) : null
  const base = details(input)
  if (!base || !base.display_name || (typedPhone && !phone)) return null
  return { ...base, phone, role_label: orNull(input.roleLabel) }
}

/** The correction to send: every editable field, so a cleared one clears. */
export function updateBody(input: StaffInput): Schemas['StaffUpdateRequest'] | null {
  const base = details(input)
  if (!base || !base.display_name) return null
  return input.kind === 'other' ? { ...base, role_label: orNull(input.roleLabel) } : base
}

/** The string key for where someone's app access stands. */
export function accessKey(row: Schemas['StaffResponse']): string {
  return `staff_access_${row.access}`
}
