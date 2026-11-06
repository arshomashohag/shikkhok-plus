/** The staff form's bodies: what is sent, and when nothing can be. */
import { describe, expect, it } from 'vitest'
import { otherBody, staffInput, teacherBody, updateBody } from './staffForm'

describe('teacherBody', () => {
  const filled = {
    ...staffInput('teacher'),
    name: ' Sumi ',
    phone: '01711111111',
    email: 'sumi@example.com',
    city: 'Dhaka',
    basis: 'per_class' as const,
    rate: '500',
  }

  it('sends the trimmed details, the rate as a string and blanks as null', () => {
    expect(teacherBody(filled)).toEqual({
      display_name: 'Sumi',
      phone: '01711111111',
      email: 'sumi@example.com',
      staff_house: null,
      staff_road: null,
      staff_city: 'Dhaka',
      staff_postcode: null,
      pay_basis: 'per_class',
      pay_rate: '500.00',
    })
  })

  it('needs a name, a phone, and a rate for a paid basis', () => {
    expect(teacherBody({ ...filled, name: '' })).toBeNull()
    expect(teacherBody({ ...filled, phone: '12' })).toBeNull()
    expect(teacherBody({ ...filled, rate: '' })).toBeNull()
    expect(teacherBody({ ...filled, postcode: '12' })).toBeNull()
  })
})

describe('otherBody', () => {
  it('sends no rate when unpaid, and no phone when none was typed', () => {
    const body = otherBody({
      ...staffInput('other'),
      name: 'Karim',
      roleLabel: 'Receptionist',
      basis: 'none',
      rate: '900',
    })
    expect(body).toMatchObject({ phone: null, pay_basis: 'none', pay_rate: null })
    expect(body?.role_label).toBe('Receptionist')
  })

  it('refuses a phone typed wrongly rather than dropping it', () => {
    expect(otherBody({ ...staffInput('other'), name: 'Karim', phone: '12' })).toBeNull()
  })
})

describe('updateBody', () => {
  it('sends a cleared field as null so the server clears it', () => {
    const row = {
      staff_id: 's1',
      kind: 'teacher' as const,
      display_name: 'Sumi',
      phone: '+8801711111111',
      email: 'sumi@example.com',
      pay_basis: 'monthly' as const,
      pay_rate: '9000.00',
      joined_on: '2026-11-01',
      status: 'active' as const,
      access: 'active' as const,
    }
    const body = updateBody({ ...staffInput('teacher', row), email: '' })
    expect(body).toMatchObject({ email: null, pay_rate: '9000.00', joined_on: '2026-11-01' })
    expect(body).not.toHaveProperty('role_label')
  })
})
