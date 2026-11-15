// @vitest-environment node
/**
 * Only the modules that own usernames and sign-in build a body with a
 * `username` or `login` key [NFR3.7] [frontend-components § 8].
 *
 * The username is owner-private: it arrives only in the account's own
 * responses and is sent only by the API layer, sign-in, sign-up (with
 * its code flow and Replace step) and the username screens. A new module
 * that starts sending one fails here, where review sees the list change.
 *
 * Textual, like `scripts/check-bundles.mjs`, and paired the same way: a
 * "present" assertion on `api/endpoints.ts` means an empty or misdirected
 * scan fails rather than passes. **Limit:** deliberate string building
 * defeats it; the fetch-layer tests' no-query-string assertions are its
 * behavioural half [NFR3.1].
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = process.cwd()

/** A `username:` or `login:` object key with a value (not a type, not a function). */
const KEYED = /(?:^|[{,])\s*['"]?(username|login)['"]?\s*:\s*(?!string\b|\(\s*\)\s*=>)\S/
/** A `{ username }` or `{ login, password }` shorthand, not a JSX `={username}`. */
const SHORTHAND = /(?<![=\w])\{\s*(username|login)\s*[,}]|,\s*(username|login)\s*[,}]/

/** Where a `username` or `login` key may be built. */
const ALLOWED = ['src/api/endpoints.ts', 'src/features/auth/', 'src/features/account/username/']

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    const rel = relative(ROOT, path).split('\\').join('/')
    if (rel === 'src/i18n/generated' || rel === 'src/test') return []
    if (entry.isDirectory()) return sourceFiles(path)
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) return []
    if (rel === 'src/api/schema.d.ts') return []
    return [rel]
  })
}

/** Each line building a `username` or `login` key, as `file:line: text`. */
function keyLines(): { file: string; line: string }[] {
  return sourceFiles(join(ROOT, 'src')).flatMap((file) =>
    readFileSync(join(ROOT, file), 'utf8')
      .split('\n')
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .filter((line) => KEYED.test(line) || SHORTHAND.test(line))
      .map((line) => ({ file, line: line.trim() })),
  )
}

const allowed = (file: string) => ALLOWED.some((a) => file === a || file.startsWith(a))

describe('the username and login send path [NFR3.7]', () => {
  it('the scan finds the keys the API layer builds (present)', () => {
    const endpoints = keyLines().filter((k) => k.file === 'src/api/endpoints.ts')
    expect(endpoints.some((k) => /\blogin\b/.test(k.line))).toBe(true)
    expect(endpoints.some((k) => /\busername\b/.test(k.line))).toBe(true)
  })

  it('the patterns tell a key from a type, a function and a JSX attribute', () => {
    for (const sent of [
      'body: { login, password },',
      '  username: values.username.trim(),',
      '{ username }',
    ])
      expect(KEYED.test(sent) || SHORTHAND.test(sent), sent).toBe(true)
    for (const not of ['  username: string', 'value={username}', "username: () => '/x',"])
      expect(KEYED.test(not) || SHORTHAND.test(not), not).toBe(false)
  })

  it('no other module builds one (absent)', () => {
    const outside = keyLines()
      .filter((k) => !allowed(k.file))
      .map((k) => `${k.file}: ${k.line}`)
    expect(outside).toEqual([])
  })
})
