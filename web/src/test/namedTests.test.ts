// @vitest-environment node
/**
 * The named test files this unit adds or extends [NFR5.1].
 *
 * No web coverage figure exists, and none is claimed (tech-stack TSD-3).
 * The obligation is named tests instead, and this list is the same one as
 * `unit-test-instructions.md`: change both together. A listed file that
 * goes missing fails here; a listed file that remains but holds no test
 * fails the Vitest run itself.
 *
 * **Not caught, stated plainly:** a weakened case inside a file that
 * still holds others, and a new module that ships with no test file at
 * all. Both are review's, against frontend-components § 8.
 */
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const NAMED_TEST_FILES = [
  'src/api/client.test.ts',
  'src/session/session.test.ts',
  'src/session/usernameGate.routing.test.tsx',
  'src/shell/RouteErrorBoundary.test.tsx',
  'src/i18n/i18n.test.ts',
  'src/features/auth/identifier.test.ts',
  'src/features/auth/parts.test.tsx',
  'src/features/auth/SignIn.test.tsx',
  'src/features/auth/SignUp.test.tsx',
  'src/features/auth/PasswordCode.test.tsx',
  'src/features/auth/username/availability.test.ts',
  'src/features/auth/username/useUsernameAvailability.test.ts',
  'src/features/auth/username/UsernameField.test.tsx',
  'src/features/account/username/ChooseUsernameGate.test.tsx',
  'src/features/account/username/username.test.tsx',
  'src/features/account/contacts/contacts.test.tsx',
  'src/features/account/security/security.test.tsx',
  'src/features/account/security/password.test.tsx',
  'src/features/teacher/people/people.test.tsx',
  'src/features/teacher/students/students.test.tsx',
  'src/features/teacher/students/mappers.test.ts',
  'src/features/teacher/centre/Members.test.ts',
  'src/features/teacher/centre/centre.screens.test.tsx',
  'src/test/lintConfig.test.ts',
  'src/test/noIdentifierLeaks.test.tsx',
  'src/test/usernameKeyScan.test.ts',
  'src/test/namedTests.test.ts',
] as const

describe('the named test files [NFR5.1]', () => {
  it.each(NAMED_TEST_FILES)('%s exists and declares a test', (file) => {
    const path = join(process.cwd(), file)
    expect(existsSync(path), `${file} is missing`).toBe(true)
    expect(readFileSync(path, 'utf8')).toMatch(/\b(it|test)(\.each\([^)]*\))?\(/)
  })

  it('the list is this unit’s, with no file named twice', () => {
    expect(new Set(NAMED_TEST_FILES).size).toBe(NAMED_TEST_FILES.length)
    expect(NAMED_TEST_FILES).toHaveLength(27)
  })
})
