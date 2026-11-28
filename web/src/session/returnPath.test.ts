/**
 * The address kept across sign-in admits exactly the two public-link
 * forms, a report and a join request, and nothing near them: a path one
 * letter off, the guardian's own list, or another host [H5 F14].
 */
import { afterEach, describe, expect, it } from 'vitest'
import { forgetReturn, peekReturn, rememberReturn } from './returnPath'

afterEach(() => sessionStorage.clear())

const kept = (path: string) => {
  sessionStorage.clear()
  rememberReturn(path)
  return peekReturn()
}

describe('returnPath', () => {
  it.each([
    '/hub-report',
    '/hub-report?kind=owner_listing&id=x',
    '/hub-enquiry',
    '/hub-enquiry?owner=sumi-apa',
    '/hub-enquiry?owner=sumi-apa&batch=0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f',
    '/hub-interest?owner=sumi-apa&batch=0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f',
  ])('keeps %s', (path) => {
    expect(kept(path)).toBe(path)
  })

  it.each([
    '/hub-enquiries',
    '/hub-interests',
    '/hub-enquiryx',
    '/hub-enquiry/x',
    '//host/hub-enquiry',
    'https://host/hub-enquiry?owner=a',
    '/hub-reports',
    '/signin',
    '/today',
  ])('refuses %s', (path) => {
    expect(kept(path)).toBeNull()
  })

  it('refuses a stored address it would not have kept', () => {
    sessionStorage.setItem('sp.return', '//host/hub-enquiry')
    expect(peekReturn()).toBeNull()
  })

  it('forgets once used', () => {
    rememberReturn('/hub-enquiry?owner=a')
    forgetReturn()
    expect(peekReturn()).toBeNull()
  })
})
