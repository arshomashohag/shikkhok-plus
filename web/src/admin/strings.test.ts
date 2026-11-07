import { describe, expect, it } from 'vitest'
import enGenerated from '../i18n/generated/strings.en.json'
import { WEB_EN } from '../i18n/i18n'
import { ADMIN_BN, ADMIN_EN } from './strings'

describe('admin strings', () => {
  it('has every string in both languages', () => {
    expect(Object.keys(ADMIN_BN).sort()).toEqual(Object.keys(ADMIN_EN).sort())
    for (const [key, value] of Object.entries(ADMIN_BN)) expect(value, key).not.toBe('')
  })

  it('are all web_admin_ keys, and collide with nothing the main app has', () => {
    for (const key of Object.keys(ADMIN_EN)) {
      expect(key.startsWith('web_admin_')).toBe(true)
      expect(key in WEB_EN || key in enGenerated).toBe(false)
    }
  })

  it('are not in the main app’s web strings, which it globs from src/i18n/web', () => {
    expect(Object.keys(WEB_EN).filter((k) => k.startsWith('web_admin_'))).toEqual([])
  })

  it('keep the same placeholders in both languages', () => {
    const holes = (s: string) => (s.match(/\{\d\}/g) ?? []).sort().join()
    for (const key of Object.keys(ADMIN_EN))
      expect(holes(ADMIN_BN[key]!), key).toBe(holes(ADMIN_EN[key]!))
  })
})
