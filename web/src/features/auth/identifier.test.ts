/**
 * The one shared email check: the server's pattern, its length counted
 * in code points [functional-spec § 1 defect 4] [NFR3.12] [FR11.3].
 * Corners from `app/accounts/identifier.py`; nothing compares the two
 * mechanically, so a server change is caught only by its own review.
 */
import { describe, expect, it } from 'vitest'
import { readIdentifier } from './identifier'

const email = (typed: string) => readIdentifier('email', typed)

/** `n` code points in all: astral characters, then `@b.cd`. */
function astralAddress(n: number): string {
  return '😀'.repeat(n - '@b.cd'.length) + '@b.cd'
}

describe('readIdentifier — email', () => {
  it('accepts the server pattern’s corners: a trailing dot and a leading-dot domain', () => {
    expect(email('a@b.c.')).toEqual({ email: 'a@b.c.' })
    expect(email('a@.b.c')).toEqual({ email: 'a@.b.c' })
  })

  it('refuses an address with no dot after the @, or nothing before it', () => {
    expect(email('a@b')).toBeNull()
    expect(email('@b.c')).toBeNull()
  })

  it('refuses an address with whitespace inside it', () => {
    expect(email('rina akter@example.com')).toBeNull()
    expect(email('rina@exam\tple.com')).toBeNull()
  })

  it('accepts 254 code points of astral characters, which JavaScript counts as more', () => {
    const address = astralAddress(254)
    expect([...address]).toHaveLength(254)
    expect(address.length).toBeGreaterThan(254)
    expect(email(address)).toEqual({ email: address })
  })

  it('refuses 255 code points', () => {
    expect(email(astralAddress(255))).toBeNull()
  })

  it('still trims and lowercases, as the server does', () => {
    expect(email('  Rina@Example.COM ')).toEqual({ email: 'rina@example.com' })
  })
})

describe('readIdentifier — phone', () => {
  it('is unchanged: a Bangla-digit number is normalised', () => {
    expect(readIdentifier('phone', '০১৭১১-২৩৪৫৬৭')).toEqual({ phone: '01711234567' })
    expect(readIdentifier('phone', '12345')).toBeNull()
  })
})
