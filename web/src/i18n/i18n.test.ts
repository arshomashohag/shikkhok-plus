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

describe('server messages with placeholders', () => {
  it('fills the tries-left count from the details, in both languages', () => {
    expect(translateMessage('en', 'auth.otp.wrong', { attempts_left: '2' })).toBe(
      "That code isn't right. 2 tries left.",
    )
    expect(translateMessage('bn', 'auth.otp.wrong', { attempts_left: '২' })).toContain('২')
  })

  it('never shows a raw placeholder when the count is missing', () => {
    const cases: (Record<string, string> | null | undefined)[] = [
      undefined,
      null,
      {},
      { attempts_left: '' },
    ]
    for (const details of cases) {
      const text = translateMessage('en', 'auth.otp.wrong', details)
      expect(text).toBe("That code isn't right.")
      expect(text).not.toMatch(/\{\d\}/)
    }
    expect(translateMessage('bn', 'auth.otp.wrong')).not.toMatch(/\{\d\}/)
  })

  it('leaves messages without placeholders alone, details or not', () => {
    expect(translateMessage('en', 'auth.otp.expired', { attempts_left: '2' })).toBe(
      translateMessage('en', 'auth.otp.expired'),
    )
  })

  it('leaves no server message with an unfilled placeholder', () => {
    // Every message key whose string carries a placeholder must be in
    // MESSAGE_ARGS; this catches the next one before a person reads it.
    for (const key of Object.keys(MESSAGE_KEYS)) {
      for (const lang of ['en', 'bn'] as const) {
        expect(translateMessage(lang, key), `${lang} ${key}`).not.toMatch(/\{\d\}/)
      }
    }
  })
})

// The web-only strings the username and contacts change made false
// (functional-spec § 5, the swept list). Each English text is pinned to
// the design's wording, so a reword that drifts back fails here.
describe('web-only strings swept for usernames and contacts [FR11.2]', () => {
  it('drops the old sign-in refusal string from both languages', () => {
    expect(WEB_EN).not.toHaveProperty('web_auth_password_wrong')
    expect(WEB_BN).not.toHaveProperty('web_auth_password_wrong')
  })

  const REWORDED: Record<string, string> = {
    web_auth_signin_body: 'With your username, mobile number or email address, and your password.',
    web_auth_point_login:
      'Log in with your username, mobile number or email address and a password.',
    web_password_set_body:
      "From now on you'll log in with your username, mobile number or email address and this password.",
    web_auth_signup_phone_help:
      "We'll send a code to this number. Teachers find students and guardians by phone number or email.",
    web_auth_signup_email_help:
      "We'll send a code to this address. Teachers find students and guardians by phone number or email.",
    web_contact_add_phone_why:
      'Teachers find students and guardians by phone number or email. Add your number to see the batches they added you to by it.',
    web_contact_add_email_why:
      'Log in with it too, get codes by email, and see the batches teachers added you to by this address.',
    web_students_col_phone: "Student's contact",
    web_students_no_phone: 'No contact',
    web_roster_col_contact: 'Contact and invitation',
  }

  it.each(Object.entries(REWORDED))('%s reads as the design words it', (key, text) => {
    expect(WEB_EN[key]).toBe(text)
    expect(WEB_BN[key]).toBeDefined()
    expect(WEB_BN[key]).not.toBe(text)
  })

  it.each([
    'web_auth_replace_username_body_plain',
    'web_students_add_by_email',
    'web_student_edit_title',
    'web_student_edit_save',
    'web_student_edit_saved',
  ])('%s is new and present in both languages', (key) => {
    expect(WEB_EN[key]).toBeTruthy()
    expect(WEB_BN[key]).toBeTruthy()
    expect(WEB_BN[key]).not.toBe(WEB_EN[key])
  })
})
