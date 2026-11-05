import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  BUNDLES,
  MESSAGE_KEYS,
  translate,
  translateMessage,
  translatePlural,
  WEB_BN,
  WEB_EN,
} from './i18n'

describe('bundles', () => {
  it('has every string in both languages', () => {
    expect(Object.keys(BUNDLES.bn).sort()).toEqual(Object.keys(BUNDLES.en).sort())
    expect(Object.keys(WEB_BN).sort()).toEqual(Object.keys(WEB_EN).sort())
  })

  it('keeps web-only keys out of the Android namespace', () => {
    for (const key of Object.keys(WEB_EN)) expect(key.startsWith('web_')).toBe(true)
  })

  it('fills positional arguments and plurals', () => {
    expect(translate('en', 'batches_count', 7, 112)).toBe('7 batches · 112 students')
    expect(translatePlural('en', 'batches_student_count', 1)).toBe('1 student')
    expect(translatePlural('en', 'batches_student_count', 18)).toBe('18 students')
    expect(translate('bn', 'batches_count', 7, 112)).toContain('7')
  })

  it('falls back to the key, never to an empty string', () => {
    expect(translate('en', 'no_such_key')).toBe('no_such_key')
  })
})

// The web counterpart of Android's MessageKeyCoverageTest: every key the
// server can emit (the committed ../message-keys.json) renders a real
// string in both languages, so no error ever shows a raw key.
describe('server message keys', () => {
  const emitted = (
    JSON.parse(readFileSync(resolve(process.cwd(), '..', 'message-keys.json'), 'utf8')) as {
      keys: string[]
    }
  ).keys

  it.each(emitted)('%s has a string in both languages', (key) => {
    const resource = MESSAGE_KEYS[key]
    expect(resource, `no mapping for ${key}`).toBeDefined()
    expect(BUNDLES.en[resource as string]).toBeDefined()
    expect(BUNDLES.bn[resource as string]).toBeDefined()
    expect(translateMessage('bn', key)).not.toBe(resource)
  })

  it('maps an unknown key to the generic message', () => {
    expect(translateMessage('en', 'not.a.key')).toBe(translate('en', 'error_unexpected'))
  })
})
